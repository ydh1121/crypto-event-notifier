from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH


MIN_USABLE_CASES = 20
MIN_EXACT_P5M_COVERAGE = 0.60
MAX_RESEARCH_ASSETS_PER_CASE = 2
REQUIRED_TABLES = {
    "dex_launch_case_status",
    "dex_launch_assets",
    "dex_launch_pools",
    "dex_launch_features",
}


def _json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _empty(*, path_exists: bool, tables: dict[str, bool] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "path_exists": path_exists,
        "tables": tables or {name: False for name in sorted(REQUIRED_TABLES)},
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "shadow_score_wired": False,
        "sample_ready": False,
        "shadow_score_candidate_ready": False,
        "blocking_reasons": ["dex_quality_schema_unavailable"],
        "thresholds": {
            "min_usable_cases": MIN_USABLE_CASES,
            "min_exact_p5m_coverage": MIN_EXACT_P5M_COVERAGE,
            "max_research_assets_per_case": MAX_RESEARCH_ASSETS_PER_CASE,
        },
        "cases": [],
    }


def evaluate_dex_launch_quality(
    path: Path | str = DB_PATH,
    *,
    min_usable_cases: int = MIN_USABLE_CASES,
    min_exact_p5m_coverage: float = MIN_EXACT_P5M_COVERAGE,
    max_research_assets_per_case: int = MAX_RESEARCH_ASSETS_PER_CASE,
) -> dict[str, Any]:
    """Evaluate whether DEX research samples are ready for shadow-score experimentation.

    This is a read-only quality gate. It never reads raw OHLCV rows and never wires
    any DEX feature into PAPER decisions or order paths.
    """

    db_path = Path(path)
    if not db_path.exists():
        return _empty(path_exists=False)

    min_cases = max(1, int(min_usable_cases))
    min_exact = min(1.0, max(0.0, float(min_exact_p5m_coverage)))
    max_assets = max(1, int(max_research_assets_per_case))

    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        existing = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        table_state = {name: name in existing for name in sorted(REQUIRED_TABLES)}
        if not all(table_state.values()):
            payload = _empty(path_exists=True, tables=table_state)
            payload["thresholds"] = {
                "min_usable_cases": min_cases,
                "min_exact_p5m_coverage": min_exact,
                "max_research_assets_per_case": max_assets,
            }
            return payload

        cases = {
            str(row["case_key"]): {
                "case_key": str(row["case_key"]),
                "coingecko_id": str(row["coingecko_id"] or ""),
                "stored_status": str(row["status"] or ""),
                "contract_count": int(row["contract_count"] or 0),
                "accepted_pool_count": int(row["accepted_pool_count"] or 0),
                "asset_keys": set(),
                "primary_asset_keys": set(),
                "feature_asset_keys": set(),
                "usable_feature_asset_keys": set(),
                "p5m_exact_asset_keys": set(),
                "launch_feature_asset_keys": set(),
            }
            for row in conn.execute(
                """SELECT case_key,coingecko_id,status,contract_count,accepted_pool_count
                   FROM dex_launch_case_status ORDER BY updated_at DESC"""
            ).fetchall()
        }

        asset_to_case: dict[str, str] = {}
        for row in conn.execute("SELECT asset_key,case_key FROM dex_launch_assets").fetchall():
            asset_key = str(row["asset_key"])
            case_key = str(row["case_key"])
            asset_to_case[asset_key] = case_key
            if case_key in cases:
                cases[case_key]["asset_keys"].add(asset_key)

        for row in conn.execute(
            "SELECT asset_key FROM dex_launch_pools WHERE selected_primary=1 AND gate_status='accepted'"
        ).fetchall():
            asset_key = str(row["asset_key"])
            case_key = asset_to_case.get(asset_key, "")
            if case_key in cases:
                cases[case_key]["primary_asset_keys"].add(asset_key)

        for row in conn.execute(
            "SELECT asset_key,feature_version,feature_json FROM dex_launch_features"
        ).fetchall():
            asset_key = str(row["asset_key"])
            case_key = asset_to_case.get(asset_key, "")
            if case_key not in cases:
                continue
            feature = _json(row["feature_json"])
            cases[case_key]["feature_asset_keys"].add(asset_key)
            domestic = (
                feature.get("domestic_listing_window")
                if isinstance(feature.get("domestic_listing_window"), dict)
                else {}
            )
            launch = (
                feature.get("pool_launch_window")
                if isinstance(feature.get("pool_launch_window"), dict)
                else {}
            )
            quality = feature.get("pool_quality") if isinstance(feature.get("pool_quality"), dict) else {}
            primary_ok = asset_key in cases[case_key]["primary_asset_keys"]
            if domestic.get("status") == "collected" and bool(quality.get("passed")) and primary_ok:
                cases[case_key]["usable_feature_asset_keys"].add(asset_key)
                if bool(domestic.get("p5m_exact_minute")):
                    cases[case_key]["p5m_exact_asset_keys"].add(asset_key)
            if launch.get("status") == "collected":
                cases[case_key]["launch_feature_asset_keys"].add(asset_key)

        rows: list[dict[str, Any]] = []
        derived_counts: Counter[str] = Counter()
        stored_counts: Counter[str] = Counter()
        usable_case_count = 0
        exact_case_count = 0
        launch_case_count = 0
        partial_case_count = 0
        usable_asset_count = 0

        for source in cases.values():
            contract_count = max(0, int(source["contract_count"]))
            asset_count = len(source["asset_keys"])
            expected_assets = min(max_assets, contract_count if contract_count > 0 else max(1, asset_count))
            feature_assets = len(source["feature_asset_keys"])
            usable_assets = len(source["usable_feature_asset_keys"])
            exact_assets = len(source["p5m_exact_asset_keys"])
            launch_assets = len(source["launch_feature_asset_keys"])

            if usable_assets <= 0:
                derived = "not_usable"
            elif usable_assets < expected_assets:
                derived = "complete_partial"
            else:
                derived = "complete"

            usable = usable_assets > 0
            exact = exact_assets > 0
            launch_usable = launch_assets > 0
            if usable:
                usable_case_count += 1
                usable_asset_count += usable_assets
            if exact:
                exact_case_count += 1
            if launch_usable:
                launch_case_count += 1
            if derived == "complete_partial":
                partial_case_count += 1
            derived_counts[derived] += 1
            stored_counts[str(source["stored_status"])] += 1

            rows.append(
                {
                    "case_key": source["case_key"],
                    "coingecko_id": source["coingecko_id"],
                    "stored_status": source["stored_status"],
                    "derived_completion": derived,
                    "contract_count": contract_count,
                    "expected_research_assets": expected_assets,
                    "asset_count": asset_count,
                    "primary_asset_count": len(source["primary_asset_keys"]),
                    "feature_asset_count": feature_assets,
                    "usable_feature_asset_count": usable_assets,
                    "p5m_exact_asset_count": exact_assets,
                    "launch_feature_asset_count": launch_assets,
                    "usable_for_shadow_analysis": usable,
                    "all_expected_assets_researched": bool(usable_assets >= expected_assets),
                }
            )

        exact_coverage = exact_case_count / usable_case_count if usable_case_count else 0.0
        required_exact_cases = int(math.ceil(min_cases * min_exact))
        blockers: list[str] = []
        if usable_case_count < min_cases:
            blockers.append(f"usable_cases_below_min:{usable_case_count}/{min_cases}")
        if exact_coverage < min_exact:
            blockers.append(f"exact_p5m_coverage_below_min:{exact_coverage:.4f}/{min_exact:.4f}")
        sample_ready = not blockers

        return {
            "ok": True,
            "path_exists": True,
            "tables": table_state,
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "shadow_score_wired": False,
            "sample_ready": sample_ready,
            "shadow_score_candidate_ready": sample_ready,
            "blocking_reasons": blockers,
            "thresholds": {
                "min_usable_cases": min_cases,
                "min_exact_p5m_coverage": min_exact,
                "required_exact_p5m_cases_at_min_sample": required_exact_cases,
                "max_research_assets_per_case": max_assets,
            },
            "case_count": len(rows),
            "stored_status_counts": dict(sorted(stored_counts.items())),
            "derived_completion_counts": dict(sorted(derived_counts.items())),
            "usable_case_count": usable_case_count,
            "usable_asset_count": usable_asset_count,
            "exact_p5m_case_count": exact_case_count,
            "exact_p5m_coverage": round(exact_coverage, 6),
            "launch_feature_case_count": launch_case_count,
            "complete_partial_case_count": partial_case_count,
            "cases": rows,
        }
    finally:
        conn.close()
