from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

TRADE_TABLE = "research_market_trade_flow_mx"
BOOK_TABLE = "research_market_orderbook_flow_mx"
FEATURE_TABLE = "research_market_flow_feature_mx"
CURSOR_TABLE = "research_market_flow_cursor_mx"


def audit_market_flow(path: Path | str = DB_PATH, *, now: float | None = None) -> dict[str, Any]:
    checked_at = float(now or time.time())
    db_path = Path(path)
    if not db_path.exists():
        return {
            "ok": True,
            "status": "database_missing",
            "path_exists": False,
            "tables_ready": False,
            "trade_rows": 0,
            "feature_rows": 0,
            "checked_at": checked_at,
        }
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        existing = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?,?,?,?)",
                (TRADE_TABLE, BOOK_TABLE, FEATURE_TABLE, CURSOR_TABLE),
            ).fetchall()
        }
        tables_ready = {TRADE_TABLE, BOOK_TABLE, FEATURE_TABLE, CURSOR_TABLE}.issubset(existing)
        if not tables_ready:
            return {
                "ok": True,
                "status": "table_missing",
                "path_exists": True,
                "tables_ready": False,
                "existing_tables": sorted(existing),
                "trade_rows": 0,
                "feature_rows": 0,
                "checked_at": checked_at,
            }
        trade = conn.execute(
            """SELECT COUNT(*) AS rows,
                      SUM(CASE WHEN aggressor_side NOT IN ('BID','ASK') THEN 1 ELSE 0 END) AS invalid_side_rows,
                      SUM(CASE WHEN side_source!='exchange' THEN 1 ELSE 0 END) AS non_exchange_side_rows,
                      MAX(received_at) AS received_at
               FROM research_market_trade_flow_mx"""
        ).fetchone()
        book = conn.execute(
            """SELECT COUNT(*) AS rows,
                      SUM(CASE WHEN best_bid IS NOT NULL AND best_ask IS NOT NULL AND best_ask<best_bid THEN 1 ELSE 0 END) AS crossed_book_rows,
                      MAX(received_at) AS received_at
               FROM research_market_orderbook_flow_mx"""
        ).fetchone()
        feature = conn.execute(
            """SELECT COUNT(*) AS rows,
                      SUM(CASE WHEN continuity_complete=1 AND side_coverage_pct<100 THEN 1 ELSE 0 END) AS complete_side_violations,
                      SUM(CASE WHEN continuity_complete=1 AND cvd_anchor_ts<=0 THEN 1 ELSE 0 END) AS complete_anchor_violations,
                      MAX(received_at) AS received_at
               FROM research_market_flow_feature_mx"""
        ).fetchone()
        cursor = conn.execute(
            """SELECT COUNT(*) AS markets,
                      SUM(last_cycle_complete) AS complete_markets,
                      MAX(updated_at) AS updated_at
               FROM research_market_flow_cursor_mx"""
        ).fetchone()
        samples = conn.execute(
            """SELECT exchange,market,feature_ts,window_seconds,trade_count,delta_quote,delta_pct,
                      observed_cvd_quote,cvd_anchor_ts,continuity_complete,side_coverage_pct,
                      spread_bps,imbalance_5,imbalance_all,received_at
               FROM research_market_flow_feature_mx
               ORDER BY feature_ts DESC LIMIT 12"""
        ).fetchall()
        return {
            "ok": True,
            "status": "ready",
            "path_exists": True,
            "tables_ready": True,
            "trade_rows": int(trade["rows"] or 0),
            "orderbook_rows": int(book["rows"] or 0),
            "feature_rows": int(feature["rows"] or 0),
            "cursor_markets": int(cursor["markets"] or 0),
            "last_cycle_complete_markets": int(cursor["complete_markets"] or 0),
            "invalid_side_rows": int(trade["invalid_side_rows"] or 0),
            "non_exchange_side_rows": int(trade["non_exchange_side_rows"] or 0),
            "crossed_book_rows": int(book["crossed_book_rows"] or 0),
            "complete_side_violations": int(feature["complete_side_violations"] or 0),
            "complete_anchor_violations": int(feature["complete_anchor_violations"] or 0),
            "received_at": max(
                float(trade["received_at"] or 0.0),
                float(book["received_at"] or 0.0),
                float(feature["received_at"] or 0.0),
                float(cursor["updated_at"] or 0.0),
            ),
            "samples": [dict(row) for row in samples],
            "aggressor_side": "exchange_provided_only",
            "cvd_scope": "local_contiguous_observation",
            "paper_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "raw_cloud_projection": False,
            "feature_version": 1,
            "checked_at": checked_at,
        }
    finally:
        conn.close()
