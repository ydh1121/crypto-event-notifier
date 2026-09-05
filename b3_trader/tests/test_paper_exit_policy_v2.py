from __future__ import annotations

from b3_trader.paper_exit_policy_v2 import evaluate_exit, target_profit_pct
from b3_trader.paper_position_plan_v2 import plan_new_position


def _plan():
    return plan_new_position(
        first_entry_price=100.0,
        regime_score=62.0,
        entry_score=70.0,
        opportunity_score=68.0,
        volatility_pct=2.0,
    )


def test_target_profit_is_bounded() -> None:
    assert target_profit_pct(entry_opportunity=58.0, entry_regime=50.0) == 8.0
    assert target_profit_pct(entry_opportunity=100.0, entry_regime=100.0) == 14.0


def test_invalidation_exits_before_other_logic() -> None:
    plan = _plan()
    decision = evaluate_exit(
        plan,
        average_price=98.0,
        current_price=plan.invalidation_price - 0.01,
        peak_price=101.0,
        current_regime_score=60.0,
        current_opportunity_score=70.0,
        holding_seconds=60.0,
        entry_opportunity_score=68.0,
        entry_regime_score=62.0,
    )
    assert decision.action == "sell"
    assert decision.reason == "thesis_invalidation_price_breached"
    assert decision.can_place_real_orders is False


def test_market_weakness_exits_underwater_position() -> None:
    plan = _plan()
    decision = evaluate_exit(
        plan,
        average_price=100.0,
        current_price=97.0,
        peak_price=101.0,
        current_regime_score=34.0,
        current_opportunity_score=45.0,
        holding_seconds=3600.0,
        entry_opportunity_score=68.0,
        entry_regime_score=62.0,
    )
    assert decision.action == "sell"
    assert decision.reason == "thesis_regime_floor_breached"


def test_profit_target_and_trailing_are_supported() -> None:
    plan = _plan()
    take_profit = evaluate_exit(
        plan,
        average_price=100.0,
        current_price=112.0,
        peak_price=112.0,
        current_regime_score=60.0,
        current_opportunity_score=65.0,
        holding_seconds=7200.0,
        entry_opportunity_score=68.0,
        entry_regime_score=62.0,
    )
    assert take_profit.action == "sell"
    assert take_profit.reason == "target_profit_reached"

    trailing = evaluate_exit(
        plan,
        average_price=100.0,
        current_price=104.0,
        peak_price=108.0,
        current_regime_score=60.0,
        current_opportunity_score=60.0,
        holding_seconds=7200.0,
        entry_opportunity_score=68.0,
        entry_regime_score=62.0,
    )
    assert trailing.action == "sell"
    assert trailing.reason == "trailing_profit_protection"


def test_stale_position_time_exit() -> None:
    plan = _plan()
    decision = evaluate_exit(
        plan,
        average_price=100.0,
        current_price=101.0,
        peak_price=102.0,
        current_regime_score=50.0,
        current_opportunity_score=45.0,
        holding_seconds=25.0 * 3600.0,
        entry_opportunity_score=68.0,
        entry_regime_score=62.0,
    )
    assert decision.action == "sell"
    assert decision.reason == "stale_position_time_exit"
