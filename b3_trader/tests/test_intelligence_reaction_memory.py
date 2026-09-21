from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from b3_trader.intelligence_event import normalize_intelligence_event
from b3_trader.intelligence_reaction import compute_event_reaction, normalize_reaction_price_observation
from b3_trader.intelligence_reaction_memory import IntelligenceReactionMemoryStore
from b3_trader.intelligence_reaction_store import IntelligenceReactionStore


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _event(external_id: str, published_at: float):
    return normalize_intelligence_event(
        source_id="us_sec_press_releases",
        source_family="official_news",
        event_type="US_SEC_POLICY",
        title=f"SEC fixture {external_id}",
        source_url=f"https://www.sec.gov/newsroom/press-releases/{external_id}",
        external_id=external_id,
        published_at=published_at,
        received_at=published_at + 5,
    )


def _price(ts: float, price: float, *, provider: str = "upbit_public_rest"):
    return normalize_reaction_price_observation(
        market="KRW-BTC",
        observed_at=ts,
        price=price,
        provider_id=provider,
        exchange="upbit",
        source="public_rest_1m_close",
        received_at=ts + 1,
        evidence={"fixture": True},
    )


def _reaction(external_id: str, anchor: float, end_price: float, *, provider: str = "upbit_public_rest"):
    event = _event(external_id, anchor)
    reaction = compute_event_reaction(
        event,
        market="KRW-BTC",
        window="15m",
        start=_price(anchor, 100.0, provider=provider),
        end=_price(anchor + 900, end_price, provider=provider),
    )
    assert reaction is not None
    return reaction


def test_refresh_builds_empirical_memory_without_confidence_weight() -> None:
    conn = _conn()
    reaction_store = IntelligenceReactionStore(conn)
    reaction_store.ingest(
        [
            _reaction("event-a", 1000, 110),
            _reaction("event-b", 3000, 90),
        ],
        seen_at=5000,
    )
    memory = IntelligenceReactionMemoryStore(conn)
    assert memory.refresh(now=6000) == {"source_rows": 2, "groups": 1}

    rows = memory.lookup(
        market="KRW-BTC",
        event_type="US_SEC_POLICY",
        window="15m",
        provider_id="upbit_public_rest",
        exchange="upbit",
        now=6000,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["sample_count"] == 2
    assert row["mean_return_pct"] == pytest.approx(0.0)
    assert row["median_return_pct"] == pytest.approx(0.0)
    assert row["stdev_return_pct"] == pytest.approx(10.0)
    assert row["positive_count"] == 1
    assert row["negative_count"] == 1
    assert row["zero_count"] == 0
    assert row["positive_rate_pct"] == pytest.approx(50.0)
    assert row["negative_rate_pct"] == pytest.approx(50.0)
    assert row["earliest_anchor_at"] == 1000
    assert row["latest_anchor_at"] == 3000
    assert row["recency_seconds"] == 3000
    assert row["confidence"] is None
    assert row["confidence_status"] == "not_promoted"


def test_memory_never_collapses_different_providers_into_one_group() -> None:
    conn = _conn()
    reaction_store = IntelligenceReactionStore(conn)
    reaction_store.ingest(
        [
            _reaction("event-a", 1000, 101, provider="provider_a"),
            _reaction("event-b", 3000, 102, provider="provider_b"),
        ],
        seen_at=5000,
    )
    memory = IntelligenceReactionMemoryStore(conn)
    assert memory.refresh(now=6000) == {"source_rows": 2, "groups": 2}
    rows = memory.lookup(market="KRW-BTC", event_type="US_SEC_POLICY", window="15m", now=6000)
    assert {row["provider_id"] for row in rows} == {"provider_a", "provider_b"}
    assert all(row["sample_count"] == 1 for row in rows)


def test_single_sample_has_zero_population_dispersion_and_preserves_delays() -> None:
    conn = _conn()
    event = _event("event-a", 1000)
    reaction = compute_event_reaction(
        event,
        market="KRW-BTC",
        window="1h",
        start=_price(1005, 100),
        end=_price(4610, 105),
        max_observation_delay_seconds=20,
    )
    assert reaction is not None
    IntelligenceReactionStore(conn).ingest([reaction], seen_at=5000)
    memory = IntelligenceReactionMemoryStore(conn)
    memory.refresh(now=6000)
    row = memory.lookup(market="KRW-BTC", window="1h", now=6000)[0]
    assert row["sample_count"] == 1
    assert row["stdev_return_pct"] == 0
    assert row["mean_start_delay_seconds"] == 5
    assert row["mean_end_delay_seconds"] == 10


def test_refresh_is_safe_when_raw_reaction_table_does_not_exist() -> None:
    memory = IntelligenceReactionMemoryStore(_conn())
    assert memory.refresh(now=1000) == {"source_rows": 0, "groups": 0}
    assert memory.lookup(market="KRW-BTC", now=1000) == []


def test_memory_layer_has_no_score_paper_decision_or_order_dependency() -> None:
    path = Path(__file__).resolve().parents[1] / "intelligence_reaction_memory.py"
    text = path.read_text(encoding="utf-8").casefold()
    assert "score_engine" not in text
    assert "paper_engine" not in text
    assert "order_executor" not in text
    assert "trading_decision" not in text
