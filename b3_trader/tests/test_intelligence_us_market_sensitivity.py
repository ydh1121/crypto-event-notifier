from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from b3_trader.intelligence_event import normalize_intelligence_event
from b3_trader.intelligence_reaction import compute_event_reaction, normalize_reaction_price_observation
from b3_trader.intelligence_reaction_store import IntelligenceReactionStore
from b3_trader.intelligence_us_market_reference import (
    UsMarketReferenceStore,
    normalize_us_market_reference_observation,
)
from b3_trader.intelligence_us_market_sensitivity import IntelligenceUsMarketSensitivityStore


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _reaction(external_id: str, anchor: float, coin_return_pct: float):
    event = normalize_intelligence_event(
        source_id="us_sec_press_releases",
        source_family="official_news",
        event_type="US_SEC_POLICY",
        title=f"fixture {external_id}",
        source_url=f"https://www.sec.gov/newsroom/press-releases/{external_id}",
        external_id=external_id,
        published_at=anchor,
        received_at=anchor + 1,
    )
    start = normalize_reaction_price_observation(
        market="KRW-BTC",
        observed_at=anchor,
        price=100.0,
        provider_id="upbit:public_rest:1m",
        exchange="upbit",
        source="public_rest",
        received_at=anchor + 1,
    )
    end = normalize_reaction_price_observation(
        market="KRW-BTC",
        observed_at=anchor + 900,
        price=100.0 * (1.0 + coin_return_pct / 100.0),
        provider_id="upbit:public_rest:1m",
        exchange="upbit",
        source="public_rest",
        received_at=anchor + 901,
    )
    reaction = compute_event_reaction(event, market="KRW-BTC", window="15m", start=start, end=end)
    assert reaction is not None
    return reaction


def _reference(
    *,
    source_id: str,
    ts: float,
    value: float,
    provider: str = "licensed_a",
    session: str = "regular",
):
    return normalize_us_market_reference_observation(
        source_id=source_id,
        observed_at=ts,
        received_at=ts + 2,
        value=value,
        provider_id=provider,
        provider_url="https://data.example.com/reference",
        data_rights="research-use fixture",
        session_state=session,
        latency_class="delayed",
        delayed_seconds=15,
    )


