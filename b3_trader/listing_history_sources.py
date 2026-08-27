from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .http_retry import get_with_retry
from .listing_history import ListingCandle
from .listing_identity import ListingIdentity, listing_identity_gate


USER_AGENT = "crypto-research-listing-history/1.0"


@dataclass(frozen=True)
class CexSpotMarket:
    exchange: str
    market: str
    base_asset: str
    quote_asset: str
    listing_at: float = 0.0
    state: str = ""
    first_price: float = 0.0
    match_confidence: float = 0.0
    match_basis: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "market": self.market,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "listing_at": self.listing_at,
            "state": self.state,
            "first_price": self.first_price,
            "match_confidence": self.match_confidence,
            "match_basis": self.match_basis or {},
        }


class SpotListingSource(Protocol):
    exchange: str

    def discover(self, identity: ListingIdentity) -> list[CexSpotMarket]: ...

    def hourly_candles(self, market: str, *, start_ts: float, end_ts: float) -> list[ListingCandle]: ...


def _require_verified(identity: ListingIdentity) -> dict[str, Any]:
    gate = listing_identity_gate(identity)
    if not gate["verified"]:
        raise ValueError("listing identity is not verified: " + ",".join(gate["reasons"]))
    return gate


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ms_to_s(value: Any) -> float:
    number = _num(value)
    return number / 1000.0 if number > 10_000_000_000 else number


class BinanceSpotSource:
    exchange = "binance"
    base_url = "https://data-api.binance.vision"
    quotes = ("USDT", "USDC", "FDUSD", "BTC")

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        response, _ = get_with_retry(
            self.base_url + path,
            headers={"User-Agent": USER_AGENT},
            params=params,
            timeout=12,
            attempts=3,
        )
        return response.json()

    def discover(self, identity: ListingIdentity) -> list[CexSpotMarket]:
        gate = _require_verified(identity)
        payload = self._get("/api/v3/exchangeInfo", {})
        rows = payload.get("symbols") if isinstance(payload, dict) else []
        result: list[CexSpotMarket] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            base = str(row.get("baseAsset") or "").upper()
            quote = str(row.get("quoteAsset") or "").upper()
            if base != identity.symbol or quote not in self.quotes:
                continue
            market = str(row.get("symbol") or "").upper()
            if not market:
                continue
            result.append(
                CexSpotMarket(
                    exchange=self.exchange,
                    market=market,
                    base_asset=base,
                    quote_asset=quote,
                    state=str(row.get("status") or ""),
                    match_confidence=float(gate["confidence"]),
                    match_basis={
                        "identity_gate": "verified",
                        "provider_id": identity.provider_id,
                        "official_domains": list(identity.official_domains),
                        "base_symbol_after_identity": True,
                    },
                )
            )
        return result

    def hourly_candles(self, market: str, *, start_ts: float, end_ts: float) -> list[ListingCandle]:
        start_ms = max(0, int(start_ts * 1000))
        end_ms = max(start_ms, int(end_ts * 1000))
        payload = self._get(
            "/api/v3/klines",
            {"symbol": market.upper(), "interval": "1h", "startTime": start_ms, "endTime": end_ms, "limit": 1000},
        )
        result: list[ListingCandle] = []
        for row in payload if isinstance(payload, list) else []:
            if not isinstance(row, list) or len(row) < 8:
                continue
            result.append(
                ListingCandle(
                    ts=_ms_to_s(row[0]),
                    open=_num(row[1]), high=_num(row[2]), low=_num(row[3]), close=_num(row[4]),
                    volume=_num(row[5]), quote_volume=_num(row[7]), interval_seconds=3600, confirmed=True,
                )
            )
        return sorted(result, key=lambda row: row.ts)

    def first_candle(self, market: str) -> ListingCandle | None:
        payload = self._get(
            "/api/v3/klines",
            {"symbol": market.upper(), "interval": "1h", "startTime": 0, "limit": 1},
        )
        rows = payload if isinstance(payload, list) else []
        if not rows or not isinstance(rows[0], list) or len(rows[0]) < 8:
            return None
        row = rows[0]
        return ListingCandle(
            ts=_ms_to_s(row[0]), open=_num(row[1]), high=_num(row[2]), low=_num(row[3]), close=_num(row[4]),
            volume=_num(row[5]), quote_volume=_num(row[7]), interval_seconds=3600, confirmed=True,
        )


