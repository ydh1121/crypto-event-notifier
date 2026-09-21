from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

TABLE = "research_market_domestic_premium_mx"


def audit_market_domestic_premium(path: Path | str = DB_PATH, *, now: float | None = None) -> dict[str, Any]:
    checked_at = float(now or time.time())
    db_path = Path(path)
    if not db_path.exists():
        return {"ok": True, "status": "database_missing", "path_exists": False, "table_exists": False, "row_count": 0, "checked_at": checked_at}
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone()
        if not exists:
            return {"ok": True, "status": "table_missing", "path_exists": True, "table_exists": False, "row_count": 0, "checked_at": checked_at}
        row = conn.execute(
            """SELECT COUNT(*) AS rows,
                      SUM(CASE WHEN status='computed' THEN 1 ELSE 0 END) AS computed_rows,
                      SUM(CASE WHEN status='computed' AND identity_verified=0 THEN 1 ELSE 0 END) AS identity_gate_violations,
                      SUM(CASE WHEN status='computed' AND reference_price_krw IS NULL THEN 1 ELSE 0 END) AS reference_null_violations,
                      SUM(CASE WHEN status='computed' AND bithumb_premium_pct IS NULL AND upbit_premium_pct IS NULL THEN 1 ELSE 0 END) AS premium_null_violations,
                      MAX(received_at) AS received_at
               FROM research_market_domestic_premium_mx"""
        ).fetchone()
        samples = conn.execute(
            """SELECT market,provider,provider_id,reference_exchange,reference_market,
                      reference_quote_asset,reference_price_krw,bithumb_premium_pct,
                      upbit_premium_pct,foreign_verified_sources,foreign_price_gap_pct,received_at
               FROM research_market_domestic_premium_mx
               WHERE status='computed' ORDER BY received_at DESC LIMIT 8"""
        ).fetchall()
        return {
            "ok": True,
            "status": "ready",
            "path_exists": True,
            "table_exists": True,
            "row_count": int(row["rows"] or 0),
            "computed_rows": int(row["computed_rows"] or 0),
            "identity_gate_violations": int(row["identity_gate_violations"] or 0),
            "reference_null_violations": int(row["reference_null_violations"] or 0),
            "premium_null_violations": int(row["premium_null_violations"] or 0),
            "received_at": float(row["received_at"] or 0.0),
            "samples": [dict(item) for item in samples],
            "feature_version": 1,
            "paper_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "raw_cloud_projection": False,
            "checked_at": checked_at,
        }
    finally:
        conn.close()
