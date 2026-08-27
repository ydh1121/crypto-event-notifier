from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from .listing_history_store import DEFAULT_DB_PATH

PRE_WINDOWS = ("t7d", "t5d", "t3d", "t1d", "t6h", "t1h")
POST_WINDOWS = ("p5m", "p1h", "p6h", "p24h", "p3d", "p7d")
DEFAULT_CASE_LIMIT = 24


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _empty_payload(*, path_exists: bool) -> dict[str, Any]:
    return {
        "version": 1,
        "paper_only": True,
        "shadow_only": True,
        "raw_candles_included": False,
        "path_exists": path_exists,
        "case_count": 0,
        "source_count": 0,
        "feature_count": 0,
        "status_counts": {},
        "updated_at": 0.0,
        "cases": [],
    }


def _compact_feature(payload: dict[str, Any], feature_version: int) -> dict[str, Any]:
    pre = payload.get("prelisting") if isinstance(payload.get("prelisting"), dict) else {}
    pre_windows = pre.get("windows") if isinstance(pre.get("windows"), dict) else {}
    post = payload.get("foreign_postlisting") if isinstance(payload.get("foreign_postlisting"), dict) else {}
    post_windows = post.get("windows") if isinstance(post.get("windows"), dict) else {}
    fine = payload.get("fine_reaction_source") if isinstance(payload.get("fine_reaction_source"), dict) else {}
    quote = payload.get("quote_to_krw") if isinstance(payload.get("quote_to_krw"), dict) else {}

    return {
        "feature_version": int(feature_version or payload.get("version") or 0),
        "domestic_listing_premium_pct": _number(pre.get("domestic_listing_premium_pct")),
        "foreign_first_to_foreign_open_pct": _number(pre.get("foreign_first_to_foreign_open_pct")),
        "foreign_open_vs_pre_ath_pct": _number(pre.get("foreign_open_vs_pre_ath_pct")),
        "foreign_open_vs_pre_atl_pct": _number(pre.get("foreign_open_vs_pre_atl_pct")),
        "prelisting_returns": {
            key: _number(pre_windows.get(f"{key}_to_foreign_open_pct")) for key in PRE_WINDOWS
        },
        "postlisting_returns": {
            key: _number(post_windows.get(f"{key}_return_pct")) for key in POST_WINDOWS
        },
        "p5m_source_interval_seconds": int(post.get("p5m_source_interval_seconds") or 0) or None,
        "fine_reaction_status": str(fine.get("status") or ""),
        "fine_reaction_candles": int(fine.get("candles") or 0),
        "quote_to_krw": {
            "rate": _number(quote.get("rate")),
            "source_exchange": str(quote.get("source_exchange") or ""),
            "source_market": str(quote.get("source_market") or ""),
        },
        "currency_safe": bool(pre.get("currency_safe", False)),
    }


