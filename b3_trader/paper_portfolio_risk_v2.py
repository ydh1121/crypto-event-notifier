from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .paper_position_plan_v2 import LadderRung, PositionPlanV2


@dataclass(frozen=True)
class PortfolioRiskPolicy:
    """Aggregate risk budget layered on top of per-position sizing.

    The risk budget is reserved from the full planned position before the first
    tranche fills. This prevents several partially filled ladders from each
    assuming they can consume the same portfolio loss budget.
    """

    max_portfolio_risk_pct: float = 5.0
    min_initial_order_krw: float = 100_000.0

    def __post_init__(self) -> None:
        if not 0 < float(self.max_portfolio_risk_pct) <= 100:
            raise ValueError("max_portfolio_risk_pct must be between 0 and 100")
        if float(self.min_initial_order_krw) <= 0:
            raise ValueError("min_initial_order_krw must be positive")


def reserved_risk_krw(plans: Iterable[PositionPlanV2]) -> float:
    return round(sum(max(0.0, float(plan.worst_case_loss_krw)) for plan in plans if plan.allowed), 2)


def cap_plan_to_portfolio_risk(
    plan: PositionPlanV2,
    *,
    current_reserved_risk_krw: float,
    risk_policy: PortfolioRiskPolicy | None = None,
) -> PositionPlanV2:
    """Scale or reject a pre-funded plan so aggregate reserved loss stays bounded."""

    risk_policy = risk_policy or PortfolioRiskPolicy()
    if not plan.allowed or not plan.ladder:
        return plan

    capital = float(plan.portfolio_capital_krw)
    aggregate_cap = capital * float(risk_policy.max_portfolio_risk_pct) / 100.0
    current = max(0.0, float(current_reserved_risk_krw))
    remaining = max(0.0, aggregate_cap - current)
    planned_loss = max(0.0, float(plan.worst_case_loss_krw))

    if planned_loss <= remaining + 0.01:
        return plan

    if remaining <= 0 or plan.stop_distance_pct <= 0:
        return PositionPlanV2(
            False,
            "portfolio_risk_cap_exhausted",
            plan.portfolio_capital_krw,
            plan.first_entry_price,
            plan.desired_position_pct,
            0.0,
            0.0,
            plan.stop_distance_pct,
            plan.invalidation_price,
            min(plan.risk_budget_krw, remaining),
            0.0,
            plan.thesis_regime_floor,
            (),
        )

    target = round(remaining / (float(plan.stop_distance_pct) / 100.0), 2)
    target = min(target, float(plan.target_position_krw))
    if target <= 0:
        return PositionPlanV2(
            False,
            "portfolio_risk_room_insufficient",
            plan.portfolio_capital_krw,
            plan.first_entry_price,
            plan.desired_position_pct,
            0.0,
            0.0,
            plan.stop_distance_pct,
            plan.invalidation_price,
            min(plan.risk_budget_krw, remaining),
            0.0,
            plan.thesis_regime_floor,
            (),
        )

    original_target = max(float(plan.target_position_krw), 1e-9)
    scale = target / original_target
    cumulative = 0.0
    ladder: list[LadderRung] = []
    for original in plan.ladder:
        order = round(float(original.order_krw) * scale, 2)
        cumulative = round(cumulative + order, 2)
        ladder.append(
            LadderRung(
                index=original.index,
                kind=original.kind,
                trigger_price=original.trigger_price,
                trigger_drop_pct=original.trigger_drop_pct,
                order_krw=order,
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

    if not ladder or ladder[0].order_krw < float(risk_policy.min_initial_order_krw):
        return PositionPlanV2(
            False,
            "portfolio_risk_room_below_minimum_entry",
            plan.portfolio_capital_krw,
            plan.first_entry_price,
            plan.desired_position_pct,
            target,
            target,
            plan.stop_distance_pct,
            plan.invalidation_price,
            min(plan.risk_budget_krw, remaining),
            round(target * plan.stop_distance_pct / 100.0, 2),
            plan.thesis_regime_floor,
            tuple(ladder),
        )

    worst_case = round(target * plan.stop_distance_pct / 100.0, 2)
    return PositionPlanV2(
        True,
        "shared_portfolio_plan_ready_risk_capped",
        plan.portfolio_capital_krw,
        plan.first_entry_price,
        plan.desired_position_pct,
        target,
        target,
        plan.stop_distance_pct,
        plan.invalidation_price,
        min(plan.risk_budget_krw, remaining),
        worst_case,
        plan.thesis_regime_floor,
        tuple(ladder),
    )
