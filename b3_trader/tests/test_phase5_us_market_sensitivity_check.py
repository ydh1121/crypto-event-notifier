from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.intelligence_event_response import PROVIDER_ID
from b3_trader.intelligence_us_market_sensitivity import UsMarketSensitivityAccumulator
from b3_trader.phase5_us_market_sensitivity_check import run_check


def _response_table(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE research_intelligence_event_responses(
               event_id TEXT NOT NULL,
               event_type TEXT NOT NULL,
               source_id TEXT NOT NULL,
               exchange TEXT NOT NULL,
               market TEXT NOT NULL,
               horizon_label TEXT NOT NULL,
               horizon_seconds REAL NOT NULL,
               event_ts REAL NOT NULL,
               return_pct REAL NOT NULL,
               provider_id TEXT NOT NULL
           )"""
    )
    return conn


def _insert_response(conn: sqlite3.Connection, *, event_id: str, value: float, ts: float) -> None:
    conn.execute(
        """INSERT INTO research_intelligence_event_responses(
               event_id,event_type,source_id,exchange,market,horizon_label,
               horizon_seconds,event_ts,return_pct,provider_id
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            event_id,
            "US_CPI",
            "us_bls_release_calendar",
            "bithumb",
            "KRW-BTC",
            "15m",
            900.0,
            ts,
            value,
            PROVIDER_ID,
        ),
    )


def test_check_waits_when_derived_table_has_no_samples(tmp_path: Path) -> None:
    path = tmp_path / "waiting.sqlite3"
    conn = _response_table(path)
    UsMarketSensitivityAccumulator(conn)
    conn.close()
    result, code = run_check(path=path)
    assert code == 1
    assert result["ok"] is False
    assert result["status"] == "waiting_for_event_response_samples"
    assert result["stats_rows"] == 0


def test_check_accepts_valid_descriptive_stats_contract(tmp_path: Path) -> None:
    path = tmp_path / "ready.sqlite3"
    conn = _response_table(path)
    _insert_response(conn, event_id="e1", value=1.0, ts=1000)
    _insert_response(conn, event_id="e2", value=-2.0, ts=2000)
    conn.commit()
    accumulator = UsMarketSensitivityAccumulator(conn)
    accumulator.run_once(now=3000)
    conn.close()

    result, code = run_check(path=path)
    assert code == 0
    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["stats_rows"] == 1
    assert result["samples_represented"] == 2
    assert result["event_types"] == ["US_CPI"]
    assert result["markets"] == ["bithumb:KRW-BTC"]
    assert result["horizons"] == ["15m"]
    assert result["readiness_counts"] == {"insufficient_sample": 1}


def test_check_rejects_stats_with_promoted_authority_flag(tmp_path: Path) -> None:
    path = tmp_path / "invalid.sqlite3"
    conn = _response_table(path)
    _insert_response(conn, event_id="e1", value=1.0, ts=1000)
    conn.commit()
    accumulator = UsMarketSensitivityAccumulator(conn)
    accumulator.run_once(now=2000)
    conn.execute(
        """UPDATE research_us_market_sensitivity_stats
           SET attributes_json='{"descriptive_only":true,"score_authority":true,"promotion_eligible":false,"missing_values_coerced_to_zero":false}'"""
    )
    conn.commit()
    conn.close()

    result, code = run_check(path=path)
    assert code == 2
    assert result["ok"] is False
    assert result["status"] == "contract_violation"
    assert any("score_authority_not_false" in item for item in result["violations"])
