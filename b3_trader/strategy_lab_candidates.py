from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from statistics import median
from typing import Any

from .auto_demo_v2 import DB_PATH

MIN_CLOSED_TRADES = 30
MIN_TRADED_MARKETS = 5
MIN_PROFITABLE_MARKET_SHARE = 0.50
MAX_PNL_CONCENTRATION_SHARE = 0.60
MAX_DRAWDOWN_FLOOR_PCT = -12.0
MIN_EXPECTANCY_PCT = 0.0
MIN_PROFIT_FACTOR = 1.10
MIN_TOTAL_RETURN_PCT = 0.0


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _gate(key: str, label: str, passed: bool, value: Any, required: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "passed": bool(passed),
        "value": value,
        "required": required,
    }


def candidate_criteria() -> dict[str, Any]:
    return {
        "min_closed_trades": MIN_CLOSED_TRADES,
        "min_traded_markets": MIN_TRADED_MARKETS,
        "min_profitable_market_share": MIN_PROFITABLE_MARKET_SHARE,
        "max_pnl_concentration_share": MAX_PNL_CONCENTRATION_SHARE,
        "max_drawdown_floor_pct": MAX_DRAWDOWN_FLOOR_PCT,
        "min_expectancy_pct": MIN_EXPECTANCY_PCT,
        "min_profit_factor": MIN_PROFIT_FACTOR,
        "min_total_return_pct": MIN_TOTAL_RETURN_PCT,
        "auto_promote": False,
        "paper_only": True,
    }


def evaluate_candidate(metric: dict[str, Any], market_rows: list[dict[str, Any]]) -> dict[str, Any]:
    closed = int(metric.get("closed_trades") or 0)
    total_return = _num(metric.get("return_pct"))
    max_drawdown = _num(metric.get("max_drawdown_pct"))
    expectancy = _num(metric.get("expectancy_pct"))
    profit_factor = _num(metric.get("profit_factor"))

    traded = [row for row in market_rows if int(row.get("closed_trades") or 0) > 0]
    traded_markets = len(traded)
    profitable_markets = sum(1 for row in traded if _num(row.get("sum_return_pct")) > 0.0)
    profitable_share = profitable_markets / traded_markets if traded_markets else 0.0

    avg_market_returns = [
        _num(row.get("sum_return_pct")) / max(1, int(row.get("closed_trades") or 0))
        for row in traded
    ]
    median_market_return = median(avg_market_returns) if avg_market_returns else 0.0

    realized_abs = [abs(_num(row.get("realized_pnl"))) for row in traded]
    realized_abs_total = sum(realized_abs)
    concentration = max(realized_abs, default=0.0) / realized_abs_total if realized_abs_total > 0 else 0.0

    gates = [
        _gate(
            "sample_size", "완료 거래 표본", closed >= MIN_CLOSED_TRADES,
            closed, f">= {MIN_CLOSED_TRADES}",
        ),
        _gate(
            "market_breadth", "거래 종목 분산", traded_markets >= MIN_TRADED_MARKETS,
            traded_markets, f">= {MIN_TRADED_MARKETS}",
        ),
        _gate(
            "profitable_market_share", "수익 종목 비율",
            profitable_share >= MIN_PROFITABLE_MARKET_SHARE,
            round(profitable_share, 4), f">= {MIN_PROFITABLE_MARKET_SHARE:.0%}",
        ),
        _gate(
            "pnl_concentration", "손익 집중도",
            concentration <= MAX_PNL_CONCENTRATION_SHARE if traded_markets else False,
            round(concentration, 4), f"<= {MAX_PNL_CONCENTRATION_SHARE:.0%}",
        ),
        _gate(
            "drawdown", "최대 낙폭",
            max_drawdown >= MAX_DRAWDOWN_FLOOR_PCT,
            round(max_drawdown, 4), f">= {MAX_DRAWDOWN_FLOOR_PCT:.1f}%",
        ),
        _gate(
            "expectancy", "거래 기대값", expectancy > MIN_EXPECTANCY_PCT,
            round(expectancy, 4), f"> {MIN_EXPECTANCY_PCT:.1f}%",
        ),
        _gate(
            "profit_factor", "Profit Factor", profit_factor >= MIN_PROFIT_FACTOR,
            round(profit_factor, 4), f">= {MIN_PROFIT_FACTOR:.2f}",
        ),
        _gate(
            "positive_return", "누적 수익률", total_return > MIN_TOTAL_RETURN_PCT,
            round(total_return, 6), f"> {MIN_TOTAL_RETURN_PCT:.1f}%",
        ),
    ]

    sample_ready = closed >= MIN_CLOSED_TRADES and traded_markets >= MIN_TRADED_MARKETS
    all_passed = all(bool(row["passed"]) for row in gates)
    if not sample_ready:
        status = "warming"
    elif all_passed:
        status = "candidate"
    else:
        status = "rejected"

    return {
        "status": status,
        "eligible_for_promotion": status == "candidate",
        "auto_promote": False,
        "paper_only": True,
        "passed_gates": sum(1 for row in gates if row["passed"]),
        "total_gates": len(gates),
        "sample_progress": round(min(1.0, closed / MIN_CLOSED_TRADES), 4),
        "breadth_progress": round(min(1.0, traded_markets / MIN_TRADED_MARKETS), 4),
        "closed_trades": closed,
        "traded_markets": traded_markets,
        "profitable_markets": profitable_markets,
        "profitable_market_share": round(profitable_share, 4),
        "pnl_concentration_share": round(concentration, 4),
        "median_market_trade_return_pct": round(median_market_return, 4),
        "gates": gates,
    }


