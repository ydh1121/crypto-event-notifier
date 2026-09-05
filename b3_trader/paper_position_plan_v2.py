from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PositionSizingPolicy:
    """Shared-portfolio PAPER sizing policy.

    The policy is deliberately separate from exchange execution. It produces a
    bounded position plan from one shared capital pool and reserves the entire
    planned position before any order adapter is allowed to act.
    """

    portfolio_capital_krw: float = 10_000_000.0
    max_gross_exposure_pct: float = 70.0
    reserve_cash_pct: float = 20.0
    max_position_pct: float = 30.0
    risk_budget_pct: float = 2.5
    min_order_krw: float = 100_000.0
    min_regime_for_new: float = 50.0
    min_entry_for_new: float = 55.0
    min_opportunity_for_new: float = 58.0
    thesis_regime_floor: float = 35.0
    ladder_weights: tuple[float, float, float, float] = (0.35, 0.25, 0.22, 0.18)
    add_trigger_stop_fractions: tuple[float, float, float] = (0.30, 0.55, 0.78)

    def __post_init__(self) -> None:
        if self.portfolio_capital_krw <= 0:
            raise ValueError("portfolio_capital_krw must be positive")
        if not math.isclose(sum(self.ladder_weights), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("ladder_weights must sum to 1")
        if len(self.ladder_weights) != 4 or len(self.add_trigger_stop_fractions) != 3:
            raise ValueError("v2 requires one initial entry plus three averaging adds")
        if not 0 < self.reserve_cash_pct < 100:
            raise ValueError("reserve_cash_pct must be between 0 and 100")
        if not 0 < self.max_gross_exposure_pct <= 100:
            raise ValueError("max_gross_exposure_pct must be between 0 and 100")
        if not 0 < self.max_position_pct <= self.max_gross_exposure_pct:
            raise ValueError("max_position_pct must be positive and <= max_gross_exposure_pct")
        if self.risk_budget_pct <= 0:
            raise ValueError("risk_budget_pct must be positive")


@dataclass(frozen=True)
class LadderRung:
    index: int
    kind: str
    trigger_price: float
    trigger_drop_pct: float
    order_krw: float
    cumulative_planned_krw: float


@dataclass(frozen=True)
class PositionPlanV2:
    allowed: bool
    reason: str
    portfolio_capital_krw: float
    first_entry_price: float
    desired_position_pct: float
    target_position_krw: float
    reserved_position_krw: float
    stop_distance_pct: float
    invalidation_price: float
    risk_budget_krw: float
    worst_case_loss_krw: float
    thesis_regime_floor: float
    ladder: tuple[LadderRung, ...]
    paper_only: bool = True
    can_place_real_orders: bool = False

    @property
    def initial_order_krw(self) -> float:
        return self.ladder[0].order_krw if self.ladder else 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["initial_order_krw"] = self.initial_order_krw
        payload["ladder"] = [asdict(row) for row in self.ladder]
        return payload


@dataclass(frozen=True)
class AddDecision:
    action: str
    reason: str
    rung_index: int
    trigger_price: float
    order_krw: float
    paper_only: bool = True
    can_place_real_orders: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, float(value)))


def _finite_positive(value: float) -> bool:
    return math.isfinite(float(value)) and float(value) > 0


def stop_distance_pct(*, volatility_pct: float, regime_score: float) -> float:
    """Bounded thesis invalidation distance for a planned multi-entry position.

    The stop is intentionally outside every averaging trigger. It is not a
    martingale escape hatch: the full planned loss must fit inside the position
    risk budget before the first buy is allowed.
    """

    volatility = max(0.0, float(volatility_pct))
    weak_regime_penalty = max(0.0, 50.0 - float(regime_score)) * 0.025
    return round(_clamp(8.0 + volatility * 0.70 + weak_regime_penalty, 8.0, 12.0), 3)


