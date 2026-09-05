from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .bithumb_client import BithumbClient
from .upbit_client import UpbitClient


@dataclass(frozen=True)
class PublicMarket:
    exchange: str
    market: str
    symbol: str
    name: str
    warning: bool = False


class PublicExchangeAdapter(Protocol):
    exchange: str

    def krw_markets(self) -> list[PublicMarket]: ...
    def krw_tickers(self) -> list[dict[str, Any]]: ...
    def candles_minutes(self, market: str, unit: int = 5, count: int = 120) -> list[dict[str, Any]]: ...
    def candles_days(self, market: str, count: int = 120) -> list[dict[str, Any]]: ...
    def recent_trades(self, market: str, count: int = 200, cursor: str | None = None) -> list[dict[str, Any]]: ...
    def orderbook(self, market: str) -> dict[str, Any]: ...


class BithumbPublicAdapter:
    exchange = "bithumb"

    def __init__(self, client: BithumbClient | None = None) -> None:
        self.client = client or BithumbClient()

    def krw_markets(self) -> list[PublicMarket]:
        result: list[PublicMarket] = []
        for row in self.client.market_all():
            market = str(row.get("market") or "")
            if not market.startswith("KRW-"):
                continue
            result.append(
                PublicMarket(
                    exchange=self.exchange,
                    market=market,
                    symbol=market.removeprefix("KRW-"),
                    name=str(row.get("korean_name") or row.get("english_name") or market),
                    warning=bool(row.get("market_warning") and str(row.get("market_warning")).upper() != "NONE"),
                )
            )
        return result

    def krw_tickers(self) -> list[dict[str, Any]]:
        markets = [row.market for row in self.krw_markets()]
        output: list[dict[str, Any]] = []
        for offset in range(0, len(markets), 70):
            output.extend(self.client.tickers(markets[offset : offset + 70]))
        return output

    def candles_minutes(self, market: str, unit: int = 5, count: int = 120) -> list[dict[str, Any]]:
        return self.client.candles_minutes(market, unit=unit, count=count)

    def candles_days(self, market: str, count: int = 120) -> list[dict[str, Any]]:
        return self.client.candles_days(market, count=count)

    def recent_trades(self, market: str, count: int = 200, cursor: str | None = None) -> list[dict[str, Any]]:
        return self.client.trades_ticks(market, count=count, cursor=cursor)

    def orderbook(self, market: str) -> dict[str, Any]:
        return self.client.orderbook(market)


class UpbitPublicAdapter:
    exchange = "upbit"

    def __init__(self, client: UpbitClient | None = None) -> None:
        self.client = client or UpbitClient()

    @staticmethod
    def _warning(row: dict[str, Any]) -> bool:
        event = row.get("market_event") if isinstance(row.get("market_event"), dict) else {}
        caution = event.get("caution") if isinstance(event.get("caution"), dict) else {}
        return bool(event.get("warning")) or any(bool(value) for value in caution.values())

    def krw_markets(self) -> list[PublicMarket]:
        result: list[PublicMarket] = []
        for row in self.client.krw_markets(details=True):
            market = str(row.get("market") or "")
            result.append(
                PublicMarket(
                    exchange=self.exchange,
                    market=market,
                    symbol=market.removeprefix("KRW-"),
                    name=str(row.get("korean_name") or row.get("english_name") or market),
                    warning=self._warning(row),
                )
            )
        return result

    def krw_tickers(self) -> list[dict[str, Any]]:
        return [row for row in self.client.tickers_by_quote("KRW") if str(row.get("market") or "").startswith("KRW-")]

    def candles_minutes(self, market: str, unit: int = 5, count: int = 120) -> list[dict[str, Any]]:
        return self.client.candles_minutes(market, unit=unit, count=count)

    def candles_days(self, market: str, count: int = 120) -> list[dict[str, Any]]:
        return self.client.candles_days(market, count=count)

    def recent_trades(self, market: str, count: int = 200, cursor: str | None = None) -> list[dict[str, Any]]:
        return self.client.trades_ticks(market, count=count, cursor=cursor)

    def orderbook(self, market: str) -> dict[str, Any]:
        return self.client.orderbook(market)


def public_exchange(name: str) -> PublicExchangeAdapter:
    normalized = str(name or "").strip().lower()
    if normalized == "bithumb":
        return BithumbPublicAdapter()
    if normalized == "upbit":
        return UpbitPublicAdapter()
    raise ValueError(f"unsupported public exchange: {name}")
