from __future__ import annotations

from b3_trader.paper_strategy_v2_shadow import build_shadow_portfolio


def _row(market: str, opportunity: float, regime: float = 70.0, entry: float = 70.0, volatility: float = 2.0):
    return {
        "exchange": "bithumb",
        "market": market,
        "symbol": market.removeprefix("KRW-"),
        "price": 100_000.0,
        "regime_score": regime,
        "entry_score": entry,
        "opportunity_score": opportunity,
        "trade_intent": "wait",
        "signal": {"volatility_pct": volatility},
    }


def test_shadow_portfolio_reserves_shared_capital_across_candidates() -> None:
    result = build_shadow_portfolio(
        [
            _row("KRW-A", 80.0),
            _row("KRW-B", 76.0),
            _row("KRW-C", 72.0),
            _row("KRW-D", 68.0),
        ],
        max_positions=3,
    )
    assert result["paper_only"] is True
    assert result["read_only"] is True
    assert result["can_place_orders"] is False
    assert result["shared_portfolio_budget"] is True
    assert len(result["proposals"]) <= 3
    assert result["reserved_target_capital_krw"] <= 7_000_000.0
    assert result["remaining_unreserved_capital_krw"] >= 3_000_000.0


def test_shadow_portfolio_ignores_legacy_intent_when_v2_thresholds_are_met() -> None:
    result = build_shadow_portfolio([_row("KRW-A", 75.0)], max_positions=1)
    assert len(result["proposals"]) == 1
    proposal = result["proposals"][0]
    assert proposal["legacy_trade_intent"] == "wait"
    assert proposal["plan"]["initial_order_krw"] > 500_000.0


def test_shadow_portfolio_reports_rejected_signal_reasons() -> None:
    result = build_shadow_portfolio(
        [
            _row("KRW-WEAK", 40.0, regime=35.0, entry=40.0),
            _row("KRW-STRONG", 75.0),
        ],
        max_positions=3,
    )
    assert len(result["proposals"]) == 1
    assert result["proposals"][0]["market"] == "KRW-STRONG"
    assert result["rejected_top"]
    assert "opportunity_below_new_entry_floor" in result["rejected_top"][0]["reason"]


def test_shadow_portfolio_orders_candidates_by_opportunity() -> None:
    result = build_shadow_portfolio(
        [_row("KRW-LOW", 60.0), _row("KRW-HIGH", 78.0)],
        max_positions=1,
    )
    assert result["proposals"][0]["market"] == "KRW-HIGH"
