from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH


def _json(value: Any, fallback: Any) -> Any:
    try:
        parsed = json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return parsed


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def audit_listing_history(path: Path = DB_PATH, *, rows: int = 6) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"ok": True, "configured": True, "path_exists": False, "case_count": 0}

    conn = sqlite3.connect(str(target), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        required = (
            "listing_history_cases",
            "listing_history_sources",
            "listing_history_candles",
            "listing_history_features",
        )
        existing = {name: _table_exists(conn, name) for name in required}
        if not existing["listing_history_cases"]:
            return {
                "ok": True,
                "configured": True,
                "path_exists": True,
                "tables": existing,
                "case_count": 0,
            }

        case_rows = conn.execute(
            """
            SELECT case_key,domestic_exchange,domestic_market,domestic_notice_id,symbol,
                   announcement_at,domestic_open_at,domestic_open_price,
                   identity_verified,identity_confidence,status,created_at,updated_at
            FROM listing_history_cases
            ORDER BY updated_at DESC
            """
        ).fetchall()
        statuses = Counter(str(row["status"] or "unknown") for row in case_rows)
        identity_verified = sum(1 for row in case_rows if int(row["identity_verified"] or 0) > 0)
        with_open_time = sum(1 for row in case_rows if float(row["domestic_open_at"] or 0) > 0)
        with_open_price = sum(1 for row in case_rows if float(row["domestic_open_price"] or 0) > 0)

        source_rows = conn.execute(
            """
            SELECT case_key,source_exchange,source_market,base_asset,quote_asset,
                   source_listing_at,first_price,match_confidence,match_basis_json,updated_at
            FROM listing_history_sources
            ORDER BY updated_at DESC
            """
        ).fetchall() if existing["listing_history_sources"] else []
        source_counts = Counter(str(row["source_exchange"] or "unknown") for row in source_rows)

        candle_count = int(conn.execute(
            "SELECT COUNT(*) FROM listing_history_candles"
        ).fetchone()[0]) if existing["listing_history_candles"] else 0

        feature_rows = conn.execute(
            """
            SELECT case_key,source_exchange,source_market,feature_version,calculated_at,feature_json
            FROM listing_history_features
            ORDER BY calculated_at DESC
            """
        ).fetchall() if existing["listing_history_features"] else []

        feature_samples: list[dict[str, Any]] = []
        for row in feature_rows[: max(1, min(20, int(rows)))]:
            payload = _json(row["feature_json"], {})
            pre = payload.get("prelisting") if isinstance(payload, dict) and isinstance(payload.get("prelisting"), dict) else {}
            post = payload.get("postlisting") if isinstance(payload, dict) and isinstance(payload.get("postlisting"), dict) else {}
            windows = pre.get("windows") if isinstance(pre.get("windows"), dict) else {}
            post_windows = post.get("windows") if isinstance(post.get("windows"), dict) else {}
            feature_samples.append(
                {
                    "case_key": row["case_key"],
                    "source_exchange": row["source_exchange"],
                    "source_market": row["source_market"],
                    "feature_version": int(row["feature_version"] or 0),
                    "prelisting_status": pre.get("status") or "",
                    "prelisting_windows": {
                        name: windows.get(name)
                        for name in ("t7d", "t5d", "t3d", "t1d", "t6h", "t1h")
                        if name in windows
                    },
                    "postlisting_status": post.get("status") or "",
                    "postlisting_windows": {
                        name: post_windows.get(name)
                        for name in ("m5", "h1", "h6", "h24", "d3", "d7")
                        if name in post_windows
                    },
                }
            )

        latest_cases = [
            {
                "case_key": row["case_key"],
                "exchange": row["domestic_exchange"],
                "market": row["domestic_market"],
                "notice_id": row["domestic_notice_id"],
                "status": row["status"],
                "identity_verified": bool(row["identity_verified"]),
                "identity_confidence": float(row["identity_confidence"] or 0),
                "announcement_at": float(row["announcement_at"] or 0),
                "domestic_open_at": float(row["domestic_open_at"] or 0),
                "domestic_open_price": float(row["domestic_open_price"] or 0),
            }
            for row in case_rows[: max(1, min(20, int(rows)))]
        ]

        latest_sources = [
            {
                "case_key": row["case_key"],
                "source_exchange": row["source_exchange"],
                "source_market": row["source_market"],
                "quote_asset": row["quote_asset"],
                "source_listing_at": float(row["source_listing_at"] or 0),
                "first_price": float(row["first_price"] or 0),
                "match_confidence": float(row["match_confidence"] or 0),
                "match_basis": _json(row["match_basis_json"], {}),
            }
            for row in source_rows[: max(1, min(20, int(rows)))]
        ]

        return {
            "ok": True,
            "configured": True,
            "path_exists": True,
            "tables": existing,
            "case_count": len(case_rows),
            "status_counts": dict(sorted(statuses.items())),
            "identity_verified": identity_verified,
            "with_domestic_open_time": with_open_time,
            "with_domestic_open_price": with_open_price,
            "source_count": len(source_rows),
            "sources_by_exchange": dict(sorted(source_counts.items())),
            "candle_count": candle_count,
            "feature_count": len(feature_rows),
            "latest_cases": latest_cases,
            "latest_sources": latest_sources,
            "feature_samples": feature_samples,
            "paper_only": True,
            "can_place_orders": False,
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only audit of domestic listing-history research")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite path")
    parser.add_argument("--rows", type=int, default=6, help="Sample rows")
    args = parser.parse_args()
    result = audit_listing_history(Path(args.db), rows=max(1, min(20, int(args.rows))))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