def build_listing_history_snapshot(
    path: Path | str = DEFAULT_DB_PATH,
    *,
    case_limit: int = DEFAULT_CASE_LIMIT,
) -> dict[str, Any]:
    """Build the Viewer-safe listing research projection.

    Only case metadata, verified source metadata and derived feature summaries are
    projected. Raw listing-history candles and OHLCV rows remain local SQLite data.
    """

    db_path = Path(path)
    if not db_path.exists():
        return _empty_payload(path_exists=False)

    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        required = {"listing_history_cases", "listing_history_sources", "listing_history_features"}
        if not required.issubset(tables):
            return _empty_payload(path_exists=True)

        counts = {
            str(row["status"] or "unknown"): int(row["count"] or 0)
            for row in conn.execute(
                "SELECT status,COUNT(*) AS count FROM listing_history_cases GROUP BY status"
            ).fetchall()
        }
        case_count = int(conn.execute("SELECT COUNT(*) FROM listing_history_cases").fetchone()[0])
        source_count = int(conn.execute("SELECT COUNT(*) FROM listing_history_sources").fetchone()[0])
        feature_count = int(conn.execute("SELECT COUNT(*) FROM listing_history_features").fetchone()[0])
        latest_case = float(conn.execute("SELECT COALESCE(MAX(updated_at),0) FROM listing_history_cases").fetchone()[0] or 0)
        latest_source = float(conn.execute("SELECT COALESCE(MAX(updated_at),0) FROM listing_history_sources").fetchone()[0] or 0)
        latest_feature = float(conn.execute("SELECT COALESCE(MAX(calculated_at),0) FROM listing_history_features").fetchone()[0] or 0)

        limit = max(1, min(100, int(case_limit)))
        case_rows = conn.execute(
            """
            SELECT case_key,domestic_exchange,domestic_market,domestic_notice_id,symbol,
                   announcement_at,domestic_open_at,domestic_open_price,
                   identity_verified,identity_confidence,status,updated_at
            FROM listing_history_cases
            ORDER BY CASE WHEN domestic_open_at>0 THEN domestic_open_at ELSE announcement_at END DESC,
                     updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        keys = [str(row["case_key"]) for row in case_rows]
        sources_by_case: dict[str, list[dict[str, Any]]] = {key: [] for key in keys}
        if keys:
            placeholders = ",".join("?" for _ in keys)
            source_rows = conn.execute(
                f"""
                SELECT s.case_key,s.source_exchange,s.source_market,s.quote_asset,
                       s.source_listing_at,s.first_price,s.match_confidence,s.updated_at,
                       COALESCE(f.feature_version,0) AS feature_version,
                       COALESCE(f.feature_json,'{{}}') AS feature_json
                FROM listing_history_sources s
                LEFT JOIN listing_history_features f
                  ON f.case_key=s.case_key
                 AND f.source_exchange=s.source_exchange
                 AND f.source_market=s.source_market
                WHERE s.case_key IN ({placeholders})
                ORDER BY s.case_key,s.match_confidence DESC,s.source_exchange,s.source_market
                """,
                keys,
            ).fetchall()
            for row in source_rows:
                source = {
                    "exchange": str(row["source_exchange"] or ""),
                    "market": str(row["source_market"] or ""),
                    "quote_asset": str(row["quote_asset"] or ""),
                    "listing_at": _number(row["source_listing_at"]),
                    "first_price": _number(row["first_price"]),
                    "match_confidence": _number(row["match_confidence"]),
                    "verified": True,
                }
                source.update(
                    _compact_feature(_json_object(row["feature_json"]), int(row["feature_version"] or 0))
                )
                sources_by_case.setdefault(str(row["case_key"]), []).append(source)

        cases = [
            {
                "case_key": str(row["case_key"] or ""),
                "exchange": str(row["domestic_exchange"] or ""),
                "market": str(row["domestic_market"] or ""),
                "symbol": str(row["symbol"] or ""),
                "notice_id": str(row["domestic_notice_id"] or ""),
                "status": str(row["status"] or ""),
                "announcement_at": _number(row["announcement_at"]),
                "domestic_open_at": _number(row["domestic_open_at"]),
                "domestic_open_price": _number(row["domestic_open_price"]),
                "identity_verified": bool(row["identity_verified"]),
                "identity_confidence": _number(row["identity_confidence"]),
                "sources": sources_by_case.get(str(row["case_key"]), []),
            }
            for row in case_rows
        ]
        return {
            "version": 1,
            "paper_only": True,
            "shadow_only": True,
            "raw_candles_included": False,
            "path_exists": True,
            "case_count": case_count,
            "source_count": source_count,
            "feature_count": feature_count,
            "status_counts": dict(sorted(Counter(counts).items())),
            "updated_at": max(latest_case, latest_source, latest_feature),
            "cases": cases,
        }
    except sqlite3.Error:
        return _empty_payload(path_exists=True)
    finally:
        conn.close()
