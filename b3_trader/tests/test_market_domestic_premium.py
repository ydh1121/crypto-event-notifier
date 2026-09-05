from __future__ import annotations

from pathlib import Path

from b3_trader.listing_history import ListingCandle
from b3_trader.listing_history_sources import CexSpotMarket
from b3_trader.listing_identity import ListingIdentity
from b3_trader.market_cross_exchange_gap import MarketCrossExchangeGapEngine
from b3_trader.market_domestic_premium import MarketDomesticPremiumEngine
from b3_trader.market_ohlcv_store import MarketOhlcvStore


def _identity(provider_id: str = "alpha-coin") -> ListingIdentity:
    return ListingIdentity(
        symbol="AAA",
        english_name="Alpha Coin",
        provider="coingecko",
        provider_id=provider_id,
        official_domains=("alpha.example",),
        match_confidence=0.95,
        verified_at=1_000_000.0,
    )


class FakeIdentityResolver:
    def __init__(self, *, right_provider_id: str = "alpha-coin") -> None:
        self.right_provider_id = right_provider_id

    def resolve(self, exchange: str, market: str) -> dict:
        identity = _identity(self.right_provider_id if exchange == "upbit" else "alpha-coin")
        return {"verified": True, "identity": identity, "status": "verified"}


class FakeSource:
    exchange = "binance"

    def __init__(self, *, close: float = 0.07) -> None:
        self.close = close
        self.discover_calls = 0

    def discover(self, identity: ListingIdentity) -> list[CexSpotMarket]:
        self.discover_calls += 1
        return [
            CexSpotMarket(
                exchange="binance",
                market="AAAUSDT",
                base_asset="AAA",
                quote_asset="USDT",
                match_confidence=0.95,
            )
        ]

    def minute_candles(self, market: str, *, start_ts: float, end_ts: float) -> list[ListingCandle]:
        return [
            ListingCandle(
                ts=end_ts - 60.0,
                open=self.close,
                high=self.close,
                low=self.close,
                close=self.close,
                volume=10.0,
                quote_volume=1.0,
                interval_seconds=60,
                confirmed=True,
            )
        ]

    def hourly_candles(self, market: str, *, start_ts: float, end_ts: float) -> list[ListingCandle]:
        return []


class FakeVerifier:
    def verify(self, identity: ListingIdentity, market: CexSpotMarket) -> dict:
        return {
            "verified": True,
            "status": "provider_pair_verified",
            "evidence": {"provider": "coingecko", "coin_id": identity.provider_id},
        }


class FakeQuoteResolver:
    def __init__(self, *, found: bool = True) -> None:
        self.found = found

    def resolve(self, quote_asset: str, target_ts: float) -> dict:
        return {
            "found": self.found,
            "status": "resolved" if self.found else "rate_not_found",
            "quote_asset": quote_asset,
            "rate": 1400.0 if self.found else 0.0,
        }


def _prepare_gap(store: MarketOhlcvStore, *, now: float) -> None:
    rows = []
    for exchange, price in (("bithumb", 100.0), ("upbit", 102.0)):
        rows.append(
            {
                "exchange": exchange,
                "market": "KRW-AAA",
                "timeframe": "1m",
                "candle_ts": now - 60.0,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "base_volume": 1.0,
                "quote_volume": price,
                "is_closed": True,
                "source": "public_rest",
                "received_at": now - 30.0,
            }
        )
    store.upsert_rows(rows)
    MarketCrossExchangeGapEngine(store.conn).compute(
        bithumb_names={"KRW-AAA": "Alpha Coin"},
        upbit_names={"KRW-AAA": "Alpha Coin"},
        now=now,
    )


def test_premium_requires_same_verified_identity_and_exact_foreign_pair(tmp_path: Path) -> None:
    store = MarketOhlcvStore(tmp_path / "premium.sqlite3")
    now = 2_000_000.0
    _prepare_gap(store, now=now)
    source = FakeSource()
    engine = MarketDomesticPremiumEngine(
        store.conn,
        identity_resolver=FakeIdentityResolver(),
        sources=[source],
        venue_verifier=FakeVerifier(),
        quote_resolver=FakeQuoteResolver(),
    )
    try:
        result = engine.collect_market("KRW-AAA", now=now)
        row = engine.read_market("KRW-AAA")
        assert result["status"] == "computed"
        assert result["verified_sources"] == 1
        assert row["identity_verified"] is True
        assert row["provider"] == "coingecko"
        assert row["provider_id"] == "alpha-coin"
        assert row["reference_exchange"] == "binance"
        assert row["reference_market"] == "AAAUSDT"
        assert row["reference_price_quote"] == 0.07
        assert row["quote_to_krw"] == 1400.0
        assert round(float(row["reference_price_krw"]), 8) == 98.0
        assert round(float(row["bithumb_premium_pct"]), 6) == round((100.0 / 98.0 - 1.0) * 100.0, 6)
        assert round(float(row["upbit_premium_pct"]), 6) == round((102.0 / 98.0 - 1.0) * 100.0, 6)
        assert row["paper_only"] is True
        assert row["score_wired"] is False
    finally:
        store.close()


def test_premium_fails_closed_when_domestic_provider_ids_differ(tmp_path: Path) -> None:
    store = MarketOhlcvStore(tmp_path / "premium.sqlite3")
    now = 2_000_000.0
    _prepare_gap(store, now=now)
    source = FakeSource()
    engine = MarketDomesticPremiumEngine(
        store.conn,
        identity_resolver=FakeIdentityResolver(right_provider_id="different-coin"),
        sources=[source],
        venue_verifier=FakeVerifier(),
        quote_resolver=FakeQuoteResolver(),
    )
    try:
        result = engine.collect_market("KRW-AAA", now=now)
        row = engine.read_market("KRW-AAA")
        assert result["status"] == "domestic_identity_unverified"
        assert row["identity_verified"] is False
        assert row["reference_price_krw"] is None
        assert row["bithumb_premium_pct"] is None
        assert source.discover_calls == 0
    finally:
        store.close()


def test_premium_does_not_mix_quote_currency_without_krw_rate(tmp_path: Path) -> None:
    store = MarketOhlcvStore(tmp_path / "premium.sqlite3")
    now = 2_000_000.0
    _prepare_gap(store, now=now)
    engine = MarketDomesticPremiumEngine(
        store.conn,
        identity_resolver=FakeIdentityResolver(),
        sources=[FakeSource()],
        venue_verifier=FakeVerifier(),
        quote_resolver=FakeQuoteResolver(found=False),
    )
    try:
        result = engine.collect_market("KRW-AAA", now=now)
        row = engine.read_market("KRW-AAA")
        assert result["status"] == "foreign_reference_unavailable"
        assert row["identity_verified"] is True
        assert row["reference_price_krw"] is None
        assert row["bithumb_premium_pct"] is None
        assert row["upbit_premium_pct"] is None
    finally:
        store.close()
