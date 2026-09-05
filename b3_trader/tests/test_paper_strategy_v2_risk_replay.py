from __future__ import annotations

from b3_trader.paper_portfolio_risk_v2 import PortfolioRiskPolicy
from b3_trader.paper_position_plan_v2 import PositionSizingPolicy
from b3_trader.paper_strategy_v2_risk_replay import replay_shared_portfolio_risk_capped, run_policy_sweep


def _row(ts: float, market: str, price: float, *, regime: float = 62.0, entry: float = 70.0, opportunity: float = 68.0, volatility: float = 2.0):
    return {
        "ts": ts,
        "exchange": "bithumb",
        "market": market,
        "strategy": "adaptive",
        "price": price,
        "regime_score": regime,
        "entry_score": entry,
        "opportunity_score": opportunity,
        "volatility_pct": volatility,
        "trade_intent": "wait",
    }


def test_risk_capped_replay_executes_prefunded_adds_without_opportunity_recheck() -> None:
    rows = [
        _row(300.0, "KRW-AAA", 100.0),
        _row(600.0, "KRW-AAA", 97.0, opportunity=40.0),
        _row(900.0, "KRW-AAA", 94.5, opportunity=35.0),
        _row(1200.0, "KRW-AAA", 92.5, opportunity=30.0),
        _row(1500.0, "KRW-AAA", 111.0, opportunity=70.0),
    ]
    result = replay_shared_portfolio_risk_capped(
        rows,
        policy=PositionSizingPolicy(risk_budget_pct=2.0),
        risk_policy=PortfolioRiskPolicy(max_portfolio_risk_pct=5.0),
        max_positions=1,
    )
    assert result["trades"]["initial_orders"] == 1
    assert result["trades"]["add_orders"] == 3
    assert result["trades"]["cycles_with_adds"] == 1


def test_replay_peak_reserved_risk_never_exceeds_cap() -> None:
    rows = []
    for market in ("KRW-AAA", "KRW-BBB", "KRW-CCC", "KRW-DDD"):
        rows.append(_row(300.0, market, 100.0))
        rows.append(_row(600.0, market, 101.0))
    result = replay_shared_portfolio_risk_capped(
        rows,
        policy=PositionSizingPolicy(max_gross_exposure_pct=80.0, max_position_pct=30.0, risk_budget_pct=2.5),
        risk_policy=PortfolioRiskPolicy(max_portfolio_risk_pct=4.0),
        max_positions=4,
    )
    assert result["portfolio"]["peak_reserved_risk_pct"] <= 4.001
    assert result["portfolio"]["max_concurrent_positions"] <= 4


def test_same_bucket_exit_does_not_immediately_reenter_same_market() -> None:
    rows = [
        _row(300.0, "KRW-AAA", 100.0),
        _row(600.0, "KRW-AAA", 112.0, opportunity=80.0),
    ]
    result = replay_shared_portfolio_risk_capped(rows, max_positions=1)
    assert result["trades"]["positions_opened"] == 1
    assert result["trades"]["positions_closed"] == 1


def test_policy_sweep_uses_same_rows_and_reports_four_presets() -> None:
    rows = [_row(300.0, "KRW-AAA", 100.0), _row(600.0, "KRW-AAA", 103.0)]
    result = run_policy_sweep(rows)
    assert result["paper_only"] is True
    assert result["same_source_rows_for_all_presets"] is True
    assert result["rows"] == 2
    assert len(result["presets"]) == 4
    assert {row["name"] for row in result["presets"]} == {
        "control_70_30_r2_5",
        "balanced_60_25_r2_agg5",
        "conservative_50_22_r1_5_agg4",
        "concentrated_55_28_r2_agg4",
    }
