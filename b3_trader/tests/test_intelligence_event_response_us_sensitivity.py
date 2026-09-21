from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from b3_trader.intelligence_event_response import PROVIDER_ID as EVENT_RESPONSE_PROVIDER_ID
from b3_trader.intelligence_event_response_us_sensitivity import (
    IntelligenceEventResponseUsSensitivityStore,
)
from b3_trader.intelligence_us_market_reference import (
    UsMarketReferenceStore,
    normalize_us_market_reference_observation,
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
               target_ts REAL NOT NULL,
               return_pct REAL NOT NULL,
               provider_id TEXT NOT NULL
           )"""
    )
    return conn


def _response(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    event_ts: float,
    return_pct: float,
    exchange: str = "bithumb",
    market: str = "KRW-BTC",
    event_type: str = "US_CPI",
    source_id: str = "us_bls_release_calendar",
    horizon_label: str = "15m",
    horizon_seconds: float = 900.0,
) -> None:
    conn.execute(
        """INSERT INTO research_intelligence_event_responses(
               event_id,event_type,source_id,exchange,market,horizon_label,horizon_seconds,
               event_ts,target_ts,return_pct,provider_id
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            event_id,
            event_type,
            source_id,
            exchange,
            market,
            horizon_label,
            horizon_seconds,
            event_ts,
            event_ts + horizon_seconds,
            return_pct,
            EVENT_RESPONSE_PROVIDER_ID,
        ),
    )
    conn.commit()


def _reference(*, ts: float, value: float, source_id: str = "us_sp500"):
    return normalize_us_market_reference_observation(
        source_id=source_id,
        observed_at=ts,
        received_at=ts + 1,
        value=value,
        provider_id="licensed_fixture",
        provider_url="https://data.example.com/reference",
        data_rights="research-use fixture",
        session_state="regular",
        latency_class="delayed",
        delayed_seconds=15,
    )


def _reference_window(
    conn: sqlite3.Connection,
    *,
    event_ts: float,
    horizon_seconds: float,
    return_pct: float,
    source_id: str = "us_sp500",
) -> None:
    UsMarketReferenceStore(conn).ingest(
        [
            _reference(ts=event_ts, value=100.0, source_id=source_id),
            _reference(
                ts=event_ts + horizon_seconds,
                value=100.0 * (1.0 + return_pct / 100.0),
                source_id=source_id,
            ),
        ],
        seen_at=event_ts + horizon_seconds + 1,
    )


def test_same_event_preserves_exchange_and_market_response_identity() -> None:
    conn = _conn()
    _response(conn, event_id="cpi-a", event_ts=1000, return_pct=1.0, exchange="bithumb")
    _response(conn, event_id="cpi-a", event_ts=1000, return_pct=2.0, exchange="upbit")
    _reference_window(conn, event_ts=1000, horizon_seconds=900, return_pct=0.5)

    store = IntelligenceEventResponseUsSensitivityStore(conn)
    result = store.run(source_ids=["us_sp500"], max_reference_skew_seconds=0, now=2000)

    assert result["ok"] is True
    assert result["pairs"]["responses_considered"] == 2
    assert result["pairs"]["pairs_ready"] == 2
    assert result["sensitivity"] == {"source_pairs": 2, "groups": 2}
    pairs = conn.execute(
        "SELECT response_id,exchange,market,coin_provider_id FROM research_intelligence_event_response_us_pairs ORDER BY exchange"
    ).fetchall()
    assert len({row["response_id"] for row in pairs}) == 2
    assert {row["exchange"] for row in pairs} == {"bithumb", "upbit"}
    assert {row["market"] for row in pairs} == {"KRW-BTC"}
    assert {row["coin_provider_id"] for row in pairs} == {EVENT_RESPONSE_PROVIDER_ID}


def test_missing_reference_target_stays_missing_and_never_becomes_zero() -> None:
    conn = _conn()
    _response(conn, event_id="cpi-a", event_ts=1000, return_pct=1.0)
    UsMarketReferenceStore(conn).ingest(
        [_reference(ts=1000, value=100.0)],
        seen_at=1001,
    )

    store = IntelligenceEventResponseUsSensitivityStore(conn)
    result = store.run(source_ids=["us_sp500"], max_reference_skew_seconds=0, now=2000)

    assert result["pairs"]["responses_considered"] == 1
    assert result["pairs"]["pairs_ready"] == 0
    assert result["pairs"]["missing_reference_end"] == 1
    assert result["missing_values_coerced_to_zero"] is False
    assert conn.execute(
        "SELECT COUNT(*) FROM research_intelligence_event_response_us_pairs"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM research_intelligence_event_response_us_sensitivity"
    ).fetchone()[0] == 0


def test_strict_samples_produce_descriptive_beta_and_correlation() -> None:
    conn = _conn()
    for event_id, event_ts, coin_return, reference_return in (
        ("cpi-a", 1000, 2.0, 1.0),
        ("cpi-b", 3000, 4.0, 2.0),
        ("cpi-c", 5000, 6.0, 3.0),
    ):
        _response(conn, event_id=event_id, event_ts=event_ts, return_pct=coin_return)
        _reference_window(
            conn,
            event_ts=event_ts,
            horizon_seconds=900,
            return_pct=reference_return,
        )

    store = IntelligenceEventResponseUsSensitivityStore(conn)
    result = store.run(source_ids=["us_sp500"], max_reference_skew_seconds=0, now=7000)
    assert result["pairs"]["pairs_ready"] == 3
    rows = store.sensitivity(
        market="KRW-BTC",
        exchange="bithumb",
        event_type="US_CPI",
        horizon_label="15m",
        reference_source_id="us_sp500",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["sample_count"] == 3
    assert row["distinct_event_count"] == 3
    assert row["beta"] == pytest.approx(2.0)
    assert row["correlation"] == pytest.approx(1.0)
    assert row["same_direction_rate_pct"] == pytest.approx(100.0)
    assert row["readiness"] == "insufficient_sample"
    assert row["score_authority"] is False
    assert row["promotion_eligible"] is False
    assert row["confidence"] is None
    assert row["confidence_status"] == "not_promoted"


def test_vix_is_raw_and_not_direction_inverted() -> None:
    conn = _conn()
    _response(conn, event_id="sec-a", event_ts=1000, return_pct=5.0, event_type="US_SEC_POLICY", source_id="us_sec_press_releases")
    _reference_window(
        conn,
        event_ts=1000,
        horizon_seconds=900,
        return_pct=10.0,
        source_id="us_cboe_vix",
    )
    store = IntelligenceEventResponseUsSensitivityStore(conn)
    store.run(source_ids=["us_cboe_vix"], max_reference_skew_seconds=0, now=2000)
    pair = conn.execute(
        "SELECT reference_series,reference_return_pct FROM research_intelligence_event_response_us_pairs"
    ).fetchone()
    assert pair is not None
    assert pair["reference_series"] == "VIX"
    assert pair["reference_return_pct"] == pytest.approx(10.0)
    row = store.sensitivity(market="KRW-BTC", reference_source_id="us_cboe_vix")[0]
    assert row["reference_direction_semantics"] == "raw_not_inverted"


def test_strict_sensitivity_layer_has_no_score_paper_decision_or_order_dependency() -> None:
    path = Path(__file__).resolve().parents[1] / "intelligence_event_response_us_sensitivity.py"
    text = path.read_text(encoding="utf-8").casefold()
    assert "score_engine" not in text
    assert "paper_engine" not in text
    assert "order_executor" not in text
    assert "trading_decision" not in text
