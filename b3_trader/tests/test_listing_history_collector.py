from __future__ import annotations

import json
from pathlib import Path

from b3_trader.listing_history import ListingCandle
from b3_trader.listing_history_collector import FEATURE_VERSION, DomesticListingCase, ListingHistoryCollector
from b3_trader.listing_history_sources import CexSpotMarket
from b3_trader.listing_history_store import ListingHistoryStore
from b3_trader.listing_identity import ListingIdentity


class FakeSource:
    exchange = "fake"

    def __init__(self) -> None:
        self.discover_calls = 0
        self.candle_calls = 0
        self.minute_calls = 0

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
            ListingCandle(ts=domestic + 6 * 3600, open=24, high=26, low=23, close=25),
            ListingCandle(ts=domestic + 24 * 3600, open=28, high=30, low=27, close=29),
            ListingCandle(ts=domestic + 3 * 24 * 3600, open=32, high=34, low=31, close=33),
            ListingCandle(ts=domestic + 7 * 24 * 3600, open=40, high=42, low=39, close=41),
        ]

    def minute_candles(self, market: str, *, start_ts: float, end_ts: float) -> list[ListingCandle]:
        self.minute_calls += 1
        domestic = 10 * 24 * 3600.0
        return [
            ListingCandle(ts=domestic, open=16, high=17, low=15, close=16.5, interval_seconds=60),
            ListingCandle(ts=domestic + 5 * 60, open=18, high=19, low=17, close=18.5, interval_seconds=60),
            ListingCandle(ts=domestic + 6 * 60, open=18.5, high=19, low=18, close=18.8, interval_seconds=60),
        ]


class FakeNotListedSource(FakeSource):
    exchange = "empty"

    def discover(self, identity: ListingIdentity) -> list[CexSpotMarket]:
        self.discover_calls += 1
        return []


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


class FakeQuoteRateResolver:
    def __init__(self, rate: float = 1.0, found: bool = True) -> None:
        self.rate = rate
        self.found = found
        self.calls = []

    def resolve(self, quote_asset: str, target_ts: float):
        self.calls.append((quote_asset, target_ts))
        return {
            "status": "resolved" if self.found else "rate_not_found",
            "found": self.found,
            "rate": self.rate if self.found else 0.0,
            "quote_asset": quote_asset,
            "source_exchange": "fake-domestic",
            "source_market": f"KRW-{quote_asset}",
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


def _collector(store: ListingHistoryStore, source, verifier=None, quote=None) -> ListingHistoryCollector:
    return ListingHistoryCollector(
        store=store,
        sources=(source,),
        venue_verifier=verifier or FakeVenueVerifier(),
        quote_rate_resolver=quote or FakeQuoteRateResolver(),
    )


def test_collector_persists_provider_verified_case_quote_rate_and_exact_p5m(tmp_path: Path) -> None:
    source = FakeSource()
    verifier = FakeVenueVerifier()
    quote = FakeQuoteRateResolver(rate=1.0)
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
    collector = _collector(store, source, verifier, quote)
    try:
        result = collector.collect_case(_case())
        assert result["status"] == "complete"
        assert result["sources_ok"] == 1
        assert source.discover_calls == 1
        assert source.candle_calls == 1
        assert source.minute_calls == 1
        assert result["sources"]["fake"]["minute_candles"] == 3
        assert result["sources"]["fake"]["fine_reaction_status"] == "collected"
        assert verifier.calls == [("alpha-beta-coin", "ABCUSDT")]
        assert quote.calls == [("USDT", _case().open_at)]
        feature_row = store.conn.execute(
            "SELECT feature_version,feature_json FROM listing_history_features WHERE source_exchange='fake'"
        ).fetchone()
        assert feature_row is not None
        assert int(feature_row["feature_version"]) == FEATURE_VERSION == 3
        payload = json.loads(feature_row["feature_json"])
        assert payload["prelisting"]["currency_safe"] is True
        assert payload["prelisting"]["quote_asset"] == "USDT"
        assert payload["foreign_postlisting"]["anchor_price"] == 16
        assert payload["foreign_postlisting"]["windows"]["p5m"]["price"] == 18
        assert payload["foreign_postlisting"]["windows"]["p5m"]["interval_seconds"] == 60
        assert payload["foreign_postlisting"]["p5m_source_interval_seconds"] == 60
        assert store.pending_cases(required_feature_version=FEATURE_VERSION) == []
    finally:
        collector.close()


def test_collector_keeps_domestic_premium_null_without_quote_rate(tmp_path: Path) -> None:
    source = FakeSource()
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
    collector = _collector(store, source, quote=FakeQuoteRateResolver(found=False))
    try:
        result = collector.collect_case(_case())
        assert result["sources_ok"] == 1
        assert result["sources"]["fake"]["domestic_listing_premium_pct"] is None
        row = store.conn.execute(
            "SELECT feature_json FROM listing_history_features WHERE source_exchange='fake'"
        ).fetchone()
        payload = json.loads(row["feature_json"])
        assert payload["prelisting"]["quote_to_krw_at_open"] is None
        assert payload["prelisting"]["domestic_listing_premium_pct"] is None
    finally:
        collector.close()


def test_collector_marks_discovered_but_unverified_pair_as_waiting(tmp_path: Path) -> None:
    source = FakeSource()
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
    collector = _collector(store, source, verifier=FakeVenueVerifier(False))
    try:
        result = collector.collect_case(_case())
        assert result["status"] == "venue_verification_waiting"
        assert result["sources_ok"] == 0
        assert result["sources"]["fake"]["status"] == "venue_unverified"
        assert source.candle_calls == 0
        assert source.minute_calls == 0
        assert len(store.pending_cases(required_feature_version=FEATURE_VERSION)) == 1
    finally:
        collector.close()


def test_collector_uses_no_foreign_market_only_when_discovery_is_empty(tmp_path: Path) -> None:
    source = FakeNotListedSource()
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
    collector = _collector(store, source)
    try:
        result = collector.collect_case(_case())
        assert result["status"] == "no_foreign_market_found"
        assert result["sources"]["empty"]["status"] == "not_listed"
    finally:
        collector.close()


def test_collector_rejects_weak_identity_without_network(tmp_path: Path) -> None:
    source = FakeSource()
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
    collector = _collector(store, source)
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
        assert source.minute_calls == 0
    finally:
        collector.close()


def test_unknown_foreign_launch_is_not_inferred_from_prelisting_window(tmp_path: Path) -> None:
    source = FakeUnknownLaunchSource()
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
    collector = _collector(store, source)
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
    collector = _collector(store, source)
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
