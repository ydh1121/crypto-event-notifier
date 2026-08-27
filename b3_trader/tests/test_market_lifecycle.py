from __future__ import annotations

import sqlite3

from b3_trader.exchange_public import PublicMarket
from b3_trader.market_lifecycle import CAUTION, NEW_LISTING, NORMAL, TERMINATED
from b3_trader.market_lifecycle_store import MarketLifecycleStore


def _store() -> MarketLifecycleStore:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return MarketLifecycleStore(conn)


def _market(symbol: str, *, warning: bool = False) -> PublicMarket:
    return PublicMarket(
        exchange="bithumb",
        market=f"KRW-{symbol}",
        symbol=symbol,
        name=symbol,
        warning=warning,
    )


def test_first_observation_is_baseline_not_mass_new_listing() -> None:
    store = _store()
    snapshot = store.observe_markets("bithumb", [_market("AAA"), _market("BBB")], observed_at=1_000.0)

    assert snapshot["baseline_run"] is True
    assert snapshot["states"] == {"KRW-AAA": NORMAL, "KRW-BBB": NORMAL}
    assert snapshot["transitions"] == []


def test_new_market_after_baseline_is_new_listing() -> None:
    store = _store()
    store.observe_markets("bithumb", [_market("AAA")], observed_at=1_000.0)
    snapshot = store.observe_markets("bithumb", [_market("AAA"), _market("NEW")], observed_at=1_100.0)

    assert snapshot["states"]["KRW-NEW"] == NEW_LISTING
    assert snapshot["transitions"] == [
        {"market": "KRW-NEW", "from": "", "to": NEW_LISTING, "reason": "recent_market_first_seen"}
    ]


def test_exchange_warning_maps_to_caution() -> None:
    store = _store()
    store.observe_markets("bithumb", [_market("AAA")], observed_at=1_000.0)
    snapshot = store.observe_markets("bithumb", [_market("AAA", warning=True)], observed_at=1_100.0)

    assert snapshot["states"]["KRW-AAA"] == CAUTION
    assert snapshot["counts"][CAUTION] == 1


def test_missing_market_requires_three_observations_before_termination() -> None:
    store = _store()
    store.observe_markets("bithumb", [_market("AAA"), _market("BBB")], observed_at=1_000.0)

    one = store.observe_markets("bithumb", [_market("AAA")], observed_at=1_100.0)
    two = store.observe_markets("bithumb", [_market("AAA")], observed_at=1_200.0)
    three = store.observe_markets("bithumb", [_market("AAA")], observed_at=1_300.0)

    assert one["states"]["KRW-BBB"] == NORMAL
    assert two["states"]["KRW-BBB"] == NORMAL
    assert three["states"]["KRW-BBB"] == TERMINATED
    assert any(row["market"] == "KRW-BBB" and row["to"] == TERMINATED for row in three["transitions"])


def test_reappearing_recent_market_can_return_as_new_listing() -> None:
    store = _store()
    store.observe_markets("bithumb", [_market("AAA")], observed_at=1_000.0)
    store.observe_markets("bithumb", [_market("AAA"), _market("NEW")], observed_at=1_100.0)
    store.observe_markets("bithumb", [_market("AAA")], observed_at=1_200.0)
    store.observe_markets("bithumb", [_market("AAA")], observed_at=1_300.0)
    store.observe_markets("bithumb", [_market("AAA")], observed_at=1_400.0)

    snapshot = store.observe_markets("bithumb", [_market("AAA"), _market("NEW")], observed_at=1_500.0)
    assert snapshot["states"]["KRW-NEW"] == NEW_LISTING
