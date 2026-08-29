from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from b3_trader.dex_shadow_readiness_audit import audit_dex_shadow_readiness


def _feature(*, exact: bool, launch: bool) -> str:
    return json.dumps(
        {
            "domestic_listing_window": {"status": "collected", "p5m_exact_minute": exact},
            "pool_launch_window": {"status": "collected" if launch else "not_available"},
            "pool_quality": {"passed": True},
        }
    )


def _seed_sample(path: Path, *, launch_cases: int) -> None:
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

    base_ts = 1_700_000_000.0
    for i in range(20):
        case_key = f"bithumb|KRW-T{i}|notice:{i}" if i < 13 else f"upbit|KRW-T{i}|notice:{i}"
        exchange = "bithumb" if i < 13 else "upbit"
        asset_id = f"asset-{i}" if i < 16 else f"asset-{i - 16}"
        contract_count = 1 if i < 10 else 2
        asset_key = f"{case_key}|ethereum|0x{i:040x}"
        network = "eth" if i % 2 == 0 else "base"
        dex_id = "dex-a" if i % 2 == 0 else "dex-b"
        month_offset = (i % 5) * 31 * 86400
        open_at = base_ts + month_offset

        conn.execute(
            "INSERT INTO listing_history_cases VALUES(?,?,?,?,?,?,?,?,?)",
            (case_key, exchange, f"KRW-T{i}", f"T{i}", open_at, "{}", 1, "complete", open_at),
        )
        conn.execute(
            "INSERT INTO dex_launch_case_status VALUES(?,?,?,?,?,?,?)",
            (case_key, asset_id, "complete", contract_count, 1, "", open_at),
        )
        conn.execute(
            "INSERT INTO dex_launch_assets VALUES(?,?,?,?,?,?,?,?,?)",
            (asset_key, case_key, asset_id, "ethereum", network, f"0x{i:040x}", "exact_contract_verified", open_at, open_at),
        )
        conn.execute(
            "INSERT INTO dex_launch_pools VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                asset_key,
                f"0x{i + 100:040x}",
                dex_id,
                "T / USD",
                open_at - 86400,
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
            (asset_key, f"0x{i + 100:040x}", 3, open_at, _feature(exact=i < 18, launch=i < launch_cases)),
        )

    conn.commit()
    conn.close()


def test_build53_blocks_low_launch_feature_coverage(tmp_path: Path) -> None:
    db = tmp_path / "sample.sqlite3"
    _seed_sample(db, launch_cases=3)
    result = audit_dex_shadow_readiness(db)

    assert result["ok"] is True
    assert result["paper_only"] is True
    assert result["can_place_orders"] is False
    assert result["score_wired"] is False
    assert result["changes_build45_thresholds"] is False
    assert result["metrics"]["build45_sample_ready"] is True
    assert result["metrics"]["unique_asset_ratio"] == 0.8
    assert result["metrics"]["exact_p5m_coverage"] == 0.9
    assert result["metrics"]["launch_feature_coverage"] == 0.15
    assert result["shadow_readiness_advisory"] is False
    assert any(reason.startswith("launch_feature_coverage_below_min:") for reason in result["blocking_reasons"])


def test_build53_can_mark_balanced_sample_advisory_ready(tmp_path: Path) -> None:
    db = tmp_path / "ready.sqlite3"
    _seed_sample(db, launch_cases=6)
    result = audit_dex_shadow_readiness(db)

    assert result["metrics"]["build45_sample_ready"] is True
    assert result["metrics"]["launch_feature_coverage"] == 0.3
    assert result["metrics"]["max_exchange_share"] == 0.65
    assert result["metrics"]["complete_partial_ratio"] == 0.5
    assert result["shadow_readiness_advisory"] is True
    assert result["blocking_reasons"] == []
    assert result["review"]["wire_shadow_score_now"] is False
