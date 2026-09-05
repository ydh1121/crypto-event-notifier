from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .market_relative_strength import BENCHMARK_MARKETS, HORIZON_DAYS, FEATURE_VERSION


def audit_market_relative_strength(path: Path | str = DB_PATH, *, now: float | None = None) -> dict[str, Any]:
    db_path = Path(path)
    checked_at = float(now or time.time())
    if not db_path.exists():
        return {
            "ok": True,
            "status": "database_missing",
            "path_exists": False,
            "table_exists": False,
            "row_count": 0,
            "exchanges": {},
            "checked_at": checked_at,
        }

    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_relative_strength_mx'"
        ).fetchone()
        if not exists:
            return {
                "ok": True,
                "status": "table_missing",
                "path_exists": True,
                "table_exists": False,
                "row_count": 0,
                "exchanges": {},
                "checked_at": checked_at,
            }

        row_count = int(conn.execute("SELECT COUNT(*) FROM research_market_relative_strength_mx").fetchone()[0])
        grouped = conn.execute(
            """SELECT exchange,COUNT(*) AS rows,COUNT(DISTINCT market) AS markets,
                      COUNT(DISTINCT horizon_days) AS horizons,
                      SUM(CASE WHEN breadth_ready=1 THEN 1 ELSE 0 END) AS breadth_ready_rows,
                      MAX(breadth_coverage_pct) AS max_breadth_coverage_pct,
                      MAX(received_at) AS received_at,MAX(as_of_ts) AS as_of_ts,
                      MAX(feature_version) AS feature_version
               FROM research_market_relative_strength_mx
               GROUP BY exchange ORDER BY exchange"""
        ).fetchall()
        exchanges: dict[str, Any] = {}
        for row in grouped:
            exchange = str(row["exchange"])
            benchmark_rows = conn.execute(
                """SELECT market,COUNT(*) AS rows,COUNT(DISTINCT horizon_days) AS horizons
                   FROM research_market_relative_strength_mx
                   WHERE exchange=? AND market IN (?,?)
                   GROUP BY market ORDER BY market""",
                (exchange, BENCHMARK_MARKETS[0], BENCHMARK_MARKETS[1]),
            ).fetchall()
            exchanges[exchange] = {
                "rows": int(row["rows"] or 0),
                "markets": int(row["markets"] or 0),
                "horizons": int(row["horizons"] or 0),
                "breadth_ready_rows": int(row["breadth_ready_rows"] or 0),
                "max_breadth_coverage_pct": float(row["max_breadth_coverage_pct"] or 0.0),
                "received_at": float(row["received_at"] or 0.0),
                "as_of_ts": float(row["as_of_ts"] or 0.0),
                "feature_version": int(row["feature_version"] or 0),
                "benchmarks": {
                    str(item["market"]): {
                        "rows": int(item["rows"] or 0),
                        "horizons": int(item["horizons"] or 0),
                    }
                    for item in benchmark_rows
                },
            }

        breadth_null_violations = int(
            conn.execute(
                """SELECT COUNT(*) FROM research_market_relative_strength_mx
                   WHERE breadth_ready=0 AND (
                       breadth_positive_pct IS NOT NULL OR
                       breadth_median_return_pct IS NOT NULL OR
                       vs_breadth_median_pp IS NOT NULL
                   )"""
            ).fetchone()[0]
        )
        score_wiring_columns = [
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(research_market_relative_strength_mx)").fetchall()
            if str(row["name"]).lower() in {"score", "weight", "trade_intent", "order_id"}
        ]
        return {
            "ok": breadth_null_violations == 0 and not score_wiring_columns,
            "status": "ready" if row_count else "empty",
            "path_exists": True,
            "table_exists": True,
            "row_count": row_count,
            "expected_horizons": list(HORIZON_DAYS),
            "expected_benchmarks": list(BENCHMARK_MARKETS),
            "exchanges": exchanges,
            "breadth_null_violations": breadth_null_violations,
            "score_wiring_columns": score_wiring_columns,
            "feature_version": FEATURE_VERSION,
            "paper_only": True,
            "can_place_orders": False,
            "raw_cloud_projection": False,
            "checked_at": checked_at,
        }
    finally:
        conn.close()
