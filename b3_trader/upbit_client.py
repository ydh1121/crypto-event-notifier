from __future__ import annotations

import threading
import time
from typing import Any

import requests


class UpbitClient:
    """Read-only/public Upbit quotation client used by Phase 3 research adapters."""

    BASE_URL = "https://api.upbit.com"
    # Quotation APIs are grouped by endpoint family. Keep a little headroom below
    # the documented 10 req/s group limits instead of relying on engine sleeps.
    MIN_GROUP_INTERVAL_SECONDS = 0.11

    def __init__(self, timeout: float = 5.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "crypto-research/phase3"})
        self._rate_lock = threading.Lock()
        self._last_group_request: dict[str, float] = {}

    @staticmethod
    def _group(path: str) -> str:
        if path.startswith("/v1/candles/"):
            return "candles"
        if path.startswith("/v1/orderbook"):
            return "orderbook"
        if path.startswith("/v1/ticker"):
            return "ticker"
        return "market"

    def _throttle(self, group: str) -> None:
        while True:
            with self._rate_lock:
                now = time.monotonic()
                last = self._last_group_request.get(group, 0.0)
                wait = self.MIN_GROUP_INTERVAL_SECONDS - (now - last)
                if wait <= 0:
                    self._last_group_request[group] = now
                    return
            time.sleep(min(wait, self.MIN_GROUP_INTERVAL_SECONDS))

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self._throttle(self._group(path))
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

    def candles_days(
        self,
        market: str,
        count: int = 120,
        to: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"market": market, "count": max(1, min(200, int(count)))}
        if to:
            params["to"] = to
        data = self._get("/v1/candles/days", params)
        return data if isinstance(data, list) else []