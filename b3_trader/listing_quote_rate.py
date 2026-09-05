from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from .bithumb_client import BithumbClient
from .domestic_candle_utils import quote_rate_at_or_before
from .upbit_client import UpbitClient


class MinuteCandleClient(Protocol):
    def candles_minutes(self, market: str, unit: int = 5, count: int = 120, to: str | None = None) -> list[dict[str, Any]]: ...


QUOTE_MARKETS = {
    "USDT": "KRW-USDT",
    "USDC": "KRW-USDC",
    "BTC": "KRW-BTC",
}


class ListingQuoteRateResolver:
    """Resolve a foreign CEX quote asset into KRW at domestic listing time.

    No stablecoin parity is invented. If a public KRW quote market is not
    available, the conversion stays unavailable and domestic premium remains
    null rather than mixing USDT/BTC/USD numerics directly with KRW.
    """

    def __init__(
        self,
        *,
        bithumb: MinuteCandleClient | None = None,
        upbit: MinuteCandleClient | None = None,
    ) -> None:
        self.clients: tuple[tuple[str, MinuteCandleClient], ...] = (
            ("bithumb", bithumb or BithumbClient()),
            ("upbit", upbit or UpbitClient()),
        )

    def resolve(self, quote_asset: str, target_ts: float) -> dict[str, Any]:
        quote = str(quote_asset or "").upper()
        if target_ts <= 0:
            return {"status": "target_time_missing", "found": False, "rate": 0.0, "quote_asset": quote}
        if quote == "KRW":
            return {
                "status": "identity",
                "found": True,
                "rate": 1.0,
                "quote_asset": quote,
                "source_exchange": "identity",
                "source_market": "KRW",
                "candle_ts": float(target_ts),
                "lag_seconds": 0.0,
            }
        market = QUOTE_MARKETS.get(quote)
        if not market:
            return {
                "status": "unsupported_quote",
                "found": False,
                "rate": 0.0,
                "quote_asset": quote,
            }

        to = datetime.fromtimestamp(target_ts + 3 * 60, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        errors: list[str] = []
        for exchange, client in self.clients:
            try:
                candles = client.candles_minutes(market, unit=1, count=8, to=to)
            except Exception as exc:
                errors.append(f"{exchange}:{type(exc).__name__}:{exc}"[:180])
                continue
            result = quote_rate_at_or_before(candles, target_ts=target_ts, max_lag_seconds=180)
            if result.get("found") and float(result.get("rate") or 0) > 0:
                return {
                    "status": "resolved",
                    "found": True,
                    "quote_asset": quote,
                    "source_exchange": exchange,
                    "source_market": market,
                    **result,
                }
        return {
            "status": "rate_not_found",
            "found": False,
            "rate": 0.0,
            "quote_asset": quote,
            "source_market": market,
            "errors": errors[:2],
        }
