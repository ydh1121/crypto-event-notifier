from __future__ import annotations

from datetime import datetime, timedelta, timezone

from b3_trader.domestic_candle_utils import parse_candle_ts
from b3_trader.domestic_listing_price import (
    DomesticListingPriceResolver,
    candle_query_to,
    listing_open_from_candles,
)

KST = timezone(timedelta(hours=9))


def test_listing_open_uses_first_candle_at_or_after_open() -> None:
    open_at = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc).timestamp()
    rows = [
        {"candle_date_time_utc": "2026-08-28T07:59:00", "opening_price": 99},
        {"candle_date_time_utc": "2026-08-28T08:04:00", "opening_price": 103},
        {"candle_date_time_utc": "2026-08-28T08:06:00", "opening_price": 105},
    ]
    result = listing_open_from_candles(rows, open_at=open_at)
    assert result["found"] is True
    assert result["price"] == 103
    assert result["distance_seconds"] == 240
    assert result["price_basis"] == "first_opening_price_at_or_after_trade_open"


def test_bithumb_kst_candle_timestamp_is_supported_without_utc_field() -> None:
    row = {"candle_date_time_kst": "2026-08-07T15:00:00", "opening_price": 123}
    expected = datetime(2026, 8, 7, 15, 0, tzinfo=KST).timestamp()
    assert parse_candle_ts(row) == expected


def test_bithumb_query_to_uses_kst_clock_without_zone_suffix() -> None:
    target = datetime(2026, 8, 7, 15, 20, tzinfo=KST).timestamp()
    assert candle_query_to("bithumb", target) == "2026-08-07 15:20:00"


def test_upbit_query_to_uses_utc_zulu_clock() -> None:
    target = datetime(2026, 8, 7, 15, 20, tzinfo=KST).timestamp()
    assert candle_query_to("upbit", target) == "2026-08-07T06:20:00Z"


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def candles_minutes(self, market: str, unit: int = 5, count: int = 120, to: str | None = None):
        self.calls.append((market, unit, count, to))
        return self.rows


def test_resolver_uses_bounded_public_minute_window() -> None:
    open_at = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc).timestamp()
    fake = FakeClient([
        {"candle_date_time_kst": "2026-08-28T17:03:00", "opening_price": 123.45},
    ])
    resolver = DomesticListingPriceResolver(bithumb=fake, upbit=fake)
    result = resolver.resolve("bithumb", "KRW-ABC", open_at)
    assert result["status"] == "resolved"
    assert result["price"] == 123.45
    assert result["response_count"] == 1
    assert fake.calls[0][0:3] == ("KRW-ABC", 1, 30)
    assert fake.calls[0][3] == "2026-08-28 17:20:00"
