from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

TABLE = "research_market_cross_exchange_gap_mx"


def audit_market_cross_exchange_gap(path: Path | str = DB_PATH, *, now: float | None = None) -> dict[str, Any]:
    checked_at = float(now or time.time())
    db_path = Path(path)
    if not db_path.exists():
        return {
            "ok": True,
            "status": "database_missing",
            "path_exists": False,
            "table_exists": False,
            "row_count": 0,
            "gap_ready_rows": 0,
            "checked_at": checked_at,
        }
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE,),
        ).fetchone()
        if not exists:
            return {
                "ok": True,
                "status": "table_missing",
                "path_exists": True,
                "table_exists": False,
                "row_count": 0,
                "gap_ready_rows": 0,
                "checked_at": checked_at,
            }
        row = conn.execute(
            """SELECT COUNT(*) AS rows,
                      SUM(CASE WHEN identity_verified=1 THEN 1 ELSE 0 END) AS identity_verified_rows,
                      SUM(CASE WHEN gap_ready=1 THEN 1 ELSE 0 END) AS gap_ready_rows,
                      SUM(CASE WHEN gap_ready=1 AND (upbit_vs_bithumb_pct IS NULL OR absolute_gap_pct IS NULL) THEN 1 ELSE 0 END) AS ready_null_violations,
                      SUM(CASE WHEN identity_verified=0 AND gap_ready=1 THEN 1 ELSE 0 END) AS identity_gate_violations,
                      MAX(received_at) AS received_at
               FROM research_market_cross_exchange_gap_mx"""
        ).fetchone()
        samples = conn.execute(
            """SELECT market,identity_basis,gap_ready,bithumb_price,upbit_price,
                      source_skew_seconds,upbit_vs_bithumb_pct,received_at
               FROM research_market_cross_exchange_gap_mx
               WHERE gap_ready=1 ORDER BY absolute_gap_pct DESC LIMIT 8"""
        ).fetchall()
        return {
            "ok": True,
            "status": "ready",
            "path_exists": True,
            "table_exists": True,
            "row_count": int(row["rows"] or 0),
            "identity_verified_rows": int(row["identity_verified_rows"] or 0),
            "gap_ready_rows": int(row["gap_ready_rows"] or 0),
            "ready_null_violations": int(row["ready_null_violations"] or 0),
            "identity_gate_violations": int(row["identity_gate_violations"] or 0),
            "received_at": float(row["received_at"] or 0.0),
            "samples": [dict(item) for item in samples],
            "source_timeframe": "1m",
            "max_price_age_seconds": 900.0,
            "max_source_skew_seconds": 300.0,
            "feature_version": 1,
            "paper_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "raw_cloud_projection": False,
            "checked_at": checked_at,
        }
    finally:
        conn.close()