def desired_position_pct(
    *,
    opportunity_score: float,
    regime_score: float,
    entry_score: float,
    policy: PositionSizingPolicy,
) -> float:
    """Translate conviction into a target position, not an individual ticket."""

    opportunity = _clamp((float(opportunity_score) - 55.0) / 25.0, 0.0, 1.0)
    regime = _clamp((float(regime_score) - 50.0) / 30.0, 0.0, 1.0)
    entry = _clamp((float(entry_score) - 55.0) / 30.0, 0.0, 1.0)
    conviction = 0.50 * opportunity + 0.25 * regime + 0.25 * entry
    return round(_clamp(22.0 + conviction * 8.0, 22.0, policy.max_position_pct), 3)


def plan_new_position(
    *,
    first_entry_price: float,
    regime_score: float,
    entry_score: float,
    opportunity_score: float,
    volatility_pct: float,
    current_reserved_exposure_krw: float = 0.0,
    available_cash_krw: float | None = None,
    policy: PositionSizingPolicy | None = None,
) -> PositionPlanV2:
    """Create one immutable shared-capital position plan.

    `current_reserved_exposure_krw` counts the *full target capital* already
    reserved for other open/planned positions, not just their filled tranches.
    This prevents several partially filled ladders from overbooking the same cash.
    """

    policy = policy or PositionSizingPolicy()
    capital = float(policy.portfolio_capital_krw)
    cash = capital if available_cash_krw is None else max(0.0, float(available_cash_krw))
    price = float(first_entry_price)
    reserved = max(0.0, float(current_reserved_exposure_krw))

    if not _finite_positive(price):
        return PositionPlanV2(
            False, "invalid_price", capital, price, 0.0, 0.0, 0.0, 0.0, 0.0,
            capital * policy.risk_budget_pct / 100.0, 0.0, policy.thesis_regime_floor, (),
        )

    threshold_failures: list[str] = []
    if float(regime_score) < policy.min_regime_for_new:
        threshold_failures.append("regime_below_new_entry_floor")
    if float(entry_score) < policy.min_entry_for_new:
        threshold_failures.append("entry_below_new_entry_floor")
    if float(opportunity_score) < policy.min_opportunity_for_new:
        threshold_failures.append("opportunity_below_new_entry_floor")
    if threshold_failures:
        return PositionPlanV2(
            False, ",".join(threshold_failures), capital, price, 0.0, 0.0, 0.0, 0.0, 0.0,
            capital * policy.risk_budget_pct / 100.0, 0.0, policy.thesis_regime_floor, (),
        )

    stop_pct = stop_distance_pct(volatility_pct=volatility_pct, regime_score=regime_score)
    desired_pct = desired_position_pct(
        opportunity_score=opportunity_score,
        regime_score=regime_score,
        entry_score=entry_score,
        policy=policy,
    )

    desired_krw = capital * desired_pct / 100.0
    per_position_cap = capital * policy.max_position_pct / 100.0
    gross_cap = capital * policy.max_gross_exposure_pct / 100.0
    gross_room = max(0.0, gross_cap - reserved)
    reserve_floor = capital * policy.reserve_cash_pct / 100.0
    cash_room = max(0.0, cash - reserve_floor)
    risk_budget = capital * policy.risk_budget_pct / 100.0
    risk_cap = risk_budget / (stop_pct / 100.0)

    target = max(0.0, min(desired_krw, per_position_cap, gross_room, cash_room, risk_cap))
    target = round(target, 2)
    worst_case_loss = round(target * stop_pct / 100.0, 2)

    if target < policy.min_order_krw / max(policy.ladder_weights[0], 1e-9):
        return PositionPlanV2(
            False, "insufficient_shared_portfolio_room", capital, price, desired_pct, target, target,
            stop_pct, round(price * (1.0 - stop_pct / 100.0), 12), risk_budget,
            worst_case_loss, policy.thesis_regime_floor, (),
        )

    trigger_drops = (0.0,) + tuple(stop_pct * fraction for fraction in policy.add_trigger_stop_fractions)
    cumulative = 0.0
    ladder: list[LadderRung] = []
    for index, (weight, drop_pct) in enumerate(zip(policy.ladder_weights, trigger_drops), start=1):
        order_krw = round(target * weight, 2)
        cumulative = round(cumulative + order_krw, 2)
        trigger = price if index == 1 else price * (1.0 - drop_pct / 100.0)
        ladder.append(
            LadderRung(
                index=index,
                kind="initial" if index == 1 else "add",
                trigger_price=round(trigger, 12),
                trigger_drop_pct=round(drop_pct, 3),
                order_krw=order_krw,
                cumulative_planned_krw=cumulative,
            )
        )

    rounding_gap = round(target - sum(row.order_krw for row in ladder), 2)
    if ladder and abs(rounding_gap) >= 0.01:
        last = ladder[-1]
        ladder[-1] = LadderRung(
            index=last.index,
            kind=last.kind,
            trigger_price=last.trigger_price,
            trigger_drop_pct=last.trigger_drop_pct,
            order_krw=round(last.order_krw + rounding_gap, 2),
            cumulative_planned_krw=target,
        )

    if ladder[0].order_krw < policy.min_order_krw:
        return PositionPlanV2(
            False, "initial_order_below_minimum", capital, price, desired_pct, target, target,
            stop_pct, round(price * (1.0 - stop_pct / 100.0), 12), risk_budget,
            worst_case_loss, policy.thesis_regime_floor, tuple(ladder),
        )

    return PositionPlanV2(
        True,
        "shared_portfolio_plan_ready",
        capital,
        price,
        desired_pct,
        target,
        target,
        stop_pct,
        round(price * (1.0 - stop_pct / 100.0), 12),
        round(risk_budget, 2),
        worst_case_loss,
        policy.thesis_regime_floor,
        tuple(ladder),
    )


