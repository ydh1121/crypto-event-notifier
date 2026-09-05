from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from statistics import median
from typing import Any

import requests

from .strategy import ExternalFactors, clamp


DEFAULT_ALT_BASKET = (
    "KRW-XRP",
    "KRW-SOL",
    "KRW-ADA",
    "KRW-DOGE",
    "KRW-AVAX",
    "KRW-LINK",
    "KRW-SUI",
    "KRW-APT",
    "KRW-SEI",
    "KRW-PEPE",
)

DEFAULT_BASE_BASKET = (
    "KRW-AERO",
    "KRW-VIRTUAL",
    "KRW-BRETT",
    "KRW-DEGEN",
)

DEFAULT_GAMING_BASKET = (
    "KRW-IMX",
    "KRW-AXS",
    "KRW-GALA",
    "KRW-BEAM",
    "KRW-SAND",
    "KRW-MANA",
)


@dataclass(frozen=True)
class BasketResult:
    score: float
    median_return_pct: float
    positive_ratio: float
    markets: tuple[str, ...]


@dataclass(frozen=True)
class FactorSnapshot:
    factors: ExternalFactors
    details: dict[str, Any]


def _ticker_return_pct(row: dict[str, Any]) -> float:
    if row.get("signed_change_rate") is not None:
        return float(row["signed_change_rate"]) * 100.0

    rate = float(row.get("change_rate") or 0.0) * 100.0
    change = str(row.get("change") or "").upper()
    if change == "FALL":
        return -abs(rate)
    if change == "RISE":
        return abs(rate)
    return rate


def eth_btc_relative_change_pct(eth_return_pct: float, btc_return_pct: float) -> float:
    """Return the ETH/BTC relative move from independent KRW returns.

    This lets the dashboard use ETH/BTC as a market reference even when the
    exchange does not expose an ETH-BTC spot market to this KRW-only engine.
    """
    denominator = 1.0 + float(btc_return_pct) / 100.0
    if denominator <= 0:
        return 0.0
    value = ((1.0 + float(eth_return_pct) / 100.0) / denominator - 1.0) * 100.0
    return round(value, 4)


def score_basket(
    returns_pct: list[float],
    markets: list[str],
    *,
    relative_to_pct: float = 0.0,
    breadth_weight: float = 30.0,
    return_weight: float = 4.0,
) -> BasketResult:
    if not returns_pct:
        return BasketResult(50.0, 0.0, 0.5, tuple())

    med = median(returns_pct)
    positive_ratio = sum(1 for x in returns_pct if x > 0) / len(returns_pct)
    relative = med - relative_to_pct
    score = clamp(
        50.0
        + relative * return_weight
        + (positive_ratio - 0.5) * breadth_weight
    )
    return BasketResult(
        round(score, 2),
        round(med, 3),
        round(positive_ratio, 3),
        tuple(markets),
    )


class OkxDerivativesProvider:
    BASE_URL = "https://www.okx.com"

    def __init__(self, enabled: bool = True, timeout: float = 4.0) -> None:
        self.enabled = enabled
        self.timeout = timeout
        self.session = requests.Session()
        self._previous_oi_usd: float | None = None
        self._previous_oi_ts: float | None = None

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        response = self.session.get(
            self.BASE_URL + path,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("code", "0")) != "0":
            raise RuntimeError(f"OKX error: {payload.get('msg')}")
        return payload

    def _funding_rate(self, inst_id: str) -> float:
        payload = self._get("/api/v5/public/funding-rate", {"instId": inst_id})
        rows = payload.get("data") or []
        return float(rows[0].get("fundingRate") or 0.0) if rows else 0.0

    def _open_interest_usd(self, inst_id: str) -> float:
        payload = self._get(
            "/api/v5/public/open-interest",
            {"instType": "SWAP", "instId": inst_id},
        )
        rows = payload.get("data") or []
        if not rows:
            return 0.0
        row = rows[0]
        for key in ("oiUsd", "oiCcy", "oi"):
            value = row.get(key)
            if value not in (None, ""):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return 0.0

    @staticmethod
    def _funding_score(rate: float) -> float:
        if rate < -0.0010:
            return 20.0
        if rate < -0.0003:
            return 35.0
        if rate <= 0.0003:
            return 65.0
        if rate <= 0.0008:
            return 50.0
        if rate <= 0.0015:
            return 30.0
        return 15.0

    def snapshot(self) -> tuple[float, dict[str, Any]]:
        if not self.enabled:
            return 50.0, {"enabled": False}

        try:
            btc_funding = self._funding_rate("BTC-USDT-SWAP")
            eth_funding = self._funding_rate("ETH-USDT-SWAP")
            btc_oi = self._open_interest_usd("BTC-USDT-SWAP")
            eth_oi = self._open_interest_usd("ETH-USDT-SWAP")
            total_oi = btc_oi + eth_oi

            funding_score = (
                self._funding_score(btc_funding) + self._funding_score(eth_funding)
            ) / 2.0

            oi_change_pct: float | None = None
            oi_score = 50.0
            now = time.time()
            if self._previous_oi_usd and self._previous_oi_usd > 0 and total_oi > 0:
                oi_change_pct = (total_oi / self._previous_oi_usd - 1.0) * 100.0
                oi_score = clamp(50.0 + oi_change_pct * 8.0)

            if total_oi > 0:
                self._previous_oi_usd = total_oi
                self._previous_oi_ts = now

            score = clamp(0.65 * funding_score + 0.35 * oi_score)
            details = {
                "enabled": True,
                "btc_funding": btc_funding,
                "eth_funding": eth_funding,
                "btc_oi": btc_oi,
                "eth_oi": eth_oi,
                "oi_change_pct": round(oi_change_pct, 4) if oi_change_pct is not None else None,
                "score": round(score, 2),
            }
            return round(score, 2), details
        except Exception as exc:
            return 50.0, {
                "enabled": True,
                "fallback": "neutral",
                "error": f"{type(exc).__name__}: {exc}",
            }


