from __future__ import annotations

from datetime import datetime, timezone

from b3_trader.listing_quote_rate import ListingQuoteRateResolver


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


class FakeClient:
    def __init__(self, rows=None, error: Exception | None = None) -> None:
        self.rows = list(rows or [])
        self.error = error
        self.calls = []

    def candles_minutes(self, market: str, unit: int = 5, count: int = 120, to: str | None = None):
        self.calls.append((market, unit, count, to))
        if self.error is not None:
            raise self.error
        return list(self.rows)


def test_quote_rate_uses_only_candle_at_or_before_target() -> None:
    target = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    bithumb = FakeClient(
        [
            {"candle_date_time_utc": _iso(target + 60), "trade_price": 9999, "opening_price": 9999},
            {"candle_date_time_utc": _iso(target - 60), "trade_price": 1400, "opening_price": 1399},
        ]
    )
    resolver = ListingQuoteRateResolver(bithumb=bithumb, upbit=FakeClient())
    result = resolver.resolve("USDT", target)
    assert result["found"] is True
    assert result["rate"] == 1400
    assert result["source_exchange"] == "bithumb"
    assert result["source_market"] == "KRW-USDT"
    assert result["lag_seconds"] == 60


def test_quote_rate_falls_back_to_second_domestic_exchange() -> None:
    target = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    upbit = FakeClient(
        [{"candle_date_time_utc": _iso(target), "trade_price": 1410, "opening_price": 1405}]
    )
    resolver = ListingQuoteRateResolver(
        bithumb=FakeClient(error=RuntimeError("missing market")),
        upbit=upbit,
    )
    result = resolver.resolve("USDT", target)
    assert result["found"] is True
    assert result["rate"] == 1410
    assert result["source_exchange"] == "upbit"


def test_quote_rate_does_not_invent_stablecoin_parity() -> None:
    resolver = ListingQuoteRateResolver(bithumb=FakeClient(), upbit=FakeClient())
    result = resolver.resolve("FDUSD", 1_000_000)
    assert result["found"] is False
    assert result["status"] == "unsupported_quote"
    assert result["rate"] == 0


def test_krw_quote_is_identity_rate() -> None:
    resolver = ListingQuoteRateResolver(bithumb=FakeClient(), upbit=FakeClient())
    result = resolver.resolve("KRW", 1_000_000)
    assert result["found"] is True
    assert result["rate"] == 1.0
    assert result["source_exchange"] == "identity"
