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


class FakeUnknownLaunchSource(FakeSource):
    exchange = "unknown"

    def discover(self, identity: ListingIdentity) -> list[CexSpotMarket]:
        self.discover_calls += 1
        return [
            CexSpotMarket(
                exchange="unknown",
                market="ABCUSDT",
                base_asset="ABC",
                quote_asset="USDT",
                listing_at=0,
                first_price=0,
                match_confidence=identity.match_confidence,
                match_basis={"identity_gate": "verified"},
            )
        ]


class FakeKnownLaunchSource(FakeSource):
    exchange = "known"

    def discover(self, identity: ListingIdentity) -> list[CexSpotMarket]:
        self.discover_calls += 1
        return [
            CexSpotMarket(
                exchange="known",
                market="ABCUSDT",
                base_asset="ABC",
                quote_asset="USDT",
                listing_at=50_000,
                first_price=0,
                match_confidence=identity.match_confidence,
                match_basis={"identity_gate": "verified"},
            )
        ]

    def hourly_candles(self, market: str, *, start_ts: float, end_ts: float) -> list[ListingCandle]:
        self.candle_calls += 1
        if end_ts <= 50_000 + 2 * 3600:
            return [ListingCandle(ts=50_000, open=3, high=4, low=2, close=3.5)]
        return super().hourly_candles(market, start_ts=start_ts, end_ts=end_ts)


class FakeVenueVerifier:
    def __init__(self, verified: bool = True) -> None:
        self.verified = verified
        self.calls = []

    def verify(self, identity: ListingIdentity, market: CexSpotMarket):
        self.calls.append((identity.provider_id, market.market))
        return {
            "verified": self.verified,
            "status": "provider_pair_verified" if self.verified else "provider_pair_not_found",
            "evidence": {"provider": "coingecko", "coin_id": identity.provider_id},
        }


def verified_identity() -> ListingIdentity:
    return ListingIdentity(
        symbol="ABC",
        english_name="Alpha Beta Coin",
        provider="coingecko",
        provider_id="alpha-beta-coin",
        official_domains=("example.org",),
        match_confidence=0.95,
    )


def _case() -> DomesticListingCase:
    domestic = 10 * 24 * 3600.0
    return DomesticListingCase(
        exchange="bithumb",
        market="KRW-ABC",
        symbol="ABC",
        announcement_at=domestic - 3600,
        open_at=domestic,
        open_price=20,
        identity=verified_identity(),
    )


def test_collector_persists_provider_verified_case(tmp_path: Path) -> None:
    source = FakeSource()
    verifier = FakeVenueVerifier()
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
    collector = ListingHistoryCollector(store=store, sources=(source,), venue_verifier=verifier)
    try:
        result = collector.collect_case(_case())
        assert result["status"] == "complete"
        assert result["sources_ok"] == 1
        assert source.discover_calls == 1
        assert source.candle_calls == 1
        assert verifier.calls == [("alpha-beta-coin", "ABCUSDT")]
        assert store.pending_cases() == []
    finally:
        collector.close()


def test_collector_rejects_unverified_foreign_pair(tmp_path: Path) -> None:
    source = FakeSource()
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
    collector = ListingHistoryCollector(
        store=store,
        sources=(source,),
        venue_verifier=FakeVenueVerifier(False),
    )
    try:
        result = collector.collect_case(_case())
        assert result["status"] == "no_foreign_market_found"
        assert result["sources_ok"] == 0
        assert result["sources"]["fake"]["status"] == "venue_unverified"
        assert source.candle_calls == 0
    finally:
        collector.close()


def test_collector_rejects_weak_identity_without_network(tmp_path: Path) -> None:
    source = FakeSource()
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
    collector = ListingHistoryCollector(store=store, sources=(source,), venue_verifier=FakeVenueVerifier())
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


def test_unknown_foreign_launch_is_not_inferred_from_prelisting_window(tmp_path: Path) -> None:
    source = FakeUnknownLaunchSource()
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
    collector = ListingHistoryCollector(store=store, sources=(source,), venue_verifier=FakeVenueVerifier())
    try:
        result = collector.collect_case(_case())
        assert result["sources_ok"] == 1
        row = store.conn.execute(
            "SELECT source_listing_at,first_price FROM listing_history_sources WHERE source_exchange='unknown'"
        ).fetchone()
        assert row is not None
        assert float(row["source_listing_at"]) == 0
        assert float(row["first_price"]) == 0
    finally:
        collector.close()


def test_known_foreign_launch_fetches_price_from_launch_window(tmp_path: Path) -> None:
    source = FakeKnownLaunchSource()
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
    collector = ListingHistoryCollector(store=store, sources=(source,), venue_verifier=FakeVenueVerifier())
    try:
        result = collector.collect_case(_case())
        assert result["sources_ok"] == 1
        row = store.conn.execute(
            "SELECT source_listing_at,first_price FROM listing_history_sources WHERE source_exchange='known'"
        ).fetchone()
        assert row is not None
        assert float(row["source_listing_at"]) == 50_000
        assert float(row["first_price"]) == 3
        assert source.candle_calls >= 2
    finally:
        collector.close()