class OkxSpotSource:
    exchange = "okx"
    base_url = "https://www.okx.com"
    quotes = ("USDT", "USDC", "USD", "BTC")

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response, _ = get_with_retry(
            self.base_url + path,
            headers={"User-Agent": USER_AGENT},
            params=params,
            timeout=12,
            attempts=3,
        )
        payload = response.json()
        if not isinstance(payload, dict) or str(payload.get("code") or "0") != "0":
            raise RuntimeError(f"OKX public API error: {payload}")
        return payload

    def discover(self, identity: ListingIdentity) -> list[CexSpotMarket]:
        gate = _require_verified(identity)
        payload = self._get("/api/v5/public/instruments", {"instType": "SPOT"})
        result: list[CexSpotMarket] = []
        for row in payload.get("data") or []:
            if not isinstance(row, dict):
                continue
            base = str(row.get("baseCcy") or "").upper()
            quote = str(row.get("quoteCcy") or "").upper()
            if base != identity.symbol or quote not in self.quotes:
                continue
            market = str(row.get("instId") or "").upper()
            if not market:
                continue
            list_time = _ms_to_s(row.get("contTdSwTime") or row.get("listTime"))
            result.append(
                CexSpotMarket(
                    exchange=self.exchange,
                    market=market,
                    base_asset=base,
                    quote_asset=quote,
                    listing_at=list_time,
                    state=str(row.get("state") or ""),
                    match_confidence=float(gate["confidence"]),
                    match_basis={
                        "identity_gate": "verified",
                        "provider_id": identity.provider_id,
                        "official_domains": list(identity.official_domains),
                        "base_symbol_after_identity": True,
                    },
                )
            )
        return result

    def hourly_candles(self, market: str, *, start_ts: float, end_ts: float) -> list[ListingCandle]:
        # OKX returns newest first. Passing `after=end` pages toward older data;
        # one 300-row hourly page covers the requested domestic-listing window.
        payload = self._get(
            "/api/v5/market/history-candles",
            {"instId": market.upper(), "bar": "1H", "after": str(int(end_ts * 1000) + 1), "limit": "300"},
        )
        result: list[ListingCandle] = []
        for row in payload.get("data") or []:
            if not isinstance(row, list) or len(row) < 9:
                continue
            ts = _ms_to_s(row[0])
            if ts < start_ts or ts > end_ts:
                continue
            result.append(
                ListingCandle(
                    ts=ts,
                    open=_num(row[1]), high=_num(row[2]), low=_num(row[3]), close=_num(row[4]),
                    volume=_num(row[5]), quote_volume=_num(row[7]), interval_seconds=3600,
                    confirmed=str(row[8]) == "1",
                )
            )
        return sorted(result, key=lambda row: row.ts)


class BybitSpotSource:
    exchange = "bybit"
    base_url = "https://api.bybit.com"
    quotes = ("USDT", "USDC", "BTC")

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response, _ = get_with_retry(
            self.base_url + path,
            headers={"User-Agent": USER_AGENT},
            params=params,
            timeout=12,
            attempts=3,
        )
        payload = response.json()
        if not isinstance(payload, dict) or int(payload.get("retCode") or 0) != 0:
            raise RuntimeError(f"Bybit public API error: {payload}")
        return payload

    def discover(self, identity: ListingIdentity) -> list[CexSpotMarket]:
        gate = _require_verified(identity)
        payload = self._get("/v5/market/instruments-info", {"category": "spot", "limit": 1000})
        result_data = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        result: list[CexSpotMarket] = []
        for row in result_data.get("list") or []:
            if not isinstance(row, dict):
                continue
            base = str(row.get("baseCoin") or "").upper()
            quote = str(row.get("quoteCoin") or "").upper()
            if base != identity.symbol or quote not in self.quotes:
                continue
            market = str(row.get("symbol") or "").upper()
            if not market:
                continue
            result.append(
                CexSpotMarket(
                    exchange=self.exchange,
                    market=market,
                    base_asset=base,
                    quote_asset=quote,
                    listing_at=_ms_to_s(row.get("launchTime")),
                    state=str(row.get("status") or ""),
                    match_confidence=float(gate["confidence"]),
                    match_basis={
                        "identity_gate": "verified",
                        "provider_id": identity.provider_id,
                        "official_domains": list(identity.official_domains),
                        "base_symbol_after_identity": True,
                    },
                )
            )
        return result

    def hourly_candles(self, market: str, *, start_ts: float, end_ts: float) -> list[ListingCandle]:
        payload = self._get(
            "/v5/market/kline",
            {
                "category": "spot",
                "symbol": market.upper(),
                "interval": "60",
                "start": int(start_ts * 1000),
                "end": int(end_ts * 1000),
                "limit": 1000,
            },
        )
        result_data = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        result: list[ListingCandle] = []
        for row in result_data.get("list") or []:
            if not isinstance(row, list) or len(row) < 7:
                continue
            result.append(
                ListingCandle(
                    ts=_ms_to_s(row[0]),
                    open=_num(row[1]), high=_num(row[2]), low=_num(row[3]), close=_num(row[4]),
                    volume=_num(row[5]), quote_volume=_num(row[6]), interval_seconds=3600, confirmed=True,
                )
            )
        return sorted(result, key=lambda row: row.ts)


def default_cex_sources() -> tuple[SpotListingSource, ...]:
    return (BinanceSpotSource(), OkxSpotSource(), BybitSpotSource())