def test_event_conditioned_sp500_pairs_produce_empirical_beta_and_correlation() -> None:
    conn = _conn()
    reactions = [
        _reaction("event-a", 1000, 2.0),
        _reaction("event-b", 3000, 4.0),
        _reaction("event-c", 5000, 6.0),
    ]
    IntelligenceReactionStore(conn).ingest(reactions, seen_at=7000)
    reference_store = UsMarketReferenceStore(conn)
    observations = []
    for anchor, ref_return in ((1000, 1.0), (3000, 2.0), (5000, 3.0)):
        observations.extend(
            [
                _reference(source_id="us_sp500", ts=anchor, value=100.0),
                _reference(source_id="us_sp500", ts=anchor + 900, value=100.0 * (1.0 + ref_return / 100.0)),
            ]
        )
    reference_store.ingest(observations, seen_at=7000)

    store = IntelligenceUsMarketSensitivityStore(conn)
    result = store.run(source_ids=["us_sp500"], max_reference_skew_seconds=0, now=7000)
    assert result["pairs"] == {
        "reactions_considered": 3,
        "providers_considered": 3,
        "pairs_ready": 3,
        "inserted": 3,
        "updated": 0,
    }
    assert result["sensitivity"] == {"source_pairs": 3, "groups": 1}

    rows = store.sensitivity(
        market="KRW-BTC",
        event_type="US_SEC_POLICY",
        window="15m",
        reference_source_id="us_sp500",
        now=7000,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["sample_count"] == 3
    assert row["beta"] == pytest.approx(2.0)
    assert row["correlation"] == pytest.approx(1.0)
    assert row["same_direction_count"] == 3
    assert row["same_direction_rate_pct"] == pytest.approx(100.0)
    assert row["reference_positive_count"] == 3
    assert row["reference_negative_count"] == 0
    assert row["mean_coin_when_reference_positive"] == pytest.approx(4.0)
    assert row["confidence"] is None
    assert row["confidence_status"] == "not_promoted"
    assert row["reference_direction_semantics"] == "raw_not_inverted"


def test_pairing_is_forward_only_and_does_not_use_pre_event_reference() -> None:
    conn = _conn()
    IntelligenceReactionStore(conn).ingest([_reaction("event-a", 1000, 2.0)], seen_at=2000)
    UsMarketReferenceStore(conn).ingest(
        [
            _reference(source_id="us_sp500", ts=999, value=100),
            _reference(source_id="us_sp500", ts=1900, value=101),
        ],
        seen_at=2000,
    )
    store = IntelligenceUsMarketSensitivityStore(conn)
    result = store.run(source_ids=["us_sp500"], max_reference_skew_seconds=0, now=2000)
    assert result["pairs"]["pairs_ready"] == 0
    assert conn.execute("SELECT COUNT(*) FROM research_intelligence_us_reference_pairs").fetchone()[0] == 0


def test_reference_provider_identity_is_never_collapsed() -> None:
    conn = _conn()
    reactions = [_reaction("event-a", 1000, 1.0), _reaction("event-b", 3000, 2.0)]
    IntelligenceReactionStore(conn).ingest(reactions, seen_at=5000)
    observations = []
    for provider in ("licensed_a", "licensed_b"):
        for anchor in (1000, 3000):
            observations.extend(
                [
                    _reference(source_id="us_sp500", ts=anchor, value=100.0, provider=provider),
                    _reference(source_id="us_sp500", ts=anchor + 900, value=101.0, provider=provider),
                ]
            )
    UsMarketReferenceStore(conn).ingest(observations, seen_at=5000)
    store = IntelligenceUsMarketSensitivityStore(conn)
    result = store.run(source_ids=["us_sp500"], max_reference_skew_seconds=0, now=5000)
    assert result["pairs"]["pairs_ready"] == 4
    assert result["sensitivity"]["groups"] == 2
    rows = store.sensitivity(market="KRW-BTC", reference_source_id="us_sp500", now=5000)
    assert {row["reference_provider_id"] for row in rows} == {"licensed_a", "licensed_b"}
    assert all(row["sample_count"] == 2 for row in rows)


def test_vix_reference_return_is_stored_raw_without_risk_direction_inversion() -> None:
    conn = _conn()
    IntelligenceReactionStore(conn).ingest([_reaction("event-a", 1000, 5.0)], seen_at=2000)
    UsMarketReferenceStore(conn).ingest(
        [
            _reference(source_id="us_cboe_vix", ts=1000, value=20.0),
            _reference(source_id="us_cboe_vix", ts=1900, value=22.0),
        ],
        seen_at=2000,
    )
    store = IntelligenceUsMarketSensitivityStore(conn)
    store.run(source_ids=["us_cboe_vix"], max_reference_skew_seconds=0, now=2000)
    pair = conn.execute("SELECT * FROM research_intelligence_us_reference_pairs").fetchone()
    assert pair is not None
    assert pair["reference_series"] == "VIX"
    assert pair["reference_return_pct"] == pytest.approx(10.0)
    row = store.sensitivity(market="KRW-BTC", reference_source_id="us_cboe_vix", now=2000)[0]
    assert row["reference_direction_semantics"] == "raw_not_inverted"
    assert row["beta"] is None
    assert row["correlation"] is None


def test_sensitivity_layer_has_no_score_paper_decision_or_order_dependency() -> None:
    path = Path(__file__).resolve().parents[1] / "intelligence_us_market_sensitivity.py"
    text = path.read_text(encoding="utf-8").casefold()
    assert "score_engine" not in text
    assert "paper_engine" not in text
    assert "order_executor" not in text
    assert "trading_decision" not in text
