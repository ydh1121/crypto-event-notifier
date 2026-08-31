from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .market_ohlcv_collector import TIMEFRAMES
from .market_ohlcv_store import DEFAULT_RETENTION_BARS

TABLE = "research_market_ohlcv_mx"


def audit_market_ohlcv(path: Path | str = DB_PATH, *, now: float | None = None) -> dict[str, Any]:
    db_path = Path(path)
    checked_at = float(now or time.time())
    if not db_path.exists():
        return {
            "ok": True,
            "status": "database_missing",
            "path_exists": False,
            "table_exists": False,
            "row_count": 0,
            "timeframes": {},
            "retention_overflow_groups": 0,
            "checked_at": checked_at,
        }

    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        table_exists = bool(
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (TABLE,),
            ).fetchone()
        )
        if not table_exists:
            return {
                "ok": True,
                "status": "table_missing",
                "path_exists": True,
                "table_exists": False,
                "row_count": 0,
                "timeframes": {},
                "retention_overflow_groups": 0,
                "checked_at": checked_at,
            }

        row_count = int(conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0])
        grouped = conn.execute(
            f"""SELECT timeframe,COUNT(*) AS rows,
                       COUNT(DISTINCT exchange||':'||market) AS markets,
                       MIN(candle_ts) AS oldest_ts,MAX(candle_ts) AS latest_ts,
                       MAX(received_at) AS received_at
                FROM {TABLE}
                GROUP BY timeframe ORDER BY timeframe"""
        ).fetchall()
        overflow = int(
            conn.execute(
                f"""SELECT COUNT(*) FROM (
                        SELECT exchange,market,timeframe,COUNT(*) AS n
                        FROM {TABLE}
                        GROUP BY exchange,market,timeframe
                        HAVING n>?
                    )""",
                (DEFAULT_RETENTION_BARS,),
            ).fetchone()[0]
        )
        expected = {spec.name: spec for spec in TIMEFRAMES}
        timeframes: dict[str, Any] = {}
        for row in grouped:
            name = str(row["timeframe"])
            spec = expected.get(name)
            latest_ts = float(row["latest_ts"] or 0.0)
            freshness_limit = (spec.seconds * 3.0 if spec is not None else 0.0)
            timeframes[name] = {
                "rows": int(row["rows"] or 0),
                "markets": int(row["markets"] or 0),
                "oldest_ts": float(row["oldest_ts"] or 0.0),
                "latest_ts": latest_ts,
                "received_at": float(row["received_at"] or 0.0),
                "latest_age_seconds": max(0.0, checked_at - latest_ts) if latest_ts > 0 else None,
                "fresh": bool(latest_ts > 0 and freshness_limit > 0 and checked_at - latest_ts <= freshness_limit),
            }
        missing = [name for name in expected if name not in timeframes]
        return {
            "ok": overflow == 0,
            "status": "ready" if row_count > 0 and not missing and overflow == 0 else "accumulating",
            "path_exists": True,
            "table_exists": True,
            "row_count": row_count,
            "timeframes": timeframes,
            "missing_timeframes": missing,
            "retention_bars_per_market_timeframe": DEFAULT_RETENTION_BARS,
            "retention_overflow_groups": overflow,
            "raw_cloud_projection": False,
            "paper_only": True,
            "can_place_orders": False,
            "checked_at": checked_at,
        }
    finally:
        conn.close()
