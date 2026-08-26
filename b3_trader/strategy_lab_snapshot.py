from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .performance_analytics import read_performance_analytics
from .strategy_lab import FEE_RATE, SLIPPAGE_RATE, SOURCE_STRATEGY, STYLE_SPECS
from .strategy_lab_candidates import candidate_criteria, read_strategy_lab_candidates


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_strategy_lab_snapshot(path: Path = DB_PATH) -> dict[str, Any]:
    candidate_state = read_strategy_lab_candidates(path)
    analytics = read_performance_analytics(path)
    base = {
        "version": 3,
        "paper_only": True,
        "source": "research_market_memory_mx",
        "source_strategy": SOURCE_STRATEGY,
        "execution_model": {"fee_rate": FEE_RATE, "slippage_rate": SLIPPAGE_RATE},
        "styles": [asdict(spec) for spec in STYLE_SPECS.values()],
        "experiments": [],
        "candidate_criteria": candidate_criteria(),
        "candidate_summary": candidate_state.get("summary") or {},
        "source_cursors": {},
        "history_bucket_seconds": int(analytics.get("history_bucket_seconds") or 300),
        "strategy_equity_history": analytics.get("strategy_equity_history") or {},
        "coin_matrix": analytics.get("coin_matrix") or {"bithumb": [], "upbit": []},
        "paper_history": analytics.get("paper_history") or {"bithumb": [], "upbit": [], "combined": []},
        "updated_at": 0.0,
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
        required = {"strategy_lab_metrics", "strategy_lab_experiments", "strategy_lab_ingest_state"}
        if not required.issubset(tables):
            return base
        rows = conn.execute(
            """SELECT m.*,e.label,e.description,e.strategy_key,e.status
               FROM strategy_lab_metrics m
               JOIN strategy_lab_experiments e USING(experiment_id)
               ORDER BY m.exchange,m.return_pct DESC"""
        ).fetchall()
        evaluations = candidate_state.get("evaluations") if isinstance(candidate_state.get("evaluations"), dict) else {}
        experiments: list[dict[str, Any]] = []
        for source in rows:
            row = dict(source)
            for key in (
                "return_pct", "realized_pnl", "max_drawdown_pct", "win_rate_pct",
                "expectancy_pct", "profit_factor", "total_equity_krw", "aggregate_start_krw",
            ):
                row[key] = round(_num(row.get(key)), 6 if key == "return_pct" else 4)
            evaluation = evaluations.get(str(row.get("experiment_id")))
            if isinstance(evaluation, dict):
                row["candidate"] = evaluation
            experiments.append(row)
        cursors = {
            str(row["exchange"]): int(row["last_memory_id"])
            for row in conn.execute(
                "SELECT exchange,last_memory_id FROM strategy_lab_ingest_state ORDER BY exchange"
            ).fetchall()
        }
        base["experiments"] = experiments
        base["source_cursors"] = cursors
        base["updated_at"] = max([0.0] + [_num(row.get("updated_ts")) for row in experiments])
        return base
    except sqlite3.Error:
        return base
    finally:
        conn.close()
