from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from b3_trader.intelligence_event import normalize_intelligence_event
from b3_trader.intelligence_reaction import (
    REACTION_WINDOWS_SECONDS,
    compute_event_reaction,
    event_reaction_anchor,
    normalize_reaction_price_observation,
)
from b3_trader.intelligence_reaction_store import IntelligenceReactionStore


def _event(**overrides):
    values = {
        "source_id": "us_sec_press_releases",
        "source_family": "official_news",
        "event_type": "US_SEC_POLICY",
        "title": "SEC policy fixture",
        "source_url": "https://www.sec.gov/newsroom/press-releases/example",
        "external_id": "fixture-1",
        "published_at": 1_000.0,
        "received_at": 1_010.0,
    }
    values.update(overrides)
    return normalize_intelligence_event(**values)


def _price(
    ts: float,
    price: float,
    *,
    market: str = "KRW-BTC",
    provider: str = "upbit_public_rest",
    exchange: str = "upbit",
):
    return normalize_reaction_price_observation(
        market=market,
        observed_at=ts,
        received_at=ts + 1,
        price=price,
        provider_id=provider,
        exchange=exchange,
        source="public_rest_1m_close",
        evidence={"candle_ts": ts},
    )


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_reaction_windows_are_fixed_phase5_horizons() -> None:
    assert REACTION_WINDOWS_SECONDS == {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def test_reaction_anchor_prefers_publication_then_observation_then_schedule_never_received() -> None:
    event = _event(published_at=1000, observed_at=1001, scheduled_at=900)
    assert event_reaction_anchor(event) == ("published_at", 1000.0)

    observed = _event(published_at=0, observed_at=1001, scheduled_at=900)
    assert event_reaction_anchor(observed) == ("observed_at", 1001.0)

    scheduled = _event(published_at=0, observed_at=0, scheduled_at=900)
    assert event_reaction_anchor(scheduled) == ("scheduled_at", 900.0)

    received_only = _event(published_at=0, observed_at=0, scheduled_at=0, received_at=1234)
    assert event_reaction_anchor(received_only) is None


def test_compute_reaction_is_forward_only_and_calculates_return() -> None:
    event = _event()
    reaction = compute_event_reaction(
        event,
        market="KRW-BTC",
        window="15m",
        start=_price(1005, 100.0),
        end=_price(1907, 103.0),
        max_observation_delay_seconds=10,
    )
    assert reaction is not None
    assert reaction.anchor_kind == "published_at"
    assert reaction.start_delay_seconds == 5
    assert reaction.end_delay_seconds == 7
    assert reaction.forward_return_pct == pytest.approx(3.0)
    assert reaction.provider_id == "upbit_public_rest"
    assert reaction.exchange == "upbit"
    assert reaction.evidence["alignment"]["forward_only"] is True


def test_compute_reaction_rejects_pre_event_or_pre_horizon_observations() -> None:
    event = _event()
    assert compute_event_reaction(
        event,
        market="KRW-BTC",
        window="15m",
        start=_price(999, 100),
        end=_price(1900, 101),
    ) is None
    assert compute_event_reaction(
        event,
        market="KRW-BTC",
        window="15m",
        start=_price(1000, 100),
        end=_price(1899, 101),
    ) is None


def test_compute_reaction_rejects_stale_post_target_observations() -> None:
    event = _event()
    assert compute_event_reaction(
        event,
        market="KRW-BTC",
        window="15m",
        start=_price(1121, 100),
        end=_price(1900, 101),
        max_observation_delay_seconds=120,
    ) is None
    assert compute_event_reaction(
        event,
        market="KRW-BTC",
        window="15m",
        start=_price(1000, 100),
        end=_price(2021, 101),
        max_observation_delay_seconds=120,
    ) is None


def test_compute_reaction_never_mixes_market_provider_exchange_or_market() -> None:
    event = _event()
    start = _price(1000, 100)
    assert compute_event_reaction(
        event,
        market="KRW-BTC",
        window="15m",
        start=start,
        end=_price(1900, 101, provider="bithumb_public_rest"),
    ) is None
    assert compute_event_reaction(
        event,
        market="KRW-BTC",
        window="15m",
        start=start,
        end=_price(1900, 101, exchange="bithumb"),
    ) is None
    assert compute_event_reaction(
        event,
        market="KRW-BTC",
        window="15m",
        start=start,
        end=_price(1900, 101, market="KRW-ETH"),
    ) is None


def test_unknown_window_raises_and_missing_precise_event_clock_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported reaction window"):
        compute_event_reaction(
            _event(),
            market="KRW-BTC",
            window="30m",
            start=_price(1000, 100),
            end=_price(2800, 101),
        )
    assert compute_event_reaction(
        _event(published_at=0, observed_at=0, scheduled_at=0),
        market="KRW-BTC",
        window="15m",
        start=_price(1000, 100),
        end=_price(1900, 101),
    ) is None


def test_reaction_store_is_idempotent_and_queryable() -> None:
    store = IntelligenceReactionStore(_conn())
    event = _event()
    reaction = compute_event_reaction(
        event,
        market="KRW-BTC",
        window="1h",
        start=_price(1000, 100),
        end=_price(4600, 102),
    )
    assert reaction is not None
    assert store.ingest([reaction], seen_at=5000) == {"received": 1, "inserted": 1, "updated": 0}

    revised = replace(reaction, end_price=103.0, forward_return_pct=3.0, version=2)
    assert store.ingest([revised], seen_at=5001) == {"received": 1, "inserted": 0, "updated": 1}
    rows = store.for_event(event.event_id)
    assert len(rows) == 1
    assert rows[0]["forward_return_pct"] == pytest.approx(3.0)
    assert rows[0]["version"] == 2
    assert rows[0]["evidence"]["alignment"]["forward_only"] is True

    history = store.history(event_type="US_SEC_POLICY", market="KRW-BTC", window="1h")
    assert [row["reaction_id"] for row in history] == [reaction.reaction_id]


def test_reaction_layer_has_no_score_paper_decision_or_order_dependency() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ("intelligence_reaction.py", "intelligence_reaction_store.py"):
        text = (root / name).read_text(encoding="utf-8").casefold()
        assert "score_engine" not in text
        assert "paper_engine" not in text
        assert "order_executor" not in text
        assert "trading_decision" not in text
