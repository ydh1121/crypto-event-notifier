from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from b3_trader.dex_shadow_score import audit_dex_shadow_scores


def _ready(_path):
    return {"shadow_readiness_advisory": True, "blocking_reasons": []}


def _blocked(_path):
    return {"shadow_readiness_advisory": False, "blocking_reasons": ["launch_feature_coverage_below_min"]}


def _quality(_path):
    return {
        "cases": [
            {
                "case_key": "bithumb|KRW-TEST|notice:1",
                "coingecko_id": "test-coin",
                "usable_for_shadow_analysis": True,
            }
        ]
    }


def _point(return_value: float, *, target_ts: float | None = None) -> dict:
    row = {"return_to_domestic_open_pct": return_value, "return_from_domestic_open_pct": return_value}
    if target_ts is not None:
        row["target_ts"] = target_ts
    return row


def _db(path: Path, *, post_p5m: float = 10.0, launch_after_listing: bool = False) -> None:
    domestic_open_at = 2_000_000.0
    pool_created_at = domestic_open_at - 3 * 86400
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            CREATE TABLE listing_history_cases(
              case_key TEXT PRIMARY KEY,
              domestic_exchange TEXT NOT NULL,
              domestic_market TEXT NOT NULL,
              symbol TEXT NOT NULL,
              domestic_open_at REAL NOT NULL
            );
            CREATE TABLE dex_launch_assets(
              asset_key TEXT PRIMARY KEY,
              case_key TEXT NOT NULL,
              network_id TEXT NOT NULL
            );
            CREATE TABLE dex_launch_pools(
              asset_key TEXT NOT NULL,
              pool_address TEXT NOT NULL,
              dex_id TEXT NOT NULL,
              pool_created_at REAL NOT NULL,
              gate_status TEXT NOT NULL,
              selected_primary INTEGER NOT NULL,
              PRIMARY KEY(asset_key,pool_address)
            );
            CREATE TABLE dex_launch_features(
              asset_key TEXT NOT NULL,
              pool_address TEXT NOT NULL,
              feature_version INTEGER NOT NULL,
              feature_json TEXT NOT NULL,
              PRIMARY KEY(asset_key,pool_address)
            );
            """
        )
        conn.execute(
            "INSERT INTO listing_history_cases VALUES(?,?,?,?,?)",
            ("bithumb|KRW-TEST|notice:1", "bithumb", "KRW-TEST", "TEST", domestic_open_at),
        )
        conn.execute(
            "INSERT INTO dex_launch_assets VALUES(?,?,?)",
            ("asset-primary", "bithumb|KRW-TEST|notice:1", "eth"),
        )
        conn.execute(
            "INSERT INTO dex_launch_assets VALUES(?,?,?)",
            ("asset-alt", "bithumb|KRW-TEST|notice:1", "eth"),
        )
        conn.execute(
            "INSERT INTO dex_launch_pools VALUES(?,?,?,?,?,?)",
            ("asset-primary", "0xprimary", "uniswap_v3", pool_created_at, "accepted", 1),
        )
        conn.execute(
            "INSERT INTO dex_launch_pools VALUES(?,?,?,?,?,?)",
            ("asset-alt", "0xalt", "uniswap-v4-ethereum", pool_created_at, "accepted", 0),
        )

        primary_feature = {
            "pool_quality": {"passed": True, "reserve_usd": 999999.0, "volume_h24_usd": 999999.0},
            "domestic_listing_window": {
                "status": "collected",
                "pre": {
                    "t1h": _point(8.0),
                    "t6h": _point(15.0),
                    "t1d": _point(25.0),
                    "t3d": _point(20.0),
                    "t7d": _point(10.0),
                },
                "post": {
                    "p5m": _point(post_p5m),
                    "p1h": _point(12.0),
                    "p6h": _point(18.0),
                    "p24h": _point(22.0),
                    "p3d": _point(30.0),
                    "p7d": _point(40.0),
                },
            },
            "pool_launch_window": {"status": "launch_ohlcv_unavailable"},
        }
        launch_target_base = domestic_open_at + 3600 if launch_after_listing else pool_created_at
        alternate_feature = {
            "pool_quality": {"passed": True},
            "domestic_listing_window": {
                "status": "alternate_pool_probe_not_used_for_domestic_listing_window",
                "pre": {},
                "post": {},
            },
            "pool_launch_window": {
                "status": "collected",
                "pool_created_at": pool_created_at,
                "windows": {
                    "p5m": {
                        "target_ts": launch_target_base + 300,
                        "return_from_launch_pct": 20.0,
                    },
                    "p1h": {
                        "target_ts": launch_target_base + 3600,
                        "return_from_launch_pct": 30.0,
                    },
                    "p6h": {
                        "target_ts": launch_target_base + 21600,
                        "return_from_launch_pct": 45.0,
                    },
                    "p24h": {
                        "target_ts": launch_target_base + 86400,
                        "return_from_launch_pct": 70.0,
                    },
                },
            },
        }
        conn.execute(
            "INSERT INTO dex_launch_features VALUES(?,?,?,?)",
            ("asset-primary", "0xprimary", 1, json.dumps(primary_feature)),
        )
        conn.execute(
            "INSERT INTO dex_launch_features VALUES(?,?,?,?)",
            ("asset-alt", "0xalt", 1, json.dumps(alternate_feature)),
        )
        conn.commit()
    finally:
        conn.close()


def test_build62_is_deterministic_and_post_listing_labels_do_not_change_score(tmp_path: Path) -> None:
    db_path = tmp_path / "sample.sqlite3"
    _db(db_path, post_p5m=10.0)

    first = audit_dex_shadow_scores(db_path, readiness_fn=_ready, quality_fn=_quality)
    assert first["ok"] is True
    assert first["status"] == "scored_read_only"
    assert first["case_score_count"] == 1
    row = first["case_scores"][0]
    first_score = row["shadow_score"]
    assert first_score > 50.0
    assert row["confidence"] == 1.0
    assert row["components"]["launch_continuity"]["available"] is True
    assert row["inputs"]["launch_source"]["source_kind"] == "alternate_accepted"
    assert row["evaluation_only_outcomes"]["excluded_from_score"] is True
    assert row["evaluation_only_outcomes"]["post_listing_returns_pct"]["p5m"] == 10.0

    conn = sqlite3.connect(str(db_path))
    try:
        raw = conn.execute(
            "SELECT feature_json FROM dex_launch_features WHERE asset_key='asset-primary' AND pool_address='0xprimary'"
        ).fetchone()[0]
        feature = json.loads(raw)
        feature["domestic_listing_window"]["post"]["p5m"]["return_from_domestic_open_pct"] = -99.0
        conn.execute(
            "UPDATE dex_launch_features SET feature_json=? WHERE asset_key='asset-primary' AND pool_address='0xprimary'",
            (json.dumps(feature),),
        )
        conn.commit()
    finally:
        conn.close()

    second = audit_dex_shadow_scores(db_path, readiness_fn=_ready, quality_fn=_quality)
    second_row = second["case_scores"][0]
    assert second_row["shadow_score"] == first_score
    assert second_row["evaluation_only_outcomes"]["post_listing_returns_pct"]["p5m"] == -99.0


def test_build62_excludes_launch_windows_that_occur_after_domestic_listing(tmp_path: Path) -> None:
    db_path = tmp_path / "sample.sqlite3"
    _db(db_path, launch_after_listing=True)
    result = audit_dex_shadow_scores(db_path, readiness_fn=_ready, quality_fn=_quality)
    row = result["case_scores"][0]
    assert row["components"]["launch_continuity"]["available"] is False
    assert "launch_continuity" in row["missing_feature_flags"]
    assert row["confidence"] == 0.8
    assert all(value is None for value in row["inputs"]["launch_returns_pct_prelisting_only"].values())


def test_build62_fails_closed_when_build53_readiness_is_false(tmp_path: Path) -> None:
    result = audit_dex_shadow_scores(tmp_path / "missing.sqlite3", readiness_fn=_blocked, quality_fn=_quality)
    assert result["ok"] is False
    assert result["status"] == "readiness_blocked"
    assert result["scoring_enabled_for_audit"] is False
    assert result["case_score_count"] == 0
    assert result["case_scores"] == []
    assert result["can_place_orders"] is False
    assert result["score_wired"] is False
