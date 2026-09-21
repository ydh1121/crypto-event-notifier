from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import b3_trader.dex_launch_coverage_audit as build60


def _feature(launch_status: str) -> str:
    return json.dumps(
        {
            "pool_quality": {"passed": True},
            "domestic_listing_window": {"status": "collected", "p5m_exact_minute": True},
            "pool_launch_window": {"status": launch_status},
        }
    )


def _db(path: Path, now: float) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE dex_launch_assets(
              asset_key TEXT PRIMARY KEY,case_key TEXT,network_id TEXT,token_address TEXT
            );
            CREATE TABLE dex_launch_pools(
              asset_key TEXT,pool_address TEXT,dex_id TEXT,pool_created_at REAL,
              reserve_usd REAL,volume_h24_usd REAL,gate_status TEXT,selected_primary INTEGER
            );
            CREATE TABLE dex_launch_features(
              asset_key TEXT,pool_address TEXT,feature_json TEXT
            );
            CREATE TABLE dex_launch_candles(
              asset_key TEXT,pool_address TEXT,series_kind TEXT,candle_ts REAL
            );
            """
        )
        created = now - 10 * 86400
        cases = [
            ("asset-collected", "case-collected", "base", "0x1", "pool-collected", "collected"),
            ("asset-partial", "case-partial", "bsc", "0x2", "pool-partial", "launch_ohlcv_unavailable"),
            ("asset-alt", "case-alt", "eth", "0x3", "pool-alt-primary", "launch_ohlcv_unavailable"),
            ("asset-attempted", "case-attempted", "base", "0x4", "pool-attempted", "launch_ohlcv_unavailable"),
        ]
        for asset_key, case_key, network, token, pool, status in cases:
            conn.execute(
                "INSERT INTO dex_launch_assets(asset_key,case_key,network_id,token_address) VALUES(?,?,?,?)",
                (asset_key, case_key, network, token),
            )
            conn.execute(
                "INSERT INTO dex_launch_pools VALUES(?,?,?,?,?,?,?,?)",
                (asset_key, pool, "dex", created, 100000.0, 50000.0, "accepted", 1),
            )
            conn.execute(
                "INSERT INTO dex_launch_features VALUES(?,?,?)",
                (asset_key, pool, _feature(status)),
            )

        conn.execute(
            "INSERT INTO dex_launch_candles VALUES(?,?,?,?)",
            ("asset-collected", "pool-collected", "launch_hourly", created + 1800),
        )
        conn.execute(
            "INSERT INTO dex_launch_candles VALUES(?,?,?,?)",
            ("asset-partial", "pool-partial", "launch_hourly", created + 7200),
        )
        conn.execute(
            "INSERT INTO dex_launch_pools VALUES(?,?,?,?,?,?,?,?)",
            ("asset-alt", "pool-alt-secondary", "alt-dex", created + 100, 90000.0, 40000.0, "accepted", 0),
        )
        conn.commit()
    finally:
        conn.close()


def test_build60_separates_launch_reference_gap_attempts_and_alternate_pools(tmp_path, monkeypatch):
    now = 2_000_000_000.0
    db_path = tmp_path / "audit.sqlite3"
    state_path = tmp_path / "state.json"
    _db(db_path, now)
    state_path.write_text(json.dumps({"launch_attempted_at": {"asset-attempted": now - 100}}), encoding="utf-8")

    quality_rows = [
        {
            "case_key": "case-collected",
            "coingecko_id": "collected",
            "usable_for_shadow_analysis": True,
            "launch_feature_asset_count": 1,
        },
        {
            "case_key": "case-partial",
            "coingecko_id": "partial",
            "usable_for_shadow_analysis": True,
            "launch_feature_asset_count": 0,
        },
        {
            "case_key": "case-alt",
            "coingecko_id": "alt",
            "usable_for_shadow_analysis": True,
            "launch_feature_asset_count": 0,
        },
        {
            "case_key": "case-attempted",
            "coingecko_id": "attempted",
            "usable_for_shadow_analysis": True,
            "launch_feature_asset_count": 0,
        },
    ]
    monkeypatch.setattr(
        build60,
        "evaluate_dex_launch_quality",
        lambda _path: {"ok": True, "cases": quality_rows},
    )

    result = build60.audit_dex_launch_coverage(db_path, state_path=state_path, now=now)

    assert result["ok"] is True
    assert result["read_only"] is True
    assert result["network_fetches"] is False
    assert result["summary"]["usable_event_cases"] == 4
    assert result["summary"]["launch_feature_cases"] == 1
    assert result["summary"]["required_launch_feature_cases"] == 2
    assert result["summary"]["additional_launch_cases_needed"] == 1
    assert result["summary"]["fresh_primary_source_count"] == 1
    assert result["summary"]["alternate_accepted_pool_candidates"] == 1

    gap = {row["case_key"]: row for row in result["missing_cases"]}
    partial = gap["case-partial"]["assets"][0]
    assert partial["classification"] == "partial_candles_without_launch_reference"
    assert partial["launch_hourly_count"] == 1
    assert partial["first_launch_hourly_delta_seconds"] == 7200.0
    assert partial["reference_available_by_original_build42_rule"] is False

    attempted = gap["case-attempted"]["assets"][0]
    assert attempted["classification"] == "attempted_source_unavailable"
    assert attempted["source_previously_attempted"] is True

    alt = result["alternate_pool_opportunities"][0]
    assert alt["case_key"] == "case-alt"
    assert alt["pool_address"] == "pool-alt-secondary"
    assert result["recommended_next_action"] == "targeted_alternate_accepted_pool_probe_review"


def test_build60_does_not_offer_secondary_assets_from_already_counted_case(tmp_path, monkeypatch):
    now = 2_000_000_000.0
    db_path = tmp_path / "counted.sqlite3"
    state_path = tmp_path / "state.json"
    _db(db_path, now)
    state_path.write_text("{}", encoding="utf-8")

    quality_rows = [
        {
            "case_key": "case-alt",
            "coingecko_id": "alt",
            "usable_for_shadow_analysis": True,
            "launch_feature_asset_count": 1,
        }
    ]
    monkeypatch.setattr(
        build60,
        "evaluate_dex_launch_quality",
        lambda _path: {"ok": True, "cases": quality_rows},
    )

    result = build60.audit_dex_launch_coverage(db_path, state_path=state_path, now=now)
    assert result["summary"]["launch_feature_cases"] == 1
    assert result["summary"]["fresh_primary_source_count"] == 0
    assert result["summary"]["alternate_accepted_pool_candidates"] == 0
