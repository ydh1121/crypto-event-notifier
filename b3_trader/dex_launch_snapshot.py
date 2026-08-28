from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from .dex_launch_store import DEFAULT_DB_PATH

PRE_WINDOWS = ("t7d", "t5d", "t3d", "t1d", "t6h", "t1h")
POST_WINDOWS = ("p5m", "p1h", "p6h", "p24h", "p3d", "p7d")
LAUNCH_WINDOWS = ("p5m", "p1h", "p6h", "p24h")
DEFAULT_CASE_LIMIT = 16
DEFAULT_ASSET_LIMIT_PER_CASE = 2


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _json(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _return(point: Any, key: str) -> float | None:
    return _num(point.get(key)) if isinstance(point, dict) else None


def _empty(*, path_exists: bool) -> dict[str, Any]:
    return {
        "version": 1,
        "paper_only": True,
        "shadow_only": True,
        "raw_candles_included": False,
        "path_exists": path_exists,
        "case_count": 0,
        "asset_count": 0,
        "pool_count": 0,
        "accepted_pool_count": 0,
        "primary_pool_count": 0,
        "feature_count": 0,
        "status_counts": {},
        "updated_at": 0.0,
        "cases": [],
    }


def _compact_feature(payload: dict[str, Any], feature_version: int) -> dict[str, Any]:
    quality = payload.get("pool_quality") if isinstance(payload.get("pool_quality"), dict) else {}
    domestic = payload.get("domestic_listing_window") if isinstance(payload.get("domestic_listing_window"), dict) else {}
    launch = payload.get("pool_launch_window") if isinstance(payload.get("pool_launch_window"), dict) else {}
    pre = domestic.get("pre") if isinstance(domestic.get("pre"), dict) else {}
    post = domestic.get("post") if isinstance(domestic.get("post"), dict) else {}
    launch_windows = launch.get("windows") if isinstance(launch.get("windows"), dict) else {}
    reference = domestic.get("reference") if isinstance(domestic.get("reference"), dict) else {}
    launch_reference = launch.get("reference") if isinstance(launch.get("reference"), dict) else {}
    return {
        "feature_version": int(feature_version or payload.get("version") or 0),
        "pool_quality": {
            "reserve_usd": _num(quality.get("reserve_usd")),
            "volume_h24_usd": _num(quality.get("volume_h24_usd")),
            "passed": bool(quality.get("passed")),
        },
        "domestic": {
            "status": str(domestic.get("status") or ""),
            "reference_price": _num(reference.get("price")),
            "pre_returns": {
                key: _return(pre.get(key), "return_to_domestic_open_pct") for key in PRE_WINDOWS
            },
            "post_returns": {
                key: _return(post.get(key), "return_from_domestic_open_pct") for key in POST_WINDOWS
            },
            "p5m_exact_minute": bool(domestic.get("p5m_exact_minute")),
        },
        "launch": {
            "status": str(launch.get("status") or ""),
            "reference_price": _num(launch_reference.get("price")),
            "pool_age_days_at_domestic_listing": _num(launch.get("pool_age_days_at_domestic_listing")),
            "returns": {
                key: _return(launch_windows.get(key), "return_from_launch_pct") for key in LAUNCH_WINDOWS
            },
            "p5m_exact_minute": bool(launch.get("p5m_exact_minute")),
        },
    }


def build_dex_launch_snapshot(
    path: Path | str = DEFAULT_DB_PATH,
    *,
    case_limit: int = DEFAULT_CASE_LIMIT,
    asset_limit_per_case: int = DEFAULT_ASSET_LIMIT_PER_CASE,
) -> dict[str, Any]:
    """Build a compact Viewer-safe DEX launch research projection.

    Exact contract/pool identity and derived features may be projected. Raw DEX
    OHLCV rows never leave local SQLite and are intentionally not queried here.
    """

    db_path = Path(path)
    if not db_path.exists():
        return _empty(path_exists=False)

    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        required = {
            "dex_launch_case_status",
            "dex_launch_assets",
            "dex_launch_pools",
            "dex_launch_features",
        }
        if not required.issubset(tables):
            return _empty(path_exists=True)

        status_counts = {
            str(row["status"] or "unknown"): int(row["n"] or 0)
            for row in conn.execute(
                "SELECT status,COUNT(*) AS n FROM dex_launch_case_status GROUP BY status"
            ).fetchall()
        }
        case_count = int(conn.execute("SELECT COUNT(*) FROM dex_launch_case_status").fetchone()[0])
        asset_count = int(conn.execute("SELECT COUNT(*) FROM dex_launch_assets").fetchone()[0])
        pool_count = int(conn.execute("SELECT COUNT(*) FROM dex_launch_pools").fetchone()[0])
        accepted_pool_count = int(
            conn.execute("SELECT COUNT(*) FROM dex_launch_pools WHERE gate_status='accepted'").fetchone()[0]
        )
        primary_pool_count = int(
            conn.execute("SELECT COUNT(*) FROM dex_launch_pools WHERE selected_primary=1").fetchone()[0]
        )
        feature_count = int(conn.execute("SELECT COUNT(*) FROM dex_launch_features").fetchone()[0])
        latest_case = float(conn.execute("SELECT COALESCE(MAX(updated_at),0) FROM dex_launch_case_status").fetchone()[0] or 0)
        latest_asset = float(conn.execute("SELECT COALESCE(MAX(updated_at),0) FROM dex_launch_assets").fetchone()[0] or 0)
        latest_pool = float(conn.execute("SELECT COALESCE(MAX(updated_at),0) FROM dex_launch_pools").fetchone()[0] or 0)
        latest_feature = float(conn.execute("SELECT COALESCE(MAX(calculated_at),0) FROM dex_launch_features").fetchone()[0] or 0)

        listing_available = "listing_history_cases" in tables
        limit = max(1, min(64, int(case_limit)))
        if listing_available:
            case_rows = conn.execute(
                """
                SELECT d.case_key,d.coingecko_id,d.status,d.contract_count,d.accepted_pool_count,d.updated_at,
                       c.domestic_exchange,c.domestic_market,c.symbol,c.domestic_open_at
                FROM dex_launch_case_status d
                LEFT JOIN listing_history_cases c ON c.case_key=d.case_key
                ORDER BY d.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            case_rows = conn.execute(
                """
                SELECT case_key,coingecko_id,status,contract_count,accepted_pool_count,updated_at,
                       '' AS domestic_exchange,'' AS domestic_market,'' AS symbol,0 AS domestic_open_at
                FROM dex_launch_case_status
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        cases: list[dict[str, Any]] = []
        asset_limit = max(1, min(4, int(asset_limit_per_case)))
        for case_row in case_rows:
            assets: list[dict[str, Any]] = []
            asset_rows = conn.execute(
                """
                SELECT a.asset_key,a.coingecko_id,a.platform_id,a.network_id,a.token_address,a.identity_status,a.updated_at,
                       p.pool_address,p.dex_id,p.pool_name,p.pool_created_at,p.reserve_usd,p.volume_h24_usd,
                       p.gate_status,p.selected_primary,
                       COALESCE(f.feature_version,0) AS feature_version,
                       COALESCE(f.feature_json,'{}') AS feature_json
                FROM dex_launch_assets a
                LEFT JOIN dex_launch_pools p
                  ON p.asset_key=a.asset_key AND p.selected_primary=1
                LEFT JOIN dex_launch_features f
                  ON f.asset_key=a.asset_key AND f.pool_address=p.pool_address
                WHERE a.case_key=?
                ORDER BY CASE WHEN p.selected_primary=1 THEN 0 ELSE 1 END,a.updated_at DESC
                LIMIT ?
                """,
                (str(case_row["case_key"]), asset_limit),
            ).fetchall()
            for row in asset_rows:
                pool = None
                if row["pool_address"]:
                    pool = {
                        "pool_address": str(row["pool_address"] or ""),
                        "dex_id": str(row["dex_id"] or ""),
                        "pool_name": str(row["pool_name"] or ""),
                        "pool_created_at": _num(row["pool_created_at"]),
                        "reserve_usd": _num(row["reserve_usd"]),
                        "volume_h24_usd": _num(row["volume_h24_usd"]),
                        "gate_status": str(row["gate_status"] or ""),
                        "selected_primary": bool(row["selected_primary"]),
                    }
                feature_json = _json(row["feature_json"])
                assets.append(
                    {
                        "coingecko_id": str(row["coingecko_id"] or ""),
                        "platform_id": str(row["platform_id"] or ""),
                        "network_id": str(row["network_id"] or ""),
                        "token_address": str(row["token_address"] or ""),
                        "identity_status": str(row["identity_status"] or ""),
                        "primary_pool": pool,
                        "feature": _compact_feature(feature_json, int(row["feature_version"] or 0)) if feature_json else None,
                    }
                )

            cases.append(
                {
                    "case_key": str(case_row["case_key"] or ""),
                    "exchange": str(case_row["domestic_exchange"] or ""),
                    "market": str(case_row["domestic_market"] or ""),
                    "symbol": str(case_row["symbol"] or ""),
                    "domestic_open_at": _num(case_row["domestic_open_at"]),
                    "coingecko_id": str(case_row["coingecko_id"] or ""),
                    "status": str(case_row["status"] or ""),
                    "contract_count": int(case_row["contract_count"] or 0),
                    "accepted_pool_count": int(case_row["accepted_pool_count"] or 0),
                    "assets": assets,
                }
            )

        return {
            "version": 1,
            "paper_only": True,
            "shadow_only": True,
            "raw_candles_included": False,
            "path_exists": True,
            "case_count": case_count,
            "asset_count": asset_count,
            "pool_count": pool_count,
            "accepted_pool_count": accepted_pool_count,
            "primary_pool_count": primary_pool_count,
            "feature_count": feature_count,
            "status_counts": dict(sorted(Counter(status_counts).items())),
            "updated_at": max(latest_case, latest_asset, latest_pool, latest_feature),
            "cases": cases,
        }
    except sqlite3.Error:
        return _empty(path_exists=True)
    finally:
        conn.close()
