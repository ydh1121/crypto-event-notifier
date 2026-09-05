from __future__ import annotations

import sqlite3

from b3_trader.intelligence_us_market_reference import (
    UsMarketReferenceStore,
    normalize_us_market_reference_observation,
)
from b3_trader.intelligence_us_market_sensitivity import IntelligenceUsMarketSensitivityStore

SOURCE_ID = "us_sp500"
PROVIDER_ID = "massive_indices_1m"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE research_intelligence_reactions (
            reaction_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            market TEXT NOT NULL,
            window TEXT NOT NULL,
            horizon_seconds INTEGER NOT NULL,
            anchor_at REAL NOT NULL,
            provider_id TEXT NOT NULL,
            exchange TEXT NOT NULL,
            forward_return_pct REAL NOT NULL
        )"""
    )
    conn.execute(
        """INSERT INTO research_intelligence_reactions(
            reaction_id,event_id,event_type,market,window,horizon_seconds,anchor_at,
            provider_id,exchange,forward_return_pct
        ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            "reaction-1",
            "event-1",
            "US_CPI",
            "KRW-BTC",
            "15m",
            900,
            1000.0,
            "upbit:public_rest:1m",
            "upbit",
            2.0,
        ),
    )
    conn.commit()
    return conn


def _reference(ts: float, value: float, *, provider: str = PROVIDER_ID):
    return normalize_us_market_reference_observation(
        source_id=SOURCE_ID,
        observed_at=ts,
        received_at=ts + 1,
        value=value,
        provider_id=provider,
        provider_url="https://api.massive.com/v2/aggs/ticker/I:SPX/range/1/minute/x/y",
        data_rights="provider_subscription_indices_advanced_internal_research_only",
        session_state="unknown",
        latency_class="realtime",
        delayed_seconds=0.0,
        attributes={"bar_timespan": "1m"},
    )


def test_dense_massive_1m_path_builds_pair() -> None:
    conn = _conn()
    observations = [
        _reference(1000.0 + 60.0 * index, 5000.0 + index)
        for index in range(16)
    ]
    UsMarketReferenceStore(conn).ingest(observations, seen_at=2000)
    store = IntelligenceUsMarketSensitivityStore(conn)
    result = store.build_pairs(
        source_ids=[SOURCE_ID],
        max_reference_skew_seconds=0,
        seen_at=2000,
    )
    assert result == {
        "reactions_considered": 1,
        "providers_considered": 1,
        "pairs_ready": 1,
        "inserted": 1,
        "updated": 0,
    }
    pair = conn.execute("SELECT * FROM research_intelligence_us_reference_pairs").fetchone()
    assert pair is not None
    assert pair["reference_provider_id"] == PROVIDER_ID
    assert pair["reference_start_at"] == 1000.0
    assert pair["reference_end_at"] == 1900.0


def test_sparse_massive_1m_path_is_rejected_with_reason_counts() -> None:
    conn = _conn()
    UsMarketReferenceStore(conn).ingest(
        [_reference(1000.0, 5000.0), _reference(1900.0, 5050.0)],
        seen_at=2000,
    )
    store = IntelligenceUsMarketSensitivityStore(conn)
    result = store.build_pairs(
        source_ids=[SOURCE_ID],
        max_reference_skew_seconds=0,
        seen_at=2000,
    )
    assert result["reactions_considered"] == 1
    assert result["providers_considered"] == 1
    assert result["pairs_ready"] == 0
    assert result["inserted"] == 0
    assert result["updated"] == 0
    assert result["quality_rejected"] == 1
    assert result["quality_rejection_reasons"] == {
        "gap_exceeded": 1,
        "insufficient_coverage": 1,
    }
    assert conn.execute("SELECT COUNT(*) FROM research_intelligence_us_reference_pairs").fetchone()[0] == 0


def test_legacy_endpoint_provider_remains_backward_compatible() -> None:
    conn = _conn()
    provider = "licensed_a"
    UsMarketReferenceStore(conn).ingest(
        [
            _reference(1000.0, 5000.0, provider=provider),
            _reference(1900.0, 5050.0, provider=provider),
        ],
        seen_at=2000,
    )
    store = IntelligenceUsMarketSensitivityStore(conn)
    result = store.build_pairs(
        source_ids=[SOURCE_ID],
        max_reference_skew_seconds=0,
        seen_at=2000,
    )
    assert result == {
        "reactions_considered": 1,
        "providers_considered": 1,
        "pairs_ready": 1,
        "inserted": 1,
        "updated": 0,
    }
