from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from b3_trader.dex_shadow_remediation_plan import plan_dex_shadow_remediation


def _ts(year: int, month: int, day: int = 15) -> float:
    return datetime(year, month, day, tzinfo=timezone.utc).timestamp()


def _feature(*, exact: bool, launch_status: str) -> str:
    return json.dumps(
        {
            "domestic_listing_window": {"status": "collected", "p5m_exact_minute": exact},
            "pool_launch_window": {"status": launch_status},
            "pool_quality": {"passed": True},
        }
    )


def _seed(path: Path, now: float) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE listing_history_cases (
          case_key TEXT PRIMARY KEY,
          domestic_exchange TEXT NOT NULL,
          domestic_market TEXT NOT NULL,
          symbol TEXT NOT NULL,
          domestic_open_at REAL NOT NULL,
          identity_json TEXT NOT NULL DEFAULT '{}',
          identity_verified INTEGER NOT NULL,
          status TEXT NOT NULL,
          updated_at REAL NOT NULL
        );
        CREATE TABLE dex_launch_case_status (
          case_key TEXT PRIMARY KEY,
          coingecko_id TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          contract_count INTEGER NOT NULL DEFAULT 0,
          accepted_pool_count INTEGER NOT NULL DEFAULT 0,
          error TEXT NOT NULL DEFAULT '',
          updated_at REAL NOT NULL
        );
        CREATE TABLE dex_launch_assets (
          asset_key TEXT PRIMARY KEY,
          case_key TEXT NOT NULL,
          coingecko_id TEXT NOT NULL,
          platform_id TEXT NOT NULL,
          network_id TEXT NOT NULL DEFAULT '',
          token_address TEXT NOT NULL,
          identity_status TEXT NOT NULL,
          created_at REAL NOT NULL,
          updated_at REAL NOT NULL
        );
        CREATE TABLE dex_launch_pools (
          asset_key TEXT NOT NULL,
          pool_address TEXT NOT NULL,
          dex_id TEXT NOT NULL DEFAULT '',
          pool_name TEXT NOT NULL DEFAULT '',
          pool_created_at REAL NOT NULL DEFAULT 0,
          reserve_usd REAL NOT NULL DEFAULT 0,
          volume_h24_usd REAL NOT NULL DEFAULT 0,
          volume_h6_usd REAL NOT NULL DEFAULT 0,
          volume_h1_usd REAL NOT NULL DEFAULT 0,
          volume_m5_usd REAL NOT NULL DEFAULT 0,
          base_token_address TEXT NOT NULL DEFAULT '',
          quote_token_address TEXT NOT NULL DEFAULT '',
          gate_status TEXT NOT NULL DEFAULT 'accepted',
          selected_primary INTEGER NOT NULL DEFAULT 0,
          updated_at REAL NOT NULL,
          PRIMARY KEY(asset_key,pool_address)
        );
        CREATE TABLE dex_launch_features (
          asset_key TEXT NOT NULL,
          pool_address TEXT NOT NULL,
          feature_version INTEGER NOT NULL,
          calculated_at REAL NOT NULL,
          feature_json TEXT NOT NULL DEFAULT '{}',
          PRIMARY KEY(asset_key,pool_address)
        );
        """
    )

    for i in range(20):
        exchange = "bithumb" if i < 13 else "upbit"
        case_key = f"{exchange}|KRW-T{i}|notice:{i}"
        asset_id = f"asset-{i}" if i < 16 else f"asset-{i - 16}"
        open_at = _ts(2026, 8) if i < 12 else _ts(2026, 7)
        asset_key = f"{case_key}|ethereum|0x{i:040x}"
        pool_address = f"0x{i + 100:040x}"
        launch_status = "collected" if i < 3 else "launch_ohlcv_unavailable"
        if i in {3, 4}:
            pool_created_at = now - 10 * 86400
        elif i >= 5:
            pool_created_at = now - 200 * 86400
        else:
            pool_created_at = now - 20 * 86400

        conn.execute(
            "INSERT INTO listing_history_cases VALUES(?,?,?,?,?,?,?,?,?)",
            (case_key, exchange, f"KRW-T{i}", f"T{i}", open_at, "{}", 1, "complete", open_at),
        )
        conn.execute(
            "INSERT INTO dex_launch_case_status VALUES(?,?,?,?,?,?,?)",
            (case_key, asset_id, "complete", 1, 1, "", open_at),
        )
        conn.execute(
            "INSERT INTO dex_launch_assets VALUES(?,?,?,?,?,?,?,?,?)",
            (
                asset_key,
                case_key,
                asset_id,
                "ethereum",
                "eth" if i % 2 == 0 else "base",
                f"0x{i:040x}",
                "exact_contract_verified",
                open_at,
                open_at,
            ),
        )
        conn.execute(
            "INSERT INTO dex_launch_pools VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                asset_key,
                pool_address,
                "dex-a" if i % 2 == 0 else "dex-b",
                "T / USD",
                pool_created_at,
                100000.0,
                50000.0,
                10000.0,
                2000.0,
                500.0,
                f"0x{i:040x}",
                f"0x{i + 200:040x}",
                "accepted",
                1,
                open_at,
            ),
        )
        conn.execute(
            "INSERT INTO dex_launch_features VALUES(?,?,?,?,?)",
            (asset_key, pool_address, 1, open_at, _feature(exact=i < 18, launch_status=launch_status)),
        )

    for j, month in enumerate((7, 6), start=100):
        case_key = f"bithumb|KRW-B{j}|notice:{j}"
        open_at = _ts(2026, month)
        conn.execute(
            "INSERT INTO listing_history_cases VALUES(?,?,?,?,?,?,?,?,?)",
            (case_key, "bithumb", f"KRW-B{j}", f"B{j}", open_at, "{}", 1, "complete", open_at),
        )

    conn.commit()
    conn.close()


def test_build54_quantifies_temporal_and_launch_remediation(tmp_path: Path) -> None:
    db = tmp_path / "sample.sqlite3"
    now = _ts(2026, 8, 29)
    _seed(db, now)

    result = plan_dex_shadow_remediation(db, now=now)

    assert result["ok"] is True
    assert result["paper_only"] is True
    assert result["can_place_orders"] is False
    assert result["score_wired"] is False
    assert result["readiness"]["shadow_readiness_advisory"] is False
    assert result["recommended_next_action"] == "historical_expansion_plus_launch_recovery"

    temporal = result["temporal_remediation"]
    assert temporal["dominant_month"] == "2026-08"
    assert temporal["dominant_month_cases"] == 12
    assert temporal["minimum_target_usable_cases"] == 30
    assert temporal["additional_non_dominant_usable_cases_needed"] == 10
    assert temporal["per_month_case_cap_at_target"] == 12
    assert temporal["existing_month_additional_capacity_at_target"]["2026-07"] == 4
    assert temporal["existing_month_additional_capacity_at_target"]["2026-08"] == 0
    assert temporal["known_non_dominant_backlog_cases"] == 2
    assert temporal["historical_expansion_likely_required"] is True

    launch = result["launch_remediation"]
    assert launch["current_launch_feature_cases"] == 3
    assert launch["current_required_launch_cases"] == 6
    assert launch["additional_launch_cases_needed_current_sample"] == 3
    assert launch["required_launch_cases_at_temporal_target"] == 9
    assert launch["additional_launch_cases_needed_at_temporal_target"] == 6
    assert launch["recoverable_existing_cases"] == 2
    assert launch["remaining_launch_cases_needed_after_full_existing_recovery"] == 4
    assert launch["missing_launch_case_classification"] == {
        "collected": 3,
        "history_window_expired": 15,
        "recoverable_recent": 2,
    }
    assert result["review"]["wire_shadow_score_now"] is False
