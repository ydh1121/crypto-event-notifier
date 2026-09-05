from __future__ import annotations

from b3_trader.paper_position_plan_v2 import (
    PositionSizingPolicy,
    evaluate_next_add,
    plan_new_position,
)


def _strong_plan(**overrides):
    params = {
        "first_entry_price": 100_000.0,
        "regime_score": 70.0,
        "entry_score": 72.0,
        "opportunity_score": 75.0,
        "volatility_pct": 2.0,
    }
    params.update(overrides)
    return plan_new_position(**params)


def test_strong_signal_uses_real_position_target_not_300k_ticket() -> None:
    plan = _strong_plan()
    assert plan.allowed is True
    assert 2_000_000.0 <= plan.target_position_krw <= 3_000_000.0
    assert plan.initial_order_krw >= 700_000.0
    assert plan.initial_order_krw > 500_000.0
    assert plan.worst_case_loss_krw <= plan.risk_budget_krw + 0.01


def test_ladder_reserves_full_target_and_sums_exactly() -> None:
    plan = _strong_plan()
    assert len(plan.ladder) == 4
    assert plan.reserved_position_krw == plan.target_position_krw
    assert round(sum(row.order_krw for row in plan.ladder), 2) == plan.target_position_krw
    assert [row.kind for row in plan.ladder] == ["initial", "add", "add", "add"]
    assert plan.ladder[1].trigger_price < plan.first_entry_price
    assert plan.ladder[2].trigger_price < plan.ladder[1].trigger_price
    assert plan.ladder[3].trigger_price < plan.ladder[2].trigger_price
    assert plan.invalidation_price < plan.ladder[-1].trigger_price


def test_shared_gross_exposure_prevents_independent_10m_accounts() -> None:
    policy = PositionSizingPolicy()
    plan = _strong_plan(
        current_reserved_exposure_krw=6_500_000.0,
        available_cash_krw=10_000_000.0,
        policy=policy,
    )
    assert plan.allowed is True
    assert plan.target_position_krw <= 500_000.0
    assert plan.reserved_position_krw <= 500_000.0


def test_cash_reserve_is_protected() -> None:
    policy = PositionSizingPolicy(reserve_cash_pct=20.0)
    plan = _strong_plan(
        available_cash_krw=2_300_000.0,
        current_reserved_exposure_krw=0.0,
        policy=policy,
    )
    assert plan.target_position_krw <= 300_000.0
    assert plan.allowed is True


def test_new_entry_thresholds_fail_closed() -> None:
    plan = _strong_plan(opportunity_score=50.0)
    assert plan.allowed is False
    assert "opportunity_below_new_entry_floor" in plan.reason
    assert plan.target_position_krw == 0.0
    assert plan.ladder == ()


def test_add_executes_on_prefunded_price_trigger_without_opportunity_recheck() -> None:
    plan = _strong_plan()
    trigger = plan.ladder[1].trigger_price
    decision = evaluate_next_add(
        plan,
        completed_entries=1,
        current_price=trigger,
        current_regime_score=50.0,
        lifecycle_add_allowed=True,
        spread_ok=True,
        slippage_ok=True,
        btc_flash_crash=False,
    )
    assert decision.action == "add"
    assert decision.order_krw == plan.ladder[1].order_krw
    assert decision.reason == "pre_funded_ladder_trigger_reached"


def test_add_waits_until_price_trigger() -> None:
    plan = _strong_plan()
    trigger = plan.ladder[1].trigger_price
    decision = evaluate_next_add(
        plan,
        completed_entries=1,
        current_price=trigger * 1.01,
        current_regime_score=60.0,
    )
    assert decision.action == "wait"
    assert decision.reason == "next_add_price_not_reached"


def test_add_is_invalidated_by_thesis_not_by_ordinary_score_softening() -> None:
    plan = _strong_plan()
    trigger = plan.ladder[1].trigger_price
    decision = evaluate_next_add(
        plan,
        completed_entries=1,
        current_price=trigger,
        current_regime_score=plan.thesis_regime_floor - 0.1,
    )
    assert decision.action == "invalidate"
    assert decision.reason == "thesis_regime_floor_breached"


def test_price_invalidation_precedes_later_averaging() -> None:
    plan = _strong_plan()
    decision = evaluate_next_add(
        plan,
        completed_entries=2,
        current_price=plan.invalidation_price,
        current_regime_score=60.0,
    )
    assert decision.action == "invalidate"
    assert decision.order_krw == 0.0


def test_execution_risk_can_block_add_without_destroying_plan() -> None:
    plan = _strong_plan()
    trigger = plan.ladder[1].trigger_price
    decision = evaluate_next_add(
        plan,
        completed_entries=1,
        current_price=trigger,
        current_regime_score=60.0,
        spread_ok=False,
    )
    assert decision.action == "blocked"
    assert decision.reason == "spread_risk"
    assert decision.order_krw == 0.0


def test_ladder_is_bounded_not_martingale() -> None:
    plan = _strong_plan()
    amounts = [row.order_krw for row in plan.ladder]
    assert amounts[0] >= amounts[1] >= amounts[2] >= amounts[3]
    assert max(amounts) <= plan.target_position_krw * 0.35 + 0.01


def test_plan_serialization_keeps_paper_safety_contract() -> None:
    payload = _strong_plan().to_dict()
    assert payload["paper_only"] is True
    assert payload["can_place_real_orders"] is False
    assert payload["initial_order_krw"] == payload["ladder"][0]["order_krw"]
