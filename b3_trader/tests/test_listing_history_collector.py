from __future__ import annotations

from pathlib import Path

from b3_trader.listing_history import ListingCandle
from b3_trader.listing_history_collector import DomesticListingCase, ListingHistoryCollector
from b3_trader.listing_history_sources import CexSpotMarket
from b3_trader.listing_history_store import ListingHistoryStore
from b3_trader.listing_identity import ListingIdentity


class FakeSource:
    exchange = "fake"

    def __init__(self) -> None:
        self.discover_calls = 0
        self.candle_calls = 0

    def discover(self, identity: ListingIdentity) -> list[CexSpotMarket]:
        self.discover_calls += 1
        return [
            CexSpotMarket(
                exchange="fake",
                market="ABCUSDT",
                base_asset="ABC",
                quote_asset="USDT",
                listing_at=1000,
                first_price=10,
                match_confidence=identity.match_confidence,
                match_basis={"identity_gate": "verified"},
            )
        ]

    def hourly_candles(self, market: str, *, start_ts: float, end_ts: float) -> list[ListingCandle]:
        self.candle_calls += 1
        domestic = 10 * 24 * 3600.0
        return [
            ListingCandle(ts=domestic - 24 * 3600, open=10, high=12, low=9, close=11),
            ListingCandle(ts=domestic - 3600, open=15, high=17, low=14, close=16),
            ListingCandle(ts=domestic + 3600, open=22, high=23, low=20, close=21),
        ]


def verified_identity() -> ListingIdentity:
    return ListingIdentity(
        symbol="ABC",
        english_name="Alpha Beta Coin",
        provider="coingecko",
        provider_id="alpha-beta-coin",
        official_domains=("example.org",),
        match_confidence=0.95,
    )


def test_collector_persists_verified_case(tmp_path: Path) -> None:
    source = FakeSource()
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
    collector = ListingHistoryCollector(store=store, sources=(source,))
    domestic = 10 * 24 * 3600.0
    try:
        result = collector.collect_case(
            DomesticListingCase(
                exchange="bithumb",
                market="KRW-ABC",
                symbol="ABC",
                announcement_at=domestic - 3600,
                open_at=domestic,
                open_price=20,
                identity=verified_identity(),
            )
        )
        assert result["status"] == "complete"
        assert result["sources_ok"] == 1
        assert source.discover_calls == 1
        assert source.candle_calls == 1
        assert store.pending_cases() == []
    finally:
        collector.close()


def test_collector_rejects_weak_identity_without_network(tmp_path: Path) -> None:
    source = FakeSource()
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
    collector = ListingHistoryCollector(store=store, sources=(source,))
    try:
        result = collector.collect_case(
            DomesticListingCase(
                exchange="bithumb",
                market="KRW-ABC",
                symbol="ABC",
                announcement_at=1,
                open_at=2,
                open_price=20,
                identity=ListingIdentity(symbol="ABC", match_confidence=1.0),
            )
        )
        assert result["status"] == "rejected_identity"
        assert source.discover_calls == 0
        assert source.candle_calls == 0
    finally:
        collector.close()
