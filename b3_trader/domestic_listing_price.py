from __future__ import annotations

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


def _observed_range(candles: list[dict[str, Any]]) -> dict[str, Any]:
    timestamps = sorted(ts for row in candles if isinstance(row, dict) if (ts := parse_candle_ts(row)) > 0)
    return {
        "response_count": len(candles),
        "observed_first_ts": timestamps[0] if timestamps else 0.0,
        "observed_last_ts": timestamps[-1] if timestamps else 0.0,
    }


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
