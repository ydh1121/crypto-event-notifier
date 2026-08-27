from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from .bithumb_client import BithumbClient
from .domestic_candle_utils import nearest_opening_price
from .upbit_client import UpbitClient


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
        # Query just after the expected open. Both domestic quotation APIs use
        # the same reverse-chronological candle shape inherited from Upbit.
        to = datetime.fromtimestamp(open_at + 5 * 60, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
