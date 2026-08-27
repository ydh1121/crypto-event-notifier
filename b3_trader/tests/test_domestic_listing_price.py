from __future__ import annotations

from datetime import datetime, timedelta, timezone

from b3_trader.domestic_listing_price import (
    DomesticListingPriceResolver,
    candle_query_to,
    listing_open_from_candles,
)

KST = timezone(timedelta(hours=9))


def test_listing_open_picks_nearest_candle() -> None:
    open_at = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc).timestamp()
    rows = [
        {"candle_date_time_utc": "2026-08-28T07:59:00", "opening_price": 99},
        {"candle_date_time_utc": "2026-08-28T08:00:00", "opening_price": 101},
        {"candle_date_time_utc": "2026-08-28T08:01:00", "opening_price": 103},
    ]
    result = listing_open_from_candles(rows, open_at=open_at)
    assert result["found"] is True
    assert result["price"] == 101
    assert result["distance_seconds"] == 0


def test_bithumb_query_to_uses_kst_clock_without_z_suffix() -> None:
    target = datetime(2026, 8, 7, 15, 5, tzinfo=KST).timestamp()
    assert candle_query_to("bithumb", target) == "2026-08-07T15:05:00"


def test_upbit_query_to_uses_utc_zulu_clock() -> None:
    target = datetime(2026, 8, 7, 15, 5, tzinfo=KST).timestamp()
    assert candle_query_to("upbit", target) == "2026-08-07T06:05:00Z"


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def candles_minutes(self, market: str, unit: int = 5, count: int = 120, to: str | None = None):
        self.calls.append((market, unit, count, to))
        return self.rows


def test_resolver_uses_public_minute_candle_shape() -> None:
    open_at = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc).timestamp()
    fake = FakeClient([
        {"candle_date_time_utc": "2026-08-28T08:00:00", "opening_price": 123.45},
    ])
    resolver = DomesticListingPriceResolver(bithumb=fake, upbit=fake)
    result = resolver.resolve("bithumb", "KRW-ABC", open_at)
    assert result["status"] == "resolved"
    assert result["price"] == 123.45
    assert fake.calls[0][0:3] == ("KRW-ABC", 1, 8)
    assert fake.calls[0][3] == "2026-08-28T17:05:00"
