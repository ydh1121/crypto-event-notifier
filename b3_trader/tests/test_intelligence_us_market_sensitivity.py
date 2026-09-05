from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from b3_trader.intelligence_event_response import PROVIDER_ID
from b3_trader.intelligence_us_market_sensitivity import (
    MIN_DESCRIPTIVE_SAMPLES,
    MIN_EXPLORATORY_SAMPLES,
    UsMarketSensitivityAccumulator,
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
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


def _response(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    return_pct: float,
    event_ts: float,
    event_type: str = "US_CPI",
    exchange: str = "bithumb",
    market: str = "KRW-BTC",
    horizon_label: str = "15m",
    horizon_seconds: float = 900.0,
) -> None:
    conn.execute(
        """INSERT INTO research_intelligence_event_responses(
               event_id,event_type,source_id,exchange,market,horizon_label,
               horizon_seconds,event_ts,return_pct,provider_id
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            event_id,
            event_type,
            "us_bls_release_calendar",
            exchange,
            market,
            horizon_label,
            horizon_seconds,
            event_ts,
            return_pct,
            PROVIDER_ID,
        ),
    )
    conn.commit()


def test_waiting_state_preserves_missing_semantics() -> None:
    conn = _conn()
    accumulator = UsMarketSensitivityAccumulator(conn)
    result = accumulator.run_once(now=1000)
    assert result["ok"] is True
    assert result["status"] == "waiting_for_event_response_samples"
    assert result["samples_considered"] == 0
    assert accumulator.recent() == []


def test_aggregates_descriptive_statistics_without_score_authority() -> None:
    conn = _conn()
    _response(conn, event_id="e1", return_pct=1.0, event_ts=1000)
    _response(conn, event_id="e2", return_pct=-2.0, event_ts=2000)
    _response(conn, event_id="e3", return_pct=3.0, event_ts=3000)
    accumulator = UsMarketSensitivityAccumulator(conn)

    result = accumulator.run_once(now=4000)
    assert result["status"] == "ok"
    assert result["samples_considered"] == 3
    assert result["groups_written"] == 1
    assert result["readiness_counts"]["insufficient_sample"] == 1

    row = accumulator.recent(limit=1)[0]
    assert row["sample_count"] == 3
    assert row["distinct_event_count"] == 3
    assert row["positive_count"] == 2
    assert row["negative_count"] == 1
    assert row["flat_count"] == 0
    assert row["positive_rate_pct"] == pytest.approx(200.0 / 3.0)
    assert row["mean_return_pct"] == pytest.approx(2.0 / 3.0)
    assert row["median_return_pct"] == pytest.approx(1.0)
    assert row["mean_abs_return_pct"] == pytest.approx(2.0)
    assert row["stddev_return_pct"] == pytest.approx(2.516611478423583)
    assert row["min_return_pct"] == pytest.approx(-2.0)
    assert row["max_return_pct"] == pytest.approx(3.0)
    assert row["readiness"] == "insufficient_sample"
    assert row["attributes"]["descriptive_only"] is True
    assert row["attributes"]["score_authority"] is False
    assert row["attributes"]["promotion_eligible"] is False
    assert row["attributes"]["missing_values_coerced_to_zero"] is False


def test_groups_are_separated_by_market_horizon_and_event_type() -> None:
    conn = _conn()
    _response(conn, event_id="cpi-btc", return_pct=1.0, event_ts=1000)
    _response(
        conn,
        event_id="cpi-eth",
        return_pct=2.0,
        event_ts=1000,
        market="KRW-ETH",
    )
    _response(
        conn,
        event_id="cpi-btc-1h",
        return_pct=3.0,
        event_ts=1000,
        horizon_label="1h",
        horizon_seconds=3600,
    )
    _response(
        conn,
        event_id="employment-btc",
        return_pct=-1.0,
        event_ts=2000,
        event_type="US_EMPLOYMENT",
    )
    accumulator = UsMarketSensitivityAccumulator(conn)
    result = accumulator.run_once(now=3000)
    assert result["groups_written"] == 4
    rows = accumulator.recent(limit=10)
    keys = {
        (row["event_type"], row["market"], row["horizon_label"])
        for row in rows
    }
    assert keys == {
        ("US_CPI", "KRW-BTC", "15m"),
        ("US_CPI", "KRW-ETH", "15m"),
        ("US_CPI", "KRW-BTC", "1h"),
        ("US_EMPLOYMENT", "KRW-BTC", "15m"),
    }


def test_readiness_thresholds_are_explicit_and_descriptive_only() -> None:
    assert MIN_EXPLORATORY_SAMPLES == 5
    assert MIN_DESCRIPTIVE_SAMPLES == 20
    assert UsMarketSensitivityAccumulator.readiness_for(4) == "insufficient_sample"
    assert UsMarketSensitivityAccumulator.readiness_for(5) == "exploratory"
    assert UsMarketSensitivityAccumulator.readiness_for(19) == "exploratory"
    assert UsMarketSensitivityAccumulator.readiness_for(20) == "descriptive_ready"


def test_recompute_is_idempotent_and_replaces_derived_snapshot() -> None:
    conn = _conn()
    _response(conn, event_id="e1", return_pct=1.0, event_ts=1000)
    accumulator = UsMarketSensitivityAccumulator(conn)
    first = accumulator.run_once(now=2000)
    second = accumulator.run_once(now=2100)
    assert first["groups_written"] == 1
    assert second["groups_written"] == 1
    assert len(accumulator.recent()) == 1
    assert accumulator.recent()[0]["calculated_at"] == pytest.approx(2100)


def test_invalid_response_row_fails_closed_without_zero_coercion() -> None:
    conn = _conn()
    _response(conn, event_id="valid", return_pct=1.0, event_ts=1000)
    accumulator = UsMarketSensitivityAccumulator(conn)
    assert accumulator.run_once(now=2000)["status"] == "ok"
    conn.execute(
        """INSERT INTO research_intelligence_event_responses(
               event_id,event_type,source_id,exchange,market,horizon_label,
               horizon_seconds,event_ts,return_pct,provider_id
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            "invalid",
            "US_CPI",
            "us_bls_release_calendar",
            "bithumb",
            "KRW-BTC",
            "15m",
            900.0,
            2000.0,
            float("inf"),
            PROVIDER_ID,
        ),
    )
    conn.commit()
    result = accumulator.run_once(now=3000)
    assert result["ok"] is False
    assert result["status"] == "invalid_event_response_rows"
    assert result["invalid_rows"] == 1
    assert accumulator.recent()[0]["sample_count"] == 1


def test_sensitivity_module_has_no_trading_authority_dependency() -> None:
    path = Path(__file__).resolve().parents[1] / "intelligence_us_market_sensitivity.py"
    text = path.read_text(encoding="utf-8").casefold()
    assert "score_engine" not in text
    assert "paper_engine" not in text
    assert "order_executor" not in text
    assert "trading_decision" not in text
