from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from b3_trader.dex_sample_audit import audit_dex_sample


def _seed(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE listing_history_cases (
          case_key TEXT PRIMARY KEY,
          domestic_exchange TEXT,
          domestic_market TEXT,
          symbol TEXT,
          identity_verified INTEGER,
          status TEXT
        );
        CREATE TABLE dex_launch_case_status (
          case_key TEXT PRIMARY KEY,
          coingecko_id TEXT,
          status TEXT,
          contract_count INTEGER,
          accepted_pool_count INTEGER,
          error TEXT,
          updated_at REAL
        );
        CREATE TABLE dex_launch_assets (
          asset_key TEXT PRIMARY KEY,
          case_key TEXT,
          coingecko_id TEXT,
          platform_id TEXT,
          network_id TEXT,
          token_address TEXT,
          identity_status TEXT,
          created_at REAL,
          updated_at REAL
        );
        CREATE TABLE dex_launch_pools (
          asset_key TEXT,
          pool_address TEXT,
          dex_id TEXT,
          pool_name TEXT,
          pool_created_at REAL,
          reserve_usd REAL,
          volume_h24_usd REAL,
          volume_h6_usd REAL,
          volume_h1_usd REAL,
          volume_m5_usd REAL,
          base_token_address TEXT,
          quote_token_address TEXT,
          gate_status TEXT,
          selected_primary INTEGER,
          updated_at REAL,
          PRIMARY KEY(asset_key,pool_address)
        );
        CREATE TABLE dex_launch_features (
          asset_key TEXT,
          pool_address TEXT,
          feature_version INTEGER,
          calculated_at REAL,
          feature_json TEXT,
          PRIMARY KEY(asset_key,pool_address)
        );
        """
    )
    cases = [
        ("bithumb|KRW-X|1", "bithumb", "KRW-X", "X", 1, "complete", "asset-x"),
        ("upbit|KRW-X|2", "upbit", "KRW-X", "X", 1, "complete", "asset-x"),
        ("bithumb|KRW-Y|3", "bithumb", "KRW-Y", "Y", 1, "source_waiting", "asset-y"),
    ]
    for index, (key, exchange, market, symbol, verified, status, cg) in enumerate(cases):
        conn.execute(
            "INSERT INTO listing_history_cases VALUES(?,?,?,?,?,?)",
            (key, exchange, market, symbol, verified, "complete"),
        )
        conn.execute(
            "INSERT INTO dex_launch_case_status VALUES(?,?,?,?,?,?,?)",
            (key, cg, status, 1, 1 if status == "complete" else 0, "", float(index + 1)),
        )
        if status == "complete":
            asset_key = f"{key}|eth|0x{index + 1}"
            conn.execute(
                "INSERT INTO dex_launch_assets VALUES(?,?,?,?,?,?,?,?,?)",
                (asset_key, key, cg, "ethereum", "eth", f"0x{index + 1}", "exact_contract_verified", 1.0, 1.0),
            )
            conn.execute(
                "INSERT INTO dex_launch_pools VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (asset_key, f"0xpool{index}", "dex", "pool", 0, 50000, 20000, 0, 0, 0, "", "", "accepted", 1, 1.0),
            )
            feature = {
                "domestic_listing_window": {"status": "collected", "p5m_exact_minute": True},
                "pool_launch_window": {"status": "collected" if index == 0 else "unavailable"},
                "pool_quality": {"passed": True},
            }
            conn.execute(
                "INSERT INTO dex_launch_features VALUES(?,?,?,?,?)",
                (asset_key, f"0xpool{index}", 1, 1.0, json.dumps(feature)),
            )
    conn.execute(
        "INSERT INTO listing_history_cases VALUES(?,?,?,?,?,?)",
        ("upbit|KRW-Z|4", "upbit", "KRW-Z", "Z", 1, "pending_identity"),
    )
    conn.commit()
    conn.close()


def test_audit_reports_unique_asset_duplicates_and_failures(tmp_path: Path) -> None:
    path = tmp_path / "audit.sqlite3"
    _seed(path)
    result = audit_dex_sample(path)
    assert result["ok"] is True
    assert result["advisory_only"] is True
    assert result["changes_build45_thresholds"] is False
    assert result["event_cases"]["usable"] == 2
    assert result["event_cases"]["unique_assets"] == 1
    assert result["event_cases"]["duplicate_event_cases"] == 1
    assert result["event_cases"]["unique_asset_ratio"] == 0.5
    assert result["exchange_distribution"]["counts"] == {"bithumb": 1, "upbit": 1}
    assert result["coverage"]["exact_p5m_cases"] == 2
    assert result["coverage"]["launch_feature_cases"] == 1
    assert result["not_usable_status_distribution"] == {"source_waiting": 1}
    assert result["remaining"]["verified_listing_cases_without_dex_status"] == 1
    assert result["duplicate_asset_groups"][0]["coingecko_id"] == "asset-x"
    assert result["review"]["do_not_enable_shadow_score_yet"] is True
