from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from .strategy import candle_closes, clamp, realized_volatility, return_pct, scale


@dataclass
class AssetExternalFactors:
    alt_breadth: float = 50.0
    context_strength: float = 50.0
    derivatives_risk_on: float = 50.0
    news_modifier: float = 0.0


@dataclass
class AssetSignal:
    regime_score: float
    entry_score: float
    btc_return_pct: float
    eth_return_pct: float
    asset_return_pct: float
    eth_vs_btc_pct: float
    asset_vs_majors_pct: float
    orderbook_imbalance: float
    pullback_pct: float
    volatility_pct: float
    fib_retrace: float | None
    action: str
    reason: str


class AssetStrategy:
    """B3-style market-regime + entry-quality model generalized to any KRW asset."""

    def score(self, btc_candles: list[dict[str, Any]], eth_candles: list[dict[str, Any]], asset_candles: list[dict[str, Any]], orderbook: dict[str, Any], external: AssetExternalFactors | None = None) -> AssetSignal:
        external = external or AssetExternalFactors()
        btc = candle_closes(btc_candles)
        eth = candle_closes(eth_candles)
        asset = candle_closes(asset_candles)
        btc_ret = return_pct(btc)
        eth_ret = return_pct(eth)
        asset_ret = return_pct(asset)
        eth_vs_btc = eth_ret - btc_ret
        asset_vs_majors = asset_ret - (btc_ret + eth_ret) / 2.0
        regime = (
            0.16 * scale(btc_ret, -4.0, 5.0)
            + 0.16 * scale(eth_ret, -5.0, 7.0)
            + 0.12 * scale(eth_vs_btc, -3.0, 4.0)
            + 0.16 * scale(asset_vs_majors, -8.0, 12.0)
            + 0.10 * clamp(external.alt_breadth)
            + 0.15 * clamp(external.context_strength)
            + 0.15 * clamp(external.derivatives_risk_on)
        )
        regime = clamp(regime + max(-20.0, min(20.0, external.news_modifier)))

        current = asset[-1]
        recent_high = max(asset)
        recent_low = min(asset)
        pullback_pct = ((recent_high - current) / recent_high * 100.0) if recent_high > 0 else 0.0
        volatility = realized_volatility(asset)
        units = orderbook.get("orderbook_units", [])[:5]
        bid_size = sum(float(x.get("bid_size", 0.0)) for x in units)
        ask_size = sum(float(x.get("ask_size", 0.0)) for x in units)
        total_size = bid_size + ask_size
        imbalance = (bid_size - ask_size) / total_size if total_size > 0 else 0.0
        fib_retrace = None
        fib_score = 50.0
        swing = recent_high - recent_low
        if swing > 0 and current <= recent_high:
            fib_retrace = (recent_high - current) / swing
            distance = min(abs(fib_retrace - target) for target in (0.382, 0.500, 0.618))
            fib_score = clamp(100.0 - distance / 0.15 * 100.0)
        if pullback_pct < 2.0:
            pullback_score = 25.0
        elif pullback_pct <= 18.0:
            pullback_score = scale(pullback_pct, 2.0, 12.0)
        elif pullback_pct <= 30.0:
            pullback_score = scale(30.0 - pullback_pct, 0.0, 12.0)
        else:
            pullback_score = 10.0
        momentum_score = scale(asset_ret, -8.0, 12.0)
        orderbook_score = scale(imbalance, -0.25, 0.25)
        volatility_score = 100.0 - scale(volatility, 0.5, 4.5)
        entry = clamp(0.28 * pullback_score + 0.24 * fib_score + 0.18 * orderbook_score + 0.16 * momentum_score + 0.14 * volatility_score)
        if regime >= 65 and entry >= 68:
            action, reason = "BUY_CANDIDATE", "broad regime and entry quality are both constructive"
        elif regime < 50:
            action, reason = "RISK_OFF", "broad market regime is not supportive"
        elif regime >= 70 and entry < 50:
            action, reason = "WAIT_PULLBACK", "market is strong but the current entry is unattractive"
        else:
            action, reason = "WATCH", "conditions are mixed or below execution thresholds"
        values = [regime, entry, btc_ret, eth_ret, asset_ret, imbalance, pullback_pct, volatility]
        if not all(isfinite(value) for value in values):
            raise RuntimeError("Non-finite strategy value detected")
        return AssetSignal(
            regime_score=round(regime, 2), entry_score=round(entry, 2), btc_return_pct=round(btc_ret, 3),
            eth_return_pct=round(eth_ret, 3), asset_return_pct=round(asset_ret, 3), eth_vs_btc_pct=round(eth_vs_btc, 3),
            asset_vs_majors_pct=round(asset_vs_majors, 3), orderbook_imbalance=round(imbalance, 4),
            pullback_pct=round(pullback_pct, 3), volatility_pct=round(volatility, 4),
            fib_retrace=round(fib_retrace, 4) if fib_retrace is not None else None, action=action, reason=reason,
        )