class MarketFactorProvider:
    def __init__(
        self,
        client: Any,
        *,
        okx_enabled: bool = True,
        news_modifier: float = 0.0,
    ) -> None:
        self.client = client
        self.news_modifier = max(-20.0, min(20.0, news_modifier))
        self.okx = OkxDerivativesProvider(enabled=okx_enabled)
        self._available_markets: set[str] = set()
        self._available_markets_at = 0.0

    def _refresh_available_markets(self) -> None:
        now = time.time()
        if self._available_markets and now - self._available_markets_at < 3600:
            return
        rows = self.client.market_all()
        self._available_markets = {
            str(row.get("market", "")).upper()
            for row in rows
            if str(row.get("market", "")).startswith("KRW-")
        }
        self._available_markets_at = now

    def _available(self, candidates: tuple[str, ...]) -> list[str]:
        self._refresh_available_markets()
        return [market for market in candidates if market in self._available_markets]

    def _returns(self, markets: list[str]) -> list[float]:
        if not markets:
            return []
        rows = self.client.tickers(markets)
        by_market = {str(row.get("market", "")).upper(): row for row in rows}
        values: list[float] = []
        for market in markets:
            row = by_market.get(market)
            if row is not None:
                values.append(_ticker_return_pct(row))
        return values

    def snapshot(self) -> FactorSnapshot:
        major_rows = self.client.tickers(["KRW-BTC", "KRW-ETH"])
        majors_by_market = {
            str(row.get("market", "")).upper(): row for row in major_rows
        }
        btc_row = majors_by_market.get("KRW-BTC") or {}
        eth_row = majors_by_market.get("KRW-ETH") or {}
        btc_return = _ticker_return_pct(btc_row) if btc_row else 0.0
        eth_return = _ticker_return_pct(eth_row) if eth_row else 0.0
        major_values = [
            value
            for row, value in ((btc_row, btc_return), (eth_row, eth_return))
            if row
        ]
        major_return = sum(major_values) / len(major_values) if major_values else 0.0
        btc_price = float(btc_row.get("trade_price") or 0.0) if btc_row else 0.0
        eth_price = float(eth_row.get("trade_price") or 0.0) if eth_row else 0.0
        eth_btc_ratio = eth_price / btc_price if btc_price > 0 and eth_price > 0 else None
        eth_btc_change = eth_btc_relative_change_pct(eth_return, btc_return)

        alt_markets = self._available(DEFAULT_ALT_BASKET)
        base_markets = self._available(DEFAULT_BASE_BASKET)
        gaming_markets = self._available(DEFAULT_GAMING_BASKET)

        alt = score_basket(
            self._returns(alt_markets),
            alt_markets,
            relative_to_pct=major_return,
            breadth_weight=40.0,
            return_weight=3.0,
        )
        base = score_basket(
            self._returns(base_markets),
            base_markets,
            relative_to_pct=major_return,
            breadth_weight=30.0,
            return_weight=4.5,
        )
        gaming = score_basket(
            self._returns(gaming_markets),
            gaming_markets,
            relative_to_pct=major_return,
            breadth_weight=30.0,
            return_weight=4.5,
        )

        derivatives_score, derivatives_details = self.okx.snapshot()
        factors = ExternalFactors(
            alt_breadth=alt.score,
            base_strength=base.score,
            gaming_strength=gaming.score,
            derivatives_risk_on=derivatives_score,
            news_modifier=self.news_modifier,
        )
        return FactorSnapshot(
            factors=factors,
            details={
                "major_24h_return_pct": round(major_return, 3),
                "btc_24h_return_pct": round(btc_return, 3),
                "eth_24h_return_pct": round(eth_return, 3),
                "eth_btc_ratio": round(eth_btc_ratio, 10) if eth_btc_ratio is not None else None,
                "eth_btc_24h_change_pct": eth_btc_change,
                "alt": asdict(alt),
                "base": asdict(base),
                "gaming": asdict(gaming),
                "derivatives": derivatives_details,
                "news_modifier": self.news_modifier,
            },
        )
