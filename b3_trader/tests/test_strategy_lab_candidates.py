from __future__ import annotations

from b3_trader.strategy_lab_candidates import evaluate_candidate


def _metric(**overrides):
    row = {
        "closed_trades": 40,
        "return_pct": 6.0,
        "max_drawdown_pct": -6.0,
        "expectancy_pct": 0.6,
        "profit_factor": 1.6,
    }
    row.update(overrides)
    return row


def _markets(count: int = 5, *, negative: int = 1):
    rows = []
    for idx in range(count):
        is_negative = idx < negative
        rows.append(
            {
                "market": f"KRW-T{idx}",
                "closed_trades": 8,
                "sum_return_pct": -1.0 if is_negative else 4.0,
                "realized_pnl": -100_000.0 if is_negative else 200_000.0,
            }
        )
    return rows


def test_candidate_gate_marks_small_sample_as_warming() -> None:
    result = evaluate_candidate(_metric(closed_trades=10), _markets(2, negative=0))
    assert result["status"] == "warming"
    assert result["eligible_for_promotion"] is False
    assert result["auto_promote"] is False
    assert result["sample_progress"] < 1.0
    assert result["breadth_progress"] < 1.0


def test_candidate_gate_accepts_broad_positive_stable_sample() -> None:
    result = evaluate_candidate(_metric(), _markets(5, negative=1))
    assert result["status"] == "candidate"
    assert result["eligible_for_promotion"] is True
    assert result["passed_gates"] == result["total_gates"]
    assert result["traded_markets"] == 5
    assert result["profitable_market_share"] == 0.8
    assert result["pnl_concentration_share"] < 0.6


def test_candidate_gate_rejects_mature_but_risky_result() -> None:
    result = evaluate_candidate(
        _metric(max_drawdown_pct=-18.0, expectancy_pct=-0.2, profit_factor=0.8),
        _markets(5, negative=1),
    )
    assert result["status"] == "rejected"
    assert result["eligible_for_promotion"] is False
    failed = {gate["key"] for gate in result["gates"] if not gate["passed"]}
    assert {"drawdown", "expectancy", "profit_factor"}.issubset(failed)
