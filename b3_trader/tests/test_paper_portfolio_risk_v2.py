from __future__ import annotations

from b3_trader.paper_portfolio_risk_v2 import PortfolioRiskPolicy, cap_plan_to_portfolio_risk, reserved_risk_krw
from b3_trader.paper_position_plan_v2 import PositionSizingPolicy, plan_new_position


def _plan(risk_budget_pct: float = 2.5):
    return plan_new_position(
        first_entry_price=100.0,
        regime_score=62.0,
        entry_score=70.0,
        opportunity_score=68.0,
        volatility_pct=2.0,
        policy=PositionSizingPolicy(risk_budget_pct=risk_budget_pct),
    )


def test_risk_guard_leaves_plan_unchanged_when_room_exists() -> None:
    plan = _plan(2.0)
    guarded = cap_plan_to_portfolio_risk(
        plan,
        current_reserved_risk_krw=100_000.0,
        risk_policy=PortfolioRiskPolicy(max_portfolio_risk_pct=5.0),
    )
    assert guarded.allowed is True
    assert guarded.target_position_krw == plan.target_position_krw
    assert guarded.worst_case_loss_krw == plan.worst_case_loss_krw


def test_risk_guard_scales_plan_to_remaining_aggregate_budget() -> None:
    plan = _plan(2.5)
    guarded = cap_plan_to_portfolio_risk(
        plan,
        current_reserved_risk_krw=420_000.0,
        risk_policy=PortfolioRiskPolicy(max_portfolio_risk_pct=5.0),
    )
    assert guarded.allowed is True
    assert guarded.reason == "shared_portfolio_plan_ready_risk_capped"
    assert guarded.target_position_krw < plan.target_position_krw
    assert guarded.worst_case_loss_krw <= 80_000.01
    assert guarded.initial_order_krw >= 100_000.0


def test_risk_guard_blocks_when_no_portfolio_risk_room_remains() -> None:
    plan = _plan()
    guarded = cap_plan_to_portfolio_risk(
        plan,
        current_reserved_risk_krw=500_000.0,
        risk_policy=PortfolioRiskPolicy(max_portfolio_risk_pct=5.0),
    )
    assert guarded.allowed is False
    assert guarded.reason == "portfolio_risk_cap_exhausted"
    assert guarded.ladder == ()


def test_reserved_risk_sums_full_planned_losses() -> None:
    first = _plan(1.5)
    second = _plan(2.0)
    assert reserved_risk_krw([first, second]) == round(first.worst_case_loss_krw + second.worst_case_loss_krw, 2)
