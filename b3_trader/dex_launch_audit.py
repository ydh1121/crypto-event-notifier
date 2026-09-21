from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH


TABLES = (
    "dex_launch_case_status",
    "dex_launch_assets",
    "dex_launch_pools",
    "dex_launch_candles",
    "dex_launch_features",
)


def _json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def audit_dex_launch(path: Path | str = DB_PATH) -> dict[str, Any]:
    db_path = Path(path)
    if not db_path.exists():
        return {"ok": False, "path_exists": False, "tables": {name: False for name in TABLES}}
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        existing = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        table_state = {name: name in existing for name in TABLES}
        if not all(table_state.values()):
            return {"ok": False, "path_exists": True, "tables": table_state}
        statuses = {
            str(row["status"]): int(row["n"])
            for row in conn.execute(
                "SELECT status,COUNT(*) AS n FROM dex_launch_case_status GROUP BY status ORDER BY status"
            ).fetchall()
        }
        latest_cases = [
            dict(row)
            for row in conn.execute(
                """SELECT case_key,coingecko_id,status,contract_count,accepted_pool_count,error,updated_at
                   FROM dex_launch_case_status ORDER BY updated_at DESC LIMIT 8"""
            ).fetchall()
        ]
        latest_assets = [
            dict(row)
            for row in conn.execute(
                """SELECT asset_key,case_key,coingecko_id,platform_id,network_id,token_address,identity_status,updated_at
                   FROM dex_launch_assets ORDER BY updated_at DESC LIMIT 8"""
            ).fetchall()
        ]
        latest_pools = [
            dict(row)
            for row in conn.execute(
                """SELECT asset_key,pool_address,dex_id,pool_name,pool_created_at,reserve_usd,volume_h24_usd,
                          gate_status,selected_primary,updated_at
                   FROM dex_launch_pools ORDER BY selected_primary DESC,updated_at DESC LIMIT 12"""
            ).fetchall()
        ]
        feature_samples: list[dict[str, Any]] = []
        for row in conn.execute(
            """SELECT asset_key,pool_address,feature_version,calculated_at,feature_json
               FROM dex_launch_features ORDER BY calculated_at DESC LIMIT 6"""
        ).fetchall():
            payload = _json(row["feature_json"])
            domestic = payload.get("domestic_listing_window") if isinstance(payload.get("domestic_listing_window"), dict) else {}
            launch = payload.get("pool_launch_window") if isinstance(payload.get("pool_launch_window"), dict) else {}
            quality = payload.get("pool_quality") if isinstance(payload.get("pool_quality"), dict) else {}
            feature_samples.append(
                {
                    "asset_key": row["asset_key"],
                    "pool_address": row["pool_address"],
                    "feature_version": int(row["feature_version"] or 0),
                    "pool_quality": quality,
                    "domestic_status": domestic.get("status"),
                    "domestic_reference": domestic.get("reference"),
                    "domestic_pre": domestic.get("pre"),
                    "domestic_post": domestic.get("post"),
                    "p5m_exact_minute": bool(domestic.get("p5m_exact_minute")),
                    "launch_status": launch.get("status"),
                    "launch_age_days_at_domestic_listing": launch.get("pool_age_days_at_domestic_listing"),
                    "launch_windows": launch.get("windows"),
                }
            )
        return {
            "ok": True,
            "path_exists": True,
            "tables": table_state,
            "case_count": int(conn.execute("SELECT COUNT(*) FROM dex_launch_case_status").fetchone()[0]),
            "case_status_counts": statuses,
            "asset_count": int(conn.execute("SELECT COUNT(*) FROM dex_launch_assets").fetchone()[0]),
            "pool_count": int(conn.execute("SELECT COUNT(*) FROM dex_launch_pools").fetchone()[0]),
            "accepted_pool_count": int(conn.execute("SELECT COUNT(*) FROM dex_launch_pools WHERE gate_status='accepted'").fetchone()[0]),
            "primary_pool_count": int(conn.execute("SELECT COUNT(*) FROM dex_launch_pools WHERE selected_primary=1").fetchone()[0]),
            "candle_count": int(conn.execute("SELECT COUNT(*) FROM dex_launch_candles").fetchone()[0]),
            "feature_count": int(conn.execute("SELECT COUNT(*) FROM dex_launch_features").fetchone()[0]),
            "latest_cases": latest_cases,
            "latest_assets": latest_assets,
            "latest_pools": latest_pools,
            "feature_samples": feature_samples,
            "raw_candles_cloud_projected": False,
            "paper_only": True,
            "can_place_orders": False,
        }
    finally:
        conn.close()


def main() -> None:
    print(json.dumps(audit_dex_launch(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
