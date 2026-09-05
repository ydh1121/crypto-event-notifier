from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class ExecutionRisk:
    allowed: bool
    reasons: list[str]
    spread_bps: float
    estimated_slippage_bps: float
    estimated_fill_price: float
    btc_flash_move_pct: float
    order_krw: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _levels(orderbook: dict[str, Any]) -> list[dict[str, Any]]:
    return list(orderbook.get("orderbook_units") or [])


def spread_bps(orderbook: dict[str, Any]) -> float:
    levels = _levels(orderbook)
    if not levels:
        return float("inf")
    best_bid = float(levels[0].get("bid_price") or 0.0)
    best_ask = float(levels[0].get("ask_price") or 0.0)
    mid = (best_bid + best_ask) / 2.0
    if best_bid <= 0 or best_ask <= 0 or mid <= 0:
        return float("inf")
    return max(0.0, (best_ask - best_bid) / mid * 10_000.0)


def _estimate_fill(
    orderbook: dict[str, Any],
    *,
    side: str,
    krw_amount: float | None = None,
    volume: float | None = None,
) -> tuple[float, float]:
    levels = _levels(orderbook)
    if not levels:
        return float("inf"), float("inf")

    if side == "buy":
        if krw_amount is None or krw_amount <= 0:
            raise ValueError("krw_amount must be positive for buy estimation")
        remaining_krw = krw_amount
        total_volume = 0.0
        total_cost = 0.0
        best = float(levels[0].get("ask_price") or 0.0)
        for row in levels:
            price = float(row.get("ask_price") or 0.0)
            size = float(row.get("ask_size") or 0.0)
            if price <= 0 or size <= 0:
                continue
            level_cost = price * size
            take_cost = min(remaining_krw, level_cost)
            take_volume = take_cost / price
            total_cost += take_cost
            total_volume += take_volume
            remaining_krw -= take_cost
            if remaining_krw <= 1e-9:
                break
        if remaining_krw > max(1.0, krw_amount * 0.001) or total_volume <= 0 or best <= 0:
            return float("inf"), float("inf")
        avg = total_cost / total_volume
        slip = max(0.0, (avg / best - 1.0) * 10_000.0)
        return avg, slip

    if side == "sell":
        if volume is None or volume <= 0:
            raise ValueError("volume must be positive for sell estimation")
        remaining = volume
        proceeds = 0.0
        filled = 0.0
        best = float(levels[0].get("bid_price") or 0.0)
        for row in levels:
            price = float(row.get("bid_price") or 0.0)
            size = float(row.get("bid_size") or 0.0)
            if price <= 0 or size <= 0:
                continue
            take = min(remaining, size)
            proceeds += take * price
            filled += take
            remaining -= take
            if remaining <= 1e-12:
                break
        if remaining > max(1e-12, volume * 0.001) or filled <= 0 or best <= 0:
            return float("inf"), float("inf")
        avg = proceeds / filled
        slip = max(0.0, (1.0 - avg / best) * 10_000.0)
        return avg, slip

    raise ValueError(f"unsupported side: {side}")


def estimate_buy(orderbook: dict[str, Any], krw_amount: float) -> tuple[float, float]:
    return _estimate_fill(orderbook, side="buy", krw_amount=krw_amount)


def estimate_sell(orderbook: dict[str, Any], volume: float) -> tuple[float, float]:
    return _estimate_fill(orderbook, side="sell", volume=volume)


def recent_move_pct(candles: list[dict[str, Any]], window: int) -> float:
    if not candles:
        return 0.0
    ordered = list(reversed(candles))  # oldest -> newest
    closes = [float(row["trade_price"]) for row in ordered]
    window = max(1, min(window, len(closes) - 1))
    if len(closes) < 2 or closes[-1 - window] <= 0:
        return 0.0
    return (closes[-1] / closes[-1 - window] - 1.0) * 100.0


class OrderRateLimiter:
    def __init__(self, per_minute: int, per_hour: int) -> None:
        self.per_minute = max(1, int(per_minute))
        self.per_hour = max(self.per_minute, int(per_hour))
        self._times: deque[float] = deque()

    def _prune(self, now: float) -> None:
        while self._times and now - self._times[0] > 3600.0:
            self._times.popleft()

    def allowed(self, now: float | None = None) -> tuple[bool, str]:
        now = time.time() if now is None else now
        self._prune(now)
        per_minute = sum(1 for ts in self._times if now - ts <= 60.0)
        if per_minute >= self.per_minute:
            return False, "max orders per minute reached"
        if len(self._times) >= self.per_hour:
            return False, "max orders per hour reached"
        return True, "ok"

    def record(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self._prune(now)
        self._times.append(now)


def adaptive_order_krw(
    base_order_krw: float,
    *,
    regime_score: float,
    entry_score: float,
    min_multiplier: float,
    max_multiplier: float,
) -> float:
    # Position size only increases when both dimensions are strong.
    regime_component = max(0.0, min(1.0, (regime_score - 55.0) / 35.0))
    entry_component = max(0.0, min(1.0, (entry_score - 55.0) / 35.0))
    confidence = (regime_component * entry_component) ** 0.5
    multiplier = min_multiplier + (max_multiplier - min_multiplier) * confidence
    return max(0.0, base_order_krw * multiplier)


class ExecutionGuard:
    def __init__(
        self,
        *,
        max_spread_bps: float,
        max_slippage_bps: float,
        btc_flash_crash_pct: float,
        btc_flash_window_candles: int,
        rate_limiter: OrderRateLimiter,
    ) -> None:
        self.max_spread_bps = float(max_spread_bps)
        self.max_slippage_bps = float(max_slippage_bps)
        self.btc_flash_crash_pct = float(btc_flash_crash_pct)
        self.btc_flash_window_candles = int(btc_flash_window_candles)
        self.rate_limiter = rate_limiter

    def evaluate_buy(
        self,
        *,
        orderbook: dict[str, Any],
        btc_candles: list[dict[str, Any]],
        order_krw: float,
        now: float | None = None,
    ) -> ExecutionRisk:
        reasons: list[str] = []
        spread = spread_bps(orderbook)
        fill_price, slippage = estimate_buy(orderbook, order_krw)
        btc_move = recent_move_pct(btc_candles, self.btc_flash_window_candles)

        if not isfinite(spread) or spread > self.max_spread_bps:
            reasons.append(f"spread too wide: {spread:.2f} bps")
        if not isfinite(slippage) or slippage > self.max_slippage_bps:
            reasons.append(f"estimated slippage too high: {slippage:.2f} bps")
        if btc_move <= self.btc_flash_crash_pct:
            reasons.append(f"BTC flash-crash guard: {btc_move:.2f}%")

        rate_ok, rate_reason = self.rate_limiter.allowed(now)
        if not rate_ok:
            reasons.append(rate_reason)

        return ExecutionRisk(
            allowed=not reasons,
            reasons=reasons,
            spread_bps=round(spread, 3) if isfinite(spread) else spread,
            estimated_slippage_bps=round(slippage, 3) if isfinite(slippage) else slippage,
            estimated_fill_price=round(fill_price, 12) if isfinite(fill_price) else fill_price,
            btc_flash_move_pct=round(btc_move, 4),
            order_krw=round(order_krw, 2),
        )
