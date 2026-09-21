from __future__ import annotations

import sqlite3

import pytest

from b3_trader.intelligence_us_market_path_quality import assess_us_market_reference_path
from b3_trader.intelligence_us_market_reference import (
    UsMarketReferenceStore,
    normalize_us_market_reference_observation,
)

SOURCE_ID = "us_sp500"
PROVIDER_ID = "massive_indices_1m"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _seed(
    conn: sqlite3.Connection,
    times: list[float],
    *,
    latency_class: str = "realtime",
    delayed_seconds: float | None = 0.0,
) -> None:
    store = UsMarketReferenceStore(conn)
    observations = [
        normalize_us_market_reference_observation(
            source_id=SOURCE_ID,
            observed_at=ts,
            received_at=ts + 1,
            value=5000.0 + index,
            provider_id=PROVIDER_ID,
            provider_url="https://api.massive.com/v2/aggs/ticker/I:SPX/range/1/minute/x/y",
            data_rights="provider_subscription_indices_advanced_internal_research_only",
            session_state="unknown",
            latency_class=latency_class,
            delayed_seconds=delayed_seconds,
            attributes={"bar_timespan": "1m"},
        )
        for index, ts in enumerate(times)
    ]
    store.ingest(observations, seen_at=max(times) + 10)


def test_dense_one_minute_path_is_pairing_eligible() -> None:
    conn = _conn()
    times = [1000.0 + 60.0 * index for index in range(16)]
    _seed(conn, times)
    result = assess_us_market_reference_path(
        conn,
        source_id=SOURCE_ID,
        provider_id=PROVIDER_ID,
        start_at=1000.0,
        end_at=1900.0,
    )
    assert result["status"] == "ok"
    assert result["eligible_for_pairing"] is True
    assert result["observation_count"] == 16
    assert result["expected_count"] == 16
    assert result["coverage_ratio"] == pytest.approx(1.0)
    assert result["max_gap_seconds"] == pytest.approx(60.0)
    assert result["latency_classes"] == ["realtime"]
    assert result["data_rights_complete"] is True


def test_large_internal_gap_blocks_pairing_even_if_coverage_ratio_passes() -> None:
    conn = _conn()
    full = [1000.0 + 60.0 * index for index in range(16)]
    times = [ts for ts in full if ts not in {1300.0, 1360.0, 1420.0}]
    _seed(conn, times)
    result = assess_us_market_reference_path(
        conn,
        source_id=SOURCE_ID,
        provider_id=PROVIDER_ID,
        start_at=1000.0,
        end_at=1900.0,
    )
    assert result["coverage_ratio"] == pytest.approx(13 / 16)
    assert result["max_gap_seconds"] == pytest.approx(240.0)
    assert result["status"] == "gap_exceeded"
    assert result["eligible_for_pairing"] is False
    assert "gap_exceeded" in result["reasons"]


def test_low_coverage_blocks_pairing_without_synthetic_fill() -> None:
    conn = _conn()
    times = [1000.0, 1180.0, 1360.0, 1540.0, 1720.0, 1900.0]
    _seed(conn, times)
    result = assess_us_market_reference_path(
        conn,
        source_id=SOURCE_ID,
        provider_id=PROVIDER_ID,
        start_at=1000.0,
        end_at=1900.0,
    )
    assert result["observation_count"] == 6
    assert result["expected_count"] == 16
    assert result["coverage_ratio"] == pytest.approx(6 / 16)
    assert result["status"] == "insufficient_coverage"
    assert result["eligible_for_pairing"] is False


def test_mixed_latency_contract_blocks_pairing() -> None:
    conn = _conn()
    times = [1000.0 + 60.0 * index for index in range(16)]
    _seed(conn, times)
    conn.execute(
        """UPDATE research_us_market_reference
           SET latency_class='delayed', delayed_seconds=900
           WHERE observed_at=?""",
        (1480.0,),
    )
    conn.commit()
    result = assess_us_market_reference_path(
        conn,
        source_id=SOURCE_ID,
        provider_id=PROVIDER_ID,
        start_at=1000.0,
        end_at=1900.0,
    )
    assert result["eligible_for_pairing"] is False
    assert "mixed_or_missing_latency_class" in result["reasons"]
    assert "mixed_delay_contract" in result["reasons"]


def test_missing_data_rights_blocks_pairing() -> None:
    conn = _conn()
    times = [1000.0 + 60.0 * index for index in range(16)]
    _seed(conn, times)
    conn.execute(
        "UPDATE research_us_market_reference SET data_rights='' WHERE observed_at=?",
        (1480.0,),
    )
    conn.commit()
    result = assess_us_market_reference_path(
        conn,
        source_id=SOURCE_ID,
        provider_id=PROVIDER_ID,
        start_at=1000.0,
        end_at=1900.0,
    )
    assert result["status"] == "missing_data_rights"
    assert result["eligible_for_pairing"] is False


def test_missing_end_endpoint_fails_closed() -> None:
    conn = _conn()
    _seed(conn, [1000.0 + 60.0 * index for index in range(5)])
    result = assess_us_market_reference_path(
        conn,
        source_id=SOURCE_ID,
        provider_id=PROVIDER_ID,
        start_at=1000.0,
        end_at=1900.0,
    )
    assert result["status"] == "endpoint_missing"
    assert result["eligible_for_pairing"] is False
    assert result["reasons"] == ["end_endpoint_missing"]


def test_quality_thresholds_are_configurable_but_validated() -> None:
    conn = _conn()
    with pytest.raises(ValueError, match="min_coverage_ratio"):
        assess_us_market_reference_path(
            conn,
            source_id=SOURCE_ID,
            provider_id=PROVIDER_ID,
            start_at=1000.0,
            end_at=1900.0,
            min_coverage_ratio=1.1,
        )
    with pytest.raises(ValueError, match="max_gap_seconds"):
        assess_us_market_reference_path(
            conn,
            source_id=SOURCE_ID,
            provider_id=PROVIDER_ID,
            start_at=1000.0,
            end_at=1900.0,
            max_gap_seconds=30.0,
        )
