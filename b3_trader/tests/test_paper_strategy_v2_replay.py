from __future__ import annotations

from b3_trader.paper_strategy_v2_replay import replay_shared_portfolio


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


def test_replay_uses_shared_capital_and_executes_prefunded_ladder() -> None:
    rows = [
        _row(300.0, "KRW-AAA", 100.0),
        _row(600.0, "KRW-AAA", 97.0, opportunity=52.0),
        _row(900.0, "KRW-AAA", 94.5, opportunity=48.0),
        _row(1200.0, "KRW-AAA", 92.5, opportunity=45.0),
        _row(1500.0, "KRW-AAA", 110.0, opportunity=70.0),
    ]
    result = replay_shared_portfolio(rows, max_positions=1, bucket_seconds=300)

    assert result["paper_only"] is True
    assert result["can_place_orders"] is False
    assert result["portfolio"]["max_concurrent_positions"] == 1
    assert result["trades"]["initial_orders"] == 1
    assert result["trades"]["add_orders"] == 3
    assert result["trades"]["cycles_with_adds"] == 1
    assert result["trades"]["positions_closed"] == 1
    assert result["portfolio"]["return_pct"] > 0


def test_replay_selects_highest_ranked_candidate_with_one_slot() -> None:
    rows = [
        _row(300.0, "KRW-AAA", 100.0, opportunity=61.0),
        _row(300.0, "KRW-BBB", 100.0, opportunity=72.0),
        _row(600.0, "KRW-AAA", 100.0, opportunity=61.0),
        _row(600.0, "KRW-BBB", 109.0, opportunity=72.0),
    ]
    result = replay_shared_portfolio(rows, max_positions=1, bucket_seconds=300)

    assert result["trades"]["positions_opened"] == 1
    assert result["portfolio"]["max_concurrent_positions"] == 1
    assert result["trades"]["positions_closed"] == 1


def test_replay_respects_new_entry_floors() -> None:
    rows = [
        _row(300.0, "KRW-AAA", 100.0, entry=40.0),
        _row(600.0, "KRW-AAA", 101.0, entry=42.0),
    ]
    result = replay_shared_portfolio(rows, max_positions=3, bucket_seconds=300)

    assert result["trades"]["positions_opened"] == 0
    assert result["trades"]["buy_orders"] == 0
    assert result["portfolio"]["final_krw"] == 10_000_000.0


def test_replay_reports_execution_limitations_explicitly() -> None:
    result = replay_shared_portfolio([_row(300.0, "KRW-AAA", 100.0)], max_positions=1)
    model = result["execution_model"]
    assert model["historical_orderbook_depth_replayed"] is False
    assert model["historical_spread_gate_replayed"] is False
    assert model["historical_lifecycle_gate_replayed"] is False
