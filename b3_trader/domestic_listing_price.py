from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from .bithumb_client import BithumbClient
from .domestic_candle_utils import opening_price_at_or_after, parse_candle_ts
from .upbit_client import UpbitClient

KST = timezone(timedelta(hours=9))
OPEN_SEARCH_SECONDS = 20 * 60


class MinuteCandleClient(Protocol):
    def candles_minutes(self, market: str, unit: int = 5, count: int = 120, to: str | None = None) -> list[dict[str, Any]]: ...


def listing_open_from_candles(
    candles: list[dict[str, Any]],
    *,
    open_at: float,
    tolerance_seconds: int = OPEN_SEARCH_SECONDS,
) -> dict[str, Any]:
    return opening_price_at_or_after(
        candles,
        target_ts=open_at,
        max_delay_seconds=tolerance_seconds,
    )


def candle_query_to(exchange: str, target_ts: float) -> str:
    """Format quotation API `to` according to each domestic exchange contract."""
    name = str(exchange or "").lower()
    if name == "bithumb":
        # Bithumb documents `to` as a KST clock time with no timezone suffix.
        return datetime.fromtimestamp(target_ts, tz=KST).strftime("%Y-%m-%d %H:%M:%S")
    # Upbit accepts ISO-8601 UTC Zulu time (and explicit timezone offsets).
    return datetime.fromtimestamp(target_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamped_rows(candles: list[dict[str, Any]]) -> list[tuple[float, dict[str, Any]]]:
    rows = [
        (parse_candle_ts(row), row)
        for row in candles
        if isinstance(row, dict)
    ]
    return sorted((row for row in rows if row[0] > 0), key=lambda row: row[0])


def _observed_range(candles: list[dict[str, Any]]) -> dict[str, Any]:
    timestamps = [row[0] for row in _timestamped_rows(candles)]
    return {
        "response_count": len(candles),
        "observed_first_ts": timestamps[0] if timestamps else 0.0,
        "observed_last_ts": timestamps[-1] if timestamps else 0.0,
    }


def _opening_price(row: dict[str, Any]) -> float:
    try:
        return float(row.get("opening_price") or 0.0)
    except (TypeError, ValueError):
        return 0.0


class DomesticListingPriceResolver:
    """Read the first actual domestic 1-minute trade candle at/after trade_open_at."""

    def __init__(
        self,
        *,
        bithumb: MinuteCandleClient | None = None,
        upbit: MinuteCandleClient | None = None,
    ) -> None:
        self.clients: dict[str, MinuteCandleClient] = {
            "bithumb": bithumb or BithumbClient(),
            "upbit": upbit or UpbitClient(),
        }

    def resolve(self, exchange: str, market: str, open_at: float) -> dict[str, Any]:
        name = str(exchange or "").lower()
        client = self.clients.get(name)
        if client is None:
            return {"status": "unsupported_exchange", "found": False, "price": 0.0}
        if open_at <= 0:
            return {"status": "open_time_missing", "found": False, "price": 0.0}

        # `to` is exclusive. Search a bounded window after the scheduled open so
        # delayed first trades still produce the real first traded minute candle.
        query_until = open_at + OPEN_SEARCH_SECONDS
        to = candle_query_to(name, query_until)
        try:
            candles = client.candles_minutes(str(market).upper(), unit=1, count=30, to=to)
        except Exception as exc:
            return {
                "status": "source_error",
                "found": False,
                "price": 0.0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        result = listing_open_from_candles(candles, open_at=open_at)
        return {
            "status": "resolved" if result["found"] else "candle_not_found",
            "exchange": name,
            "market": str(market).upper(),
            "open_at": float(open_at),
            "query_to": to,
            **_observed_range(candles),
            **result,
        }

    def resolve_first_trade(
        self,
        exchange: str,
        market: str,
        *,
        now: float | None = None,
        max_coarse_pages: int = 3,
    ) -> dict[str, Any]:
        """Fail-safe a missing notice open time from the market's first public trade.

        Recent listing cases can lose the public notice/detail id. Page backward
        through 240-minute public candles until the exchange proves the beginning
        of available history, then narrow the oldest bucket with 60-minute and
        1-minute candles. If the bounded history cannot prove the beginning, fail
        closed instead of treating the oldest observed page as a launch event.
        """
        name = str(exchange or "").lower()
        client = self.clients.get(name)
        if client is None:
            return {"status": "unsupported_exchange", "found": False, "open_at": 0.0, "price": 0.0}

        cursor = float(now or time.time()) + 60.0
        coarse: list[tuple[float, dict[str, Any]]] = []
        oldest_reached = False
        pages = 0
        try:
            for _ in range(max(1, min(6, int(max_coarse_pages)))):
                rows = client.candles_minutes(
                    str(market).upper(), unit=240, count=200, to=candle_query_to(name, cursor)
                )
                parsed = _timestamped_rows(rows)
                pages += 1
                if not parsed:
                    break
                coarse.extend(parsed)
                oldest = parsed[0][0]
                if len(rows) < 200:
                    oldest_reached = True
                    break
                if oldest >= cursor - 60:
                    break
                cursor = oldest
        except Exception as exc:
            return {
                "status": "source_error",
                "found": False,
                "open_at": 0.0,
                "price": 0.0,
                "error": f"{type(exc).__name__}: {exc}",
            }

        if not coarse:
            return {
                "status": "first_trade_not_found",
                "found": False,
                "open_at": 0.0,
                "price": 0.0,
                "coarse_pages": pages,
            }
        if not oldest_reached:
            return {
                "status": "history_window_exhausted",
                "found": False,
                "open_at": 0.0,
                "price": 0.0,
                "coarse_pages": pages,
                "oldest_coarse_ts": min(item[0] for item in coarse),
            }

        coarse_start = min(item[0] for item in coarse)
        try:
            hour_rows = client.candles_minutes(
                str(market).upper(),
                unit=60,
                count=8,
                to=candle_query_to(name, coarse_start + 4 * 3600 + 60),
            )
            hours = [
                item for item in _timestamped_rows(hour_rows)
                if coarse_start <= item[0] < coarse_start + 4 * 3600 + 60
            ]
            if not hours:
                return {
                    "status": "first_trade_hour_not_found",
                    "found": False,
                    "open_at": 0.0,
                    "price": 0.0,
                    "coarse_start": coarse_start,
                }
            hour_start = hours[0][0]
            minute_rows = client.candles_minutes(
                str(market).upper(),
                unit=1,
                count=120,
                to=candle_query_to(name, hour_start + 3600 + 60),
            )
        except Exception as exc:
            return {
                "status": "source_error",
                "found": False,
                "open_at": 0.0,
                "price": 0.0,
                "error": f"{type(exc).__name__}: {exc}",
            }

        minutes = [
            item for item in _timestamped_rows(minute_rows)
            if hour_start <= item[0] < hour_start + 3600 + 60
        ]
        if not minutes:
            return {
                "status": "first_trade_minute_not_found",
                "found": False,
                "open_at": 0.0,
                "price": 0.0,
                "hour_start": hour_start,
            }
        first_ts, first_row = minutes[0]
        price = _opening_price(first_row)
        if price <= 0:
            return {
                "status": "first_trade_price_missing",
                "found": False,
                "open_at": 0.0,
                "price": 0.0,
                "candle_ts": first_ts,
            }
        return {
            "status": "resolved_first_trade",
            "found": True,
            "exchange": name,
            "market": str(market).upper(),
            "open_at": first_ts,
            "price": price,
            "candle_ts": first_ts,
            "price_basis": "first_public_trade_candle",
            "coarse_pages": pages,
            "coarse_start": coarse_start,
            "hour_start": hour_start,
        }