def evaluate_next_add(
    plan: PositionPlanV2,
    *,
    completed_entries: int,
    current_price: float,
    current_regime_score: float,
    lifecycle_add_allowed: bool = True,
    spread_ok: bool = True,
    slippage_ok: bool = True,
    btc_flash_crash: bool = False,
) -> AddDecision:
    """Evaluate the next pre-funded averaging rung.

    There is intentionally no current opportunity-score threshold here. Once a
    position thesis is accepted, adds are controlled by the pre-funded price
    ladder plus thesis invalidation and execution-risk checks. This removes the
    v1 contradiction where a pullback reached the add price but simultaneously
    lowered opportunity enough to disable the add.
    """

    if not plan.allowed or not plan.ladder:
        return AddDecision("blocked", "plan_not_allowed", 0, 0.0, 0.0)
    entries = int(completed_entries)
    if entries < 1:
        return AddDecision("blocked", "initial_entry_not_filled", 0, 0.0, 0.0)
    if entries >= len(plan.ladder):
        return AddDecision("complete", "ladder_complete", entries, 0.0, 0.0)

    next_rung = plan.ladder[entries]
    price = float(current_price)
    if not _finite_positive(price):
        return AddDecision("blocked", "invalid_price", next_rung.index, next_rung.trigger_price, 0.0)
    if price <= plan.invalidation_price:
        return AddDecision("invalidate", "thesis_invalidation_price_breached", next_rung.index, next_rung.trigger_price, 0.0)
    if float(current_regime_score) < plan.thesis_regime_floor:
        return AddDecision("invalidate", "thesis_regime_floor_breached", next_rung.index, next_rung.trigger_price, 0.0)
    if not lifecycle_add_allowed:
        return AddDecision("blocked", "lifecycle_add_blocked", next_rung.index, next_rung.trigger_price, 0.0)
    if btc_flash_crash:
        return AddDecision("blocked", "btc_flash_crash", next_rung.index, next_rung.trigger_price, 0.0)
    if not spread_ok:
        return AddDecision("blocked", "spread_risk", next_rung.index, next_rung.trigger_price, 0.0)
    if not slippage_ok:
        return AddDecision("blocked", "slippage_risk", next_rung.index, next_rung.trigger_price, 0.0)
    if price > next_rung.trigger_price:
        return AddDecision("wait", "next_add_price_not_reached", next_rung.index, next_rung.trigger_price, 0.0)

    return AddDecision(
        "add",
        "pre_funded_ladder_trigger_reached",
        next_rung.index,
        next_rung.trigger_price,
        next_rung.order_krw,
    )
