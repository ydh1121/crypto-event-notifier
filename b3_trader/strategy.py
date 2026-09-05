from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import pstdev
from typing import Any


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def scale(value: float, bad: float, good: float) -> float:
    if good == bad:
        return 50.0
    return clamp((value - bad) / (good - bad) * 100.0)


def candle_closes(candles: list[dict[str, Any]]) -> list[float]:
    # Bithumb returns newest first. Convert to oldest -> newest.
    return [float(row["trade_price"]) for row in reversed(candles)]


def return_pct(prices: list[float]) -> float:
    if len(prices) < 2 or prices[0] <= 0:
        return 0.0
    return (prices[-1] / prices[0] - 1.0) * 100.0


def realized_volatility(prices: list[float]) -> float:
    if len(prices) < 3:
        return 0.0
    rets = []
    for prev, cur in zip(prices, prices[1:]):
        if prev > 0:
            rets.append((cur / prev - 1.0) * 100.0)
    return pstdev(rets) if len(rets) >= 2 else 0.0


@dataclass
class ExternalFactors:
    # 0 = strongly bearish, 50 = neutral, 100 = strongly bullish
    alt_breadth: float = 50.0
    base_strength: float = 50.0
    gaming_strength: float = 50.0
    derivatives_risk_on: float = 50.0
    news_modifier: float = 0.0  # -20 .. +20 points applied after weighted score


@dataclass
class SignalSnapshot:
    regime_score: float
    entry_score: float
    btc_return_pct: float
    eth_return_pct: float
    b3_return_pct: float
    eth_vs_btc_pct: float
    b3_vs_majors_pct: float
    orderbook_imbalance: float
    pullback_pct: float
    volatility_pct: float
    fib_retrace: float | None
    action: str
    reason: str


class B3Strategy:
    def score(
        self,
        btc_candles: list[dict[str, Any]],
        eth_candles: list[dict[str, Any]],
        b3_candles: list[dict[str, Any]],
        orderbook: dict[str, Any],
        external: ExternalFactors | None = None,
    ) -> SignalSnapshot:
        external = external or ExternalFactors()

        btc = candle_closes(btc_candles)
        eth = candle_closes(eth_candles)
        b3 = candle_closes(b3_candles)

        btc_ret = return_pct(btc)
        eth_ret = return_pct(eth)
        b3_ret = return_pct(b3)
        eth_vs_btc = eth_ret - btc_ret
        b3_vs_majors = b3_ret - (btc_ret + eth_ret) / 2.0

        # RegimeScore separates broad risk-on conditions from the price entry itself.
        regime = (
            0.16 * scale(btc_ret, -4.0, 5.0)
            + 0.16 * scale(eth_ret, -5.0, 7.0)
            + 0.12 * scale(eth_vs_btc, -3.0, 4.0)
            + 0.16 * scale(b3_vs_majors, -8.0, 12.0)
            + 0.10 * clamp(external.alt_breadth)
            + 0.10 * clamp(external.base_strength)
            + 0.10 * clamp(external.gaming_strength)
            + 0.10 * clamp(external.derivatives_risk_on)
        )
        regime = clamp(regime + max(-20.0, min(20.0, external.news_modifier)))

        current = b3[-1]
        recent_high = max(b3) if b3 else current
        recent_low = min(b3) if b3 else current
        pullback_pct = ((recent_high - current) / recent_high * 100.0) if recent_high > 0 else 0.0
        volatility = realized_volatility(b3)

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
            targets = [0.382, 0.500, 0.618]
            distance = min(abs(fib_retrace - target) for target in targets)
            # Full credit directly on 38.2/50/61.8, fades by ~0.15 retracement distance.
            fib_score = clamp(100.0 - distance / 0.15 * 100.0)

        # Prefer constructive pullbacks. 0% pullback is chase-risk, 6~18% is generally better.
        if pullback_pct < 2.0:
            pullback_score = 25.0
        elif pullback_pct <= 18.0:
            pullback_score = scale(pullback_pct, 2.0, 12.0)
        elif pullback_pct <= 30.0:
            pullback_score = scale(30.0 - pullback_pct, 0.0, 12.0)
        else:
            pullback_score = 10.0

        momentum_score = scale(b3_ret, -8.0, 12.0)
        orderbook_score = scale(imbalance, -0.25, 0.25)
        volatility_score = 100.0 - scale(volatility, 0.5, 4.5)

        entry = clamp(
            0.28 * pullback_score
            + 0.24 * fib_score
            + 0.18 * orderbook_score
            + 0.16 * momentum_score
            + 0.14 * volatility_score
        )

        if regime >= 65 and entry >= 68:
            action = "BUY_CANDIDATE"
            reason = "broad regime and entry quality are both constructive"
        elif regime < 50:
            action = "RISK_OFF"
            reason = "broad market regime is not supportive"
        elif regime >= 70 and entry < 50:
            action = "WAIT_PULLBACK"
            reason = "market is strong but the current B3 entry is unattractive"
        else:
            action = "WATCH"
            reason = "conditions are mixed or below execution thresholds"

        values = [regime, entry, btc_ret, eth_ret, b3_ret, imbalance, pullback_pct, volatility]
        if not all(isfinite(v) for v in values):
            raise RuntimeError("Non-finite strategy value detected")

        return SignalSnapshot(
            regime_score=round(regime, 2),
            entry_score=round(entry, 2),
            btc_return_pct=round(btc_ret, 3),
            eth_return_pct=round(eth_ret, 3),
            b3_return_pct=round(b3_ret, 3),
            eth_vs_btc_pct=round(eth_vs_btc, 3),
            b3_vs_majors_pct=round(b3_vs_majors, 3),
            orderbook_imbalance=round(imbalance, 4),
            pullback_pct=round(pullback_pct, 3),
            volatility_pct=round(volatility, 4),
            fib_retrace=round(fib_retrace, 4) if fib_retrace is not None else None,
            action=action,
            reason=reason,
        )
