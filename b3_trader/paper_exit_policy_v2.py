from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .paper_position_plan_v2 import PositionPlanV2


@dataclass(frozen=True)
class ExitDecision:
    action: str
    reason: str
    trigger_price: float
    paper_only: bool = True
    can_place_real_orders: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, float(value)))


def target_profit_pct(*, entry_opportunity: float, entry_regime: float) -> float:
    value = 8.0 + max(0.0, float(entry_opportunity) - 58.0) * 0.15
    value += max(0.0, float(entry_regime) - 50.0) * 0.05
    return round(_clamp(value, 8.0, 14.0), 3)


def evaluate_exit(
    plan: PositionPlanV2,
    *,
    average_price: float,
    current_price: float,
    peak_price: float,
    current_regime_score: float,
    current_opportunity_score: float,
    holding_seconds: float,
    entry_opportunity_score: float,
    entry_regime_score: float,
) -> ExitDecision:
    """Bounded PAPER exit policy for the shared-capital v2 plan.

    The order is deliberate: thesis invalidation first, then market weakness,
    take-profit/trailing protection, and finally a stale-position time exit.
    It has no authority to place a real order.
    """

    avg = float(average_price)
    price = float(current_price)
    peak = max(float(peak_price), price)
    if avg <= 0 or price <= 0:
        return ExitDecision("blocked", "invalid_position_price", 0.0)

    if price <= float(plan.invalidation_price):
        return ExitDecision("sell", "thesis_invalidation_price_breached", float(plan.invalidation_price))

    pnl_pct = (price / avg - 1.0) * 100.0
    if float(current_regime_score) < float(plan.thesis_regime_floor) and pnl_pct < 0.0:
        return ExitDecision("sell", "thesis_regime_floor_breached", price)

    target_pct = target_profit_pct(
        entry_opportunity=entry_opportunity_score,
        entry_regime=entry_regime_score,
    )
    target_price = avg * (1.0 + target_pct / 100.0)
    if price >= target_price:
        return ExitDecision("sell", "target_profit_reached", target_price)

    peak_gain_pct = (peak / avg - 1.0) * 100.0
    trail_arm_pct = 5.0
    trail_giveback_pct = 3.0
    if peak_gain_pct >= trail_arm_pct:
        trailing_price = peak * (1.0 - trail_giveback_pct / 100.0)
        if price <= trailing_price:
            return ExitDecision("sell", "trailing_profit_protection", trailing_price)

    if float(holding_seconds) >= 24.0 * 3600.0 and pnl_pct < 2.0 and float(current_opportunity_score) < 50.0:
        return ExitDecision("sell", "stale_position_time_exit", price)

    return ExitDecision("hold", "position_thesis_active", 0.0)
