from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .dex_sample_audit import audit_dex_sample


MIN_UNIQUE_ASSET_RATIO = 0.75
MAX_DUPLICATE_EVENT_SHARE = 0.25
MAX_EXCHANGE_SHARE = 0.70
MIN_FULL_COMPLETE_RATIO = 0.50
MAX_COMPLETE_PARTIAL_RATIO = 0.50
MIN_EXACT_P5M_COVERAGE = 0.80
MIN_LAUNCH_FEATURE_COVERAGE = 0.30
MAX_PRIMARY_NETWORK_SHARE = 0.70
MAX_PRIMARY_DEX_SHARE = 0.60
MAX_MONTH_SHARE = 0.40
MAX_SOURCE_WAITING_SHARE_OF_NOT_USABLE = 0.50


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def _month_bucket(ts: Any) -> str:
    try:
        value = float(ts or 0.0)
    except (TypeError, ValueError):
        return "unknown"
    if value <= 0:
        return "unknown"
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m")
    except (OverflowError, OSError, ValueError):
        return "unknown"


def audit_dex_shadow_readiness(path: Path | str = DB_PATH) -> dict[str, Any]:
    """Read-only advisory gate before wiring any DEX shadow score experiment.

    Build53 does not alter Build45 thresholds, supervisors, score functions,
    PAPER decisions, or order paths. It only inspects the local research sample.
    """

    db_path = Path(path)
    sample = audit_dex_sample(db_path)
    base = {
        "ok": bool(sample.get("ok")),
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_wired": False,
        "advisory_only": True,
        "changes_build45_thresholds": False,
        "changes_build51_policy": False,
    }
    if not sample.get("ok") or not db_path.exists():
        return {**base, "sample_audit": sample, "shadow_readiness_advisory": False, "blocking_reasons": ["sample_audit_unavailable"]}

    event_cases = sample.get("event_cases") or {}
    coverage = sample.get("coverage") or {}
    exchange = sample.get("exchange_distribution") or {}
    usable_count = int(event_cases.get("usable") or 0)
    not_usable_count = int(event_cases.get("not_usable") or 0)

    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        required = {"listing_history_cases", "dex_launch_assets", "dex_launch_pools"}
        if not required.issubset(tables):
            missing = sorted(required - tables)
            return {
                **base,
                "sample_audit": sample,
                "shadow_readiness_advisory": False,
                "blocking_reasons": [f"required_tables_missing:{','.join(missing)}"],
            }

        usable_case_keys: set[str] = set()
        quality_cases = sample.get("sample_ready_build45")
        # Build50 intentionally exposes aggregate composition only, so rebuild the
        # usable case set from Build45 quality rows through the same read-only API.
        from .dex_launch_quality import evaluate_dex_launch_quality

        quality = evaluate_dex_launch_quality(db_path)
        for row in quality.get("cases") or []:
            if isinstance(row, dict) and row.get("usable_for_shadow_analysis") and row.get("case_key"):
                usable_case_keys.add(str(row["case_key"]))

        month_counts: Counter[str] = Counter()
        if usable_case_keys:
            placeholders = ",".join("?" for _ in usable_case_keys)
            rows = conn.execute(
                f"SELECT case_key,domestic_open_at FROM listing_history_cases WHERE case_key IN ({placeholders})",
                tuple(sorted(usable_case_keys)),
            ).fetchall()
            for row in rows:
                month_counts[_month_bucket(row["domestic_open_at"])] += 1

        network_case_groups: dict[str, set[str]] = defaultdict(set)
        dex_case_groups: dict[str, set[str]] = defaultdict(set)
        primary_asset_rows = 0
        if usable_case_keys:
            placeholders = ",".join("?" for _ in usable_case_keys)
            rows = conn.execute(
                f"""
                SELECT a.case_key,a.network_id,p.dex_id
                FROM dex_launch_assets a
                JOIN dex_launch_pools p ON p.asset_key=a.asset_key
                WHERE p.selected_primary=1
                  AND a.case_key IN ({placeholders})
                """,
                tuple(sorted(usable_case_keys)),
            ).fetchall()
            for row in rows:
                case_key = str(row["case_key"] or "")
                network_id = str(row["network_id"] or "unknown")
                dex_id = str(row["dex_id"] or "unknown")
                if case_key:
                    network_case_groups[network_id].add(case_key)
                    dex_case_groups[dex_id].add(case_key)
                    primary_asset_rows += 1

        network_counts = Counter({key: len(value) for key, value in network_case_groups.items()})
        dex_counts = Counter({key: len(value) for key, value in dex_case_groups.items()})
        max_network_count = max(network_counts.values(), default=0)
        max_dex_count = max(dex_counts.values(), default=0)
        max_month_count = max(month_counts.values(), default=0)

        not_usable_statuses = sample.get("not_usable_status_distribution") or {}
        source_waiting_count = int(not_usable_statuses.get("source_waiting") or 0)

        metrics = {
            "build45_sample_ready": bool(sample.get("sample_ready_build45")),
            "usable_event_cases": usable_count,
            "unique_assets": int(event_cases.get("unique_assets") or 0),
            "unique_asset_ratio": float(event_cases.get("unique_asset_ratio") or 0.0),
            "duplicate_event_share": _ratio(int(event_cases.get("duplicate_event_cases") or 0), usable_count),
            "max_exchange_share": float(exchange.get("max_exchange_share") or 0.0),
            "fully_complete_ratio": float(coverage.get("fully_complete_ratio") or 0.0),
            "complete_partial_ratio": float(coverage.get("complete_partial_ratio") or 0.0),
            "exact_p5m_coverage": float(coverage.get("exact_p5m_coverage") or 0.0),
            "launch_feature_coverage": float(coverage.get("launch_feature_coverage") or 0.0),
            "max_primary_network_share": _ratio(max_network_count, usable_count),
            "max_primary_dex_share": _ratio(max_dex_count, usable_count),
            "max_month_share": _ratio(max_month_count, usable_count),
            "source_waiting_share_of_not_usable": _ratio(source_waiting_count, not_usable_count),
        }

        thresholds = {
            "min_unique_asset_ratio": MIN_UNIQUE_ASSET_RATIO,
            "max_duplicate_event_share": MAX_DUPLICATE_EVENT_SHARE,
            "max_exchange_share": MAX_EXCHANGE_SHARE,
            "min_fully_complete_ratio": MIN_FULL_COMPLETE_RATIO,
            "max_complete_partial_ratio": MAX_COMPLETE_PARTIAL_RATIO,
            "min_exact_p5m_coverage": MIN_EXACT_P5M_COVERAGE,
            "min_launch_feature_coverage": MIN_LAUNCH_FEATURE_COVERAGE,
            "max_primary_network_share": MAX_PRIMARY_NETWORK_SHARE,
            "max_primary_dex_share": MAX_PRIMARY_DEX_SHARE,
            "max_month_share": MAX_MONTH_SHARE,
            "max_source_waiting_share_of_not_usable": MAX_SOURCE_WAITING_SHARE_OF_NOT_USABLE,
        }

        blockers: list[str] = []
        if not metrics["build45_sample_ready"]:
            blockers.append("build45_sample_not_ready")
        if metrics["unique_asset_ratio"] < MIN_UNIQUE_ASSET_RATIO:
            blockers.append(f"unique_asset_ratio_below_min:{metrics['unique_asset_ratio']:.6f}/{MIN_UNIQUE_ASSET_RATIO:.2f}")
        if metrics["duplicate_event_share"] > MAX_DUPLICATE_EVENT_SHARE:
            blockers.append(f"duplicate_event_share_above_max:{metrics['duplicate_event_share']:.6f}/{MAX_DUPLICATE_EVENT_SHARE:.2f}")
        if metrics["max_exchange_share"] > MAX_EXCHANGE_SHARE:
            blockers.append(f"exchange_concentration_above_max:{metrics['max_exchange_share']:.6f}/{MAX_EXCHANGE_SHARE:.2f}")
        if metrics["fully_complete_ratio"] < MIN_FULL_COMPLETE_RATIO:
            blockers.append(f"fully_complete_ratio_below_min:{metrics['fully_complete_ratio']:.6f}/{MIN_FULL_COMPLETE_RATIO:.2f}")
        if metrics["complete_partial_ratio"] > MAX_COMPLETE_PARTIAL_RATIO:
            blockers.append(f"complete_partial_ratio_above_max:{metrics['complete_partial_ratio']:.6f}/{MAX_COMPLETE_PARTIAL_RATIO:.2f}")
        if metrics["exact_p5m_coverage"] < MIN_EXACT_P5M_COVERAGE:
            blockers.append(f"exact_p5m_coverage_below_min:{metrics['exact_p5m_coverage']:.6f}/{MIN_EXACT_P5M_COVERAGE:.2f}")
        if metrics["launch_feature_coverage"] < MIN_LAUNCH_FEATURE_COVERAGE:
            blockers.append(f"launch_feature_coverage_below_min:{metrics['launch_feature_coverage']:.6f}/{MIN_LAUNCH_FEATURE_COVERAGE:.2f}")
        if metrics["max_primary_network_share"] > MAX_PRIMARY_NETWORK_SHARE:
            blockers.append(f"network_concentration_above_max:{metrics['max_primary_network_share']:.6f}/{MAX_PRIMARY_NETWORK_SHARE:.2f}")
        if metrics["max_primary_dex_share"] > MAX_PRIMARY_DEX_SHARE:
            blockers.append(f"dex_concentration_above_max:{metrics['max_primary_dex_share']:.6f}/{MAX_PRIMARY_DEX_SHARE:.2f}")
        if metrics["max_month_share"] > MAX_MONTH_SHARE:
            blockers.append(f"temporal_concentration_above_max:{metrics['max_month_share']:.6f}/{MAX_MONTH_SHARE:.2f}")
        if metrics["source_waiting_share_of_not_usable"] > MAX_SOURCE_WAITING_SHARE_OF_NOT_USABLE:
            blockers.append(
                f"source_waiting_share_above_max:{metrics['source_waiting_share_of_not_usable']:.6f}/{MAX_SOURCE_WAITING_SHARE_OF_NOT_USABLE:.2f}"
            )

        return {
            **base,
            "shadow_readiness_advisory": not blockers,
            "blocking_reasons": blockers,
            "metrics": metrics,
            "thresholds": thresholds,
            "distributions": {
                "primary_network_case_counts": dict(sorted(network_counts.items())),
                "primary_dex_case_counts": dict(sorted(dex_counts.items())),
                "listing_month_counts": dict(sorted(month_counts.items())),
                "primary_asset_rows": primary_asset_rows,
            },
            "sample_audit": {
                "sample_ready_build45": bool(sample.get("sample_ready_build45")),
                "event_cases": event_cases,
                "coverage": coverage,
                "exchange_distribution": exchange,
                "not_usable_status_distribution": not_usable_statuses,
            },
            "review": {
                "wire_shadow_score_now": False,
                "reason": "build53_is_advisory_only; explicit implementation review is required before any shadow-score wiring",
            },
        }
    finally:
        conn.close()
