from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.intelligence_event_response import PROVIDER_ID
from b3_trader.phase5_event_response_check import run_check


def _create_response_table(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE research_intelligence_event_responses (
            event_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            exchange TEXT NOT NULL,
            market TEXT NOT NULL,
            horizon_label TEXT NOT NULL,
            horizon_seconds REAL NOT NULL,
            event_ts REAL NOT NULL,
            baseline_trade_ts REAL NOT NULL,
            baseline_price REAL NOT NULL,
            target_ts REAL NOT NULL,
            target_trade_ts REAL NOT NULL,
            target_price REAL NOT NULL,
            return_pct REAL NOT NULL,
            provider_id TEXT NOT NULL,
            data_rights TEXT NOT NULL,
            observation_tolerance_seconds REAL NOT NULL,
            captured_at REAL NOT NULL,
            attributes_json TEXT NOT NULL DEFAULT '{}',
            schema_version INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    return conn


def test_check_reports_waiting_when_table_has_no_samples(tmp_path: Path) -> None:
    path = tmp_path / "empty.sqlite3"
    conn = _create_response_table(path)
    conn.commit()
    conn.close()
    result, code = run_check(path=path)
    assert code == 1
    assert result["ok"] is False
    assert result["status"] == "waiting_for_observable_event"
    assert result["sample_count"] == 0


def test_check_accepts_point_in_time_sample_contract(tmp_path: Path) -> None:
    path = tmp_path / "ready.sqlite3"
    conn = _create_response_table(path)
    conn.execute(
        """INSERT INTO research_intelligence_event_responses(
               event_id,event_type,source_id,exchange,market,horizon_label,horizon_seconds,
               event_ts,baseline_trade_ts,baseline_price,target_ts,target_trade_ts,target_price,
               return_pct,provider_id,data_rights,observation_tolerance_seconds,captured_at,
               attributes_json,schema_version
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "evt",
            "US_CPI",
            "us_bls_release_calendar",
            "bithumb",
            "KRW-BTC",
            "15m",
            900.0,
            10000.0,
            9999.0,
            100.0,
            10900.0,
            10901.0,
            102.0,
            2.0,
            PROVIDER_ID,
            "public_exchange_market_data_internal_research",
            120.0,
            11000.0,
            "{}",
            1,
        ),
    )
    conn.commit()
    conn.close()

    result, code = run_check(path=path)
    assert code == 0
    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["sample_count"] == 1
    assert result["events_with_samples"] == 1
    assert result["horizon_counts"]["15m"] == 1


def test_check_rejects_forward_looking_baseline(tmp_path: Path) -> None:
    path = tmp_path / "invalid.sqlite3"
    conn = _create_response_table(path)
    conn.execute(
        """INSERT INTO research_intelligence_event_responses(
               event_id,event_type,source_id,exchange,market,horizon_label,horizon_seconds,
               event_ts,baseline_trade_ts,baseline_price,target_ts,target_trade_ts,target_price,
               return_pct,provider_id,data_rights,observation_tolerance_seconds,captured_at,
               attributes_json,schema_version
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "evt",
            "US_CPI",
            "us_bls_release_calendar",
            "bithumb",
            "KRW-BTC",
            "15m",
            900.0,
            10000.0,
            10001.0,
            100.0,
            10900.0,
            10901.0,
            102.0,
            2.0,
            PROVIDER_ID,
            "public_exchange_market_data_internal_research",
            120.0,
            11000.0,
            "{}",
            1,
        ),
    )
    conn.commit()
    conn.close()

    result, code = run_check(path=path)
    assert code == 2
    assert result["ok"] is False
    assert result["status"] == "contract_violation"