def read_strategy_lab_candidates(path: Path = DB_PATH) -> dict[str, Any]:
    base = {
        "version": 1,
        "paper_only": True,
        "auto_promote": False,
        "criteria": candidate_criteria(),
        "evaluations": {},
        "summary": {"candidate": 0, "warming": 0, "rejected": 0, "total": 0},
    }
    if not path.exists():
        return base
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        required = {"strategy_lab_metrics", "strategy_lab_accounts", "strategy_lab_experiments"}
        if not required.issubset(tables):
            return base
        metrics = conn.execute(
            """SELECT m.*,e.status AS experiment_status
               FROM strategy_lab_metrics m
               JOIN strategy_lab_experiments e USING(experiment_id)
               ORDER BY m.exchange,m.experiment_id"""
        ).fetchall()
        accounts = conn.execute(
            """SELECT experiment_id,market,closed_trades,sum_return_pct,realized_pnl,max_drawdown_pct
               FROM strategy_lab_accounts ORDER BY experiment_id,market"""
        ).fetchall()
        by_experiment: dict[str, list[dict[str, Any]]] = {}
        for source in accounts:
            row = dict(source)
            by_experiment.setdefault(str(row["experiment_id"]), []).append(row)

        evaluations: dict[str, dict[str, Any]] = {}
        summary = {"candidate": 0, "warming": 0, "rejected": 0, "total": 0}
        for source in metrics:
            metric = dict(source)
            exp_id = str(metric["experiment_id"])
            evaluation = evaluate_candidate(metric, by_experiment.get(exp_id, []))
            if str(metric.get("experiment_status") or "running") != "running":
                evaluation["status"] = "paused"
                evaluation["eligible_for_promotion"] = False
            evaluation["experiment_id"] = exp_id
            evaluation["exchange"] = str(metric.get("exchange") or "")
            evaluations[exp_id] = evaluation
            if evaluation["status"] in summary:
                summary[evaluation["status"]] += 1
            summary["total"] += 1
        base["evaluations"] = evaluations
        base["summary"] = summary
        return base
    except sqlite3.Error:
        return base
    finally:
        conn.close()
