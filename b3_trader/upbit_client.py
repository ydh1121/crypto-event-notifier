from __future__ import annotations

from typing import Any

import requests


class UpbitClient:
    """Read-only/public Upbit quotation client used by Phase 3 research adapters."""

    BASE_URL = "https://api.upbit.com"

    def __init__(self, timeout: float = 5.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "crypto-research/phase3"})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self.session.get(self.BASE_URL + path, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def market_all(self, *, details: bool = True) -> list[dict[str, Any]]:
        data = self._get("/v1/market/all", {"is_details": "true" if details else "false"})
        return data if isinstance(data, list) else []

    def krw_markets(self, *, details: bool = True) -> list[dict[str, Any]]:
        return [row for row in self.market_all(details=details) if str(row.get("market") or "").startswith("KRW-")]

    def tickers_by_quote(self, quote_currencies: str = "KRW") -> list[dict[str, Any]]:
        data = self._get("/v1/ticker/all", {"quote_currencies": quote_currencies})
        return data if isinstance(data, list) else []

    def ticker(self, market: str) -> dict[str, Any]:
        data = self._get("/v1/ticker", {"markets": market})
        if not isinstance(data, list) or not data:
            raise RuntimeError(f"No Upbit ticker data for {market}")
        return data[0]

    def orderbook(self, market: str, *, count: int = 30) -> dict[str, Any]:
        data = self._get("/v1/orderbook", {"markets": market, "count": max(1, min(30, int(count)))})
        if not isinstance(data, list) or not data:
            raise RuntimeError(f"No Upbit orderbook data for {market}")
        return data[0]

    def candles_minutes(
        self,
        market: str,
        unit: int = 5,
        count: int = 120,
        to: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"market": market, "count": max(1, min(200, int(count)))}
        if to:
            params["to"] = to
        data = self._get(f"/v1/candles/minutes/{int(unit)}", params)
        return data if isinstance(data, list) else []
