from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from b3_trader.dex_shadow_score_v2_forward import audit_dex_shadow_score_v2_forward
from b3_trader.dex_shadow_score_v2_preregistration import FORWARD_CUTOFF_TS


def _ready_prereg(_: Path | str) -> dict:
    return {
        "ok": True,
        "status": "v2_preregistered_forward_only",
        "v1": {"retired": True},
        "v2": {
            "score_version": 2,
            "score_name": "dex_prelisting_exhaustion_shadow_hypothesis_v2",
        },
        "forward_boundary": {"cutoff_unix": FORWARD_CUTOFF_TS},
        "review": {"build66_forward_scorer_allowed": True},
    }


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE listing_history_cases (case_key TEXT PRIMARY KEY, domestic_exchange TEXT, domestic_market TEXT, symbol TEXT, domestic_open_at REAL)"
        )
        conn.execute(
            "CREATE TABLE dex_launch_assets (case_key TEXT, asset_key TEXT, network_id TEXT)"
        )
        conn.execute(
            "CREATE TABLE dex_launch_pools (asset_key TEXT, pool_address TEXT, dex_id TEXT, pool_created_at REAL, gate_status TEXT, selected_primary INTEGER)"
        )
        conn.execute(
            "CREATE TABLE dex_launch_features (asset_key TEXT, pool_address TEXT, feature_version INTEGER, feature_json TEXT)"
        )
        conn.commit()
    finally:
        conn.close()


def _insert_case(path: Path, *, case_key: str, open_at: float, with_features: bool = True) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "INSERT INTO listing_history_cases VALUES (?,?,?,?,?)",
            (case_key, "upbit", "KRW-TEST", "TEST", open_at),
        )
        if with_features:
            asset_key = case_key + "|eth|0xtest"
            pool_address = "0xpool" + case_key[-1]
            feature = {
                "pool_quality": {"passed": True},
                "domestic_listing_window": {
                    "status": "collected",
                    "pre": {
                        "t1h": {"return_to_domestic_open_pct": 8.0},
                        "t6h": {"return_to_domestic_open_pct": 12.0},
                        "t1d": {"return_to_domestic_open_pct": 20.0},
                        "t3d": {"return_to_domestic_open_pct": 30.0},
                        "t7d": {"return_to_domestic_open_pct": 50.0},
                    },
                    "post": {
                        "p1h": {"return_from_domestic_open_pct": 2.0},
                        "p6h": {"return_from_domestic_open_pct": -1.0},
                        "p24h": {"return_from_domestic_open_pct": 4.0},
                    },
                },
            }
            conn.execute("INSERT INTO dex_launch_assets VALUES (?,?,?)", (case_key, asset_key, "eth"))
            conn.execute(
                "INSERT INTO dex_launch_pools VALUES (?,?,?,?,?,?)",
                (asset_key, pool_address, "uniswap_v3", open_at - 86400.0, "accepted", 1),
            )
            conn.execute(
                "INSERT INTO dex_launch_features VALUES (?,?,?,?)",
                (asset_key, pool_address, 1, json.dumps(feature)),
            )
        conn.commit()
    finally:
        conn.close()


def test_build66_scores_only_forward_cases_and_excludes_historical(tmp_path: Path) -> None:
    db = tmp_path / "research.sqlite"
    _init_db(db)
    old_case = "upbit|KRW-OLD|notice:1"
    new_case = "upbit|KRW-NEW|notice:2"
    _insert_case(db, case_key=old_case, open_at=FORWARD_CUTOFF_TS - 60.0, with_features=False)
    _insert_case(db, case_key=new_case, open_at=FORWARD_CUTOFF_TS + 60.0, with_features=True)

    def quality(_: Path | str) -> dict:
        return {
            "cases": [
                {"case_key": old_case, "coingecko_id": "old", "usable_for_shadow_analysis": True},
                {"case_key": new_case, "coingecko_id": "new", "usable_for_shadow_analysis": True},
            ]
        }

    result = audit_dex_shadow_score_v2_forward(db, preregistration_fn=_ready_prereg, quality_fn=quality)
    assert result["ok"] is True
    assert result["status"] == "scored_forward_only"
    assert result["pre_cutoff_design_only_case_count"] == 1
    assert result["forward_eligible_case_count"] == 1
    assert result["case_score_count"] == 1
    assert result["historical_rows_scored_as_v2"] is False
    assert result["historical_rows_eligible_for_v2_validation"] is False
    row = result["case_scores"][0]
    assert row["case_key"] == new_case
    assert row["forward_eligible"] is True
    assert row["shadow_score"] < 50.0
    assert set(row["components"]) == {"pre_short_exhaustion", "pre_medium_exhaustion"}
    assert row["components"]["pre_short_exhaustion"]["signal"] < 0.0
    assert "pre_acceleration" not in row["components"]
    assert "launch_continuity" not in row["components"]
    assert result["can_place_orders"] is False
    assert result["paper_ab_wired"] is False


def test_build66_waits_cleanly_when_no_forward_case_exists(tmp_path: Path) -> None:
    db = tmp_path / "research.sqlite"
    _init_db(db)
    old_case = "bithumb|KRW-OLD|notice:3"
    _insert_case(db, case_key=old_case, open_at=FORWARD_CUTOFF_TS - 1.0, with_features=False)

    def quality(_: Path | str) -> dict:
        return {"cases": [{"case_key": old_case, "coingecko_id": "old", "usable_for_shadow_analysis": True}]}

    result = audit_dex_shadow_score_v2_forward(db, preregistration_fn=_ready_prereg, quality_fn=quality)
    assert result["ok"] is True
    assert result["status"] == "forward_waiting_no_eligible_cases"
    assert result["pre_cutoff_design_only_case_count"] == 1
    assert result["forward_eligible_case_count"] == 0
    assert result["case_score_count"] == 0
    assert result["historical_rows_scored_as_v2"] is False
    assert result["review"]["build67_forward_validation_allowed"] is False


def test_build66_fails_closed_without_build65_preregistration(tmp_path: Path) -> None:
    def blocked(_: Path | str) -> dict:
        return {
            "ok": False,
            "status": "v1_retirement_blocked",
            "v1": {"retired": False},
            "review": {"build66_forward_scorer_allowed": False},
        }

    result = audit_dex_shadow_score_v2_forward(tmp_path / "missing.sqlite", preregistration_fn=blocked)
    assert result["ok"] is False
    assert result["status"] == "preregistration_blocked"
    assert result["case_score_count"] == 0
    assert result["historical_rows_scored_as_v2"] is False
    assert result["can_place_orders"] is False
