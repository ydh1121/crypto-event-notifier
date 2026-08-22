from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import jwt
import requests


class BithumbClient:
    BASE_URL = "https://api.bithumb.com"

    def __init__(self, access_key: str = "", secret_key: str = "", timeout: float = 5.0):
        self.access_key = access_key
        self.secret_key = secret_key
        self.timeout = timeout
        self.session = requests.Session()

    def _jwt_token(self, params: dict[str, Any] | None = None) -> str:
        if not self.access_key or not self.secret_key:
            raise RuntimeError("Bithumb private API credentials are not configured")

        payload: dict[str, Any] = {
            "access_key": self.access_key,
            "nonce": str(uuid.uuid4()),
            "timestamp": round(time.time() * 1000),
        }

        if params:
            query = urlencode(params, doseq=True)
            payload["query_hash"] = hashlib.sha512(query.encode("utf-8")).hexdigest()
            payload["query_hash_alg"] = "SHA512"

        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def authorization_header(self, params: dict[str, Any] | None = None) -> str:
        return f"Bearer {self._jwt_token(params)}"

    def _jwt_headers(self, params: dict[str, Any] | None = None) -> dict[str, str]:
        return {
            "Authorization": self.authorization_header(params),
            "Content-Type": "application/json; charset=utf-8",
        }

    def _get(self, path: str, params: dict[str, Any] | None = None, private: bool = False) -> Any:
        headers = self._jwt_headers(params) if private else None
        response = self.session.get(
            self.BASE_URL + path,
            params=params,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def market_all(self) -> list[dict[str, Any]]:
        return self._get("/v1/market/all")

    def ticker(self, market: str) -> dict[str, Any]:
        data = self.tickers([market])
        if not data:
            raise RuntimeError(f"No ticker data for {market}")
        return data[0]

    def tickers(self, markets: list[str]) -> list[dict[str, Any]]:
        if not markets:
            return []
        return self._get("/v1/ticker", {"markets": ",".join(markets)})

    def orderbook(self, market: str) -> dict[str, Any]:
        data = self._get("/v1/orderbook", {"markets": market})
        if not data:
            raise RuntimeError(f"No orderbook data for {market}")
        return data[0]

    def candles_minutes(
        self,
        market: str,
        unit: int = 5,
        count: int = 120,
        to: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"market": market, "count": count}
        if to:
            params["to"] = to
        return self._get(f"/v1/candles/minutes/{unit}", params)

    def order_chance(self, market: str) -> dict[str, Any]:
        return self._get("/v1/orders/chance", {"market": market}, private=True)

    def place_order(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = self._jwt_headers(body)
        response = self.session.post(
            self.BASE_URL + "/v2/orders",
            json=body,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def buy_market_krw(self, market: str, krw_amount: float, client_order_id: str) -> dict[str, Any]:
        return self.place_order(
            {
                "market": market,
                "side": "bid",
                "price": str(int(krw_amount)),
                "order_type": "price",
                "client_order_id": client_order_id,
            }
        )

    def sell_market(self, market: str, volume: float, client_order_id: str) -> dict[str, Any]:
        return self.place_order(
            {
                "market": market,
                "side": "ask",
                "volume": format(volume, ".12f").rstrip("0").rstrip("."),
                "order_type": "market",
                "client_order_id": client_order_id,
            }
        )
