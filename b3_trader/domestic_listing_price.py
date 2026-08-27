from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from .bithumb_client import BithumbClient
from .domestic_candle_utils import nearest_opening_price
from .upbit_client import UpbitClient

KST = timezone(timedelta(hours=9))


class MinuteCandleClient(Protocol):
    def candles_minutes(self, market: str, unit: int = 5, count: int = 120, to: str | None = None) -> list[dict[str, Any]]: ...


def listing_open_from_candles(
    candles: list[dict[str, Any]],
    *,
    open_at: float,
    tolerance_seconds: int = 180,
) -> dict[str, Any]:
    return nearest_opening_price(
        candles,
        target_ts=open_at,
        tolerance_seconds=tolerance_seconds,
    )


def candle_query_to(exchange: str, target_ts: float) -> str:
    """Format quotation API `to` according to each domestic exchange contract."""
    name = str(exchange or "").lower()
    if name == "bithumb":
        # Bithumb documents `to` as a KST clock time and its examples omit a
        # timezone suffix. Sending a UTC `Z` value shifts historical lookups by
        # nine hours when the server interprets the clock as KST.
        return datetime.fromtimestamp(target_ts, tz=KST).strftime("%Y-%m-%dT%H:%M:%S")
    # Upbit accepts an ISO-8601 UTC Zulu timestamp (and also explicit offsets).
    return datetime.fromtimestamp(target_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DomesticListingPriceResolver:
    """Read the actual domestic 1-minute opening candle around trade_open_at."""

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
        # Query just after the expected open. Both APIs are exclusive of `to`,
        # but Bithumb and Upbit use different timezone conventions for it.
        to = candle_query_to(name, open_at + 5 * 60)
        try:
            candles = client.candles_minutes(str(market).upper(), unit=1, count=8, to=to)
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
            **result,
        }
