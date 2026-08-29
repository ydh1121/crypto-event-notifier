from __future__ import annotations

import json
import math
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .dex_launch_quality import evaluate_dex_launch_quality
from .dex_launch_research_cycle import DEX_OHLCV_HISTORY_SECONDS
from .dex_shadow_readiness_audit import (
    MAX_MONTH_SHARE,
    MIN_LAUNCH_FEATURE_COVERAGE,
    audit_dex_shadow_readiness,
)


def _json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _month_bucket(ts: Any) -> str:
    try:
        value = float(ts or 0.0)
    except (TypeError, ValueError):
        return "unknown"
    if value <= 0:
        return "unknown"
    return time.strftime("%Y-%m", time.gmtime(value))


def _launch_case_class(rows: list[dict[str, Any]], now: float) -> str:
    if any(row.get("launch_status") == "collected" for row in rows):
        return "collected"
    recent_missing = False
    expired = False
    created_missing = False
    feature_missing = False
    for row in rows:
        created = float(row.get("pool_created_at") or 0.0)
        status = str(row.get("launch_status") or "")
        if created <= 0 or status == "pool_created_at_missing":
            created_missing = True
            continue
        if now - created > DEX_OHLCV_HISTORY_SECONDS:
            expired = True
            continue
        if status in {"launch_ohlcv_unavailable", "not_available", ""}:
            recent_missing = True
        if row.get("feature_missing"):
            feature_missing = True
    if recent_missing:
        return "recoverable_recent"
    if expired:
        return "history_window_expired"
    if created_missing:
        return "pool_created_at_missing"
    if feature_missing:
        return "feature_missing"
    return "other_unavailable"


def plan_dex_shadow_remediation(
    path: Path | str = DB_PATH,
    *,
    now: float | None = None,
) -> dict[str, Any]:
    """Read-only plan for fixing Build53 blockers before any shadow-score wiring."""

    db_path = Path(path)
    current_now = float(now if now is not None else time.time())
    readiness = audit_dex_shadow_readiness(db_path)
    base = {
        "ok": bool(readiness.get("ok")),
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_wired": False,
        "advisory_only": True,
        "changes_build45_thresholds": False,
        "changes_build51_policy": False,
        "changes_build53_thresholds": False,
    }
    if not readiness.get("ok") or not db_path.exists():
        return {
            **base,
            "readiness": readiness,
            "recommended_next_action": "readiness_unavailable",
            "review": {"wire_shadow_score_now": False},
        }

    quality = evaluate_dex_launch_quality(db_path)
    usable_keys = {
        str(row.get("case_key"))
        for row in quality.get("cases") or []
        if isinstance(row, dict) and row.get("usable_for_shadow_analysis") and row.get("case_key")
    }
    metrics = readiness.get("metrics") or {}
    distributions = readiness.get("distributions") or {}
    month_counts = Counter({str(k): int(v) for k, v in (distributions.get("listing_month_counts") or {}).items()})
    usable_count = int(metrics.get("usable_event_cases") or 0)
    launch_count = int(round(float(metrics.get("launch_feature_coverage") or 0.0) * usable_count))

    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        required = {"listing_history_cases", "dex_launch_assets", "dex_launch_pools", "dex_launch_features"}
        if not required.issubset(tables):
            return {
                **base,
                "readiness": readiness,
                "recommended_next_action": "required_tables_missing",
                "missing_tables": sorted(required - tables),
                "review": {"wire_shadow_score_now": False},
            }

        primary_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if usable_keys:
            placeholders = ",".join("?" for _ in usable_keys)
            rows = conn.execute(
                f"""
                SELECT a.case_key,p.pool_created_at,f.feature_json
                FROM dex_launch_assets a
                JOIN dex_launch_pools p ON p.asset_key=a.asset_key
                LEFT JOIN dex_launch_features f
                  ON f.asset_key=p.asset_key AND f.pool_address=p.pool_address
                WHERE p.selected_primary=1
                  AND a.case_key IN ({placeholders})
                """,
                tuple(sorted(usable_keys)),
            ).fetchall()
            for row in rows:
                feature = _json(row["feature_json"])
                launch = feature.get("pool_launch_window") if isinstance(feature.get("pool_launch_window"), dict) else {}
                primary_by_case[str(row["case_key"])].append(
                    {
                        "pool_created_at": float(row["pool_created_at"] or 0.0),
                        "launch_status": str(launch.get("status") or ""),
                        "feature_missing": not bool(feature),
                    }
                )

        launch_classes: Counter[str] = Counter()
        for case_key in sorted(usable_keys):
            launch_classes[_launch_case_class(primary_by_case.get(case_key, []), current_now)] += 1

        backlog_months: Counter[str] = Counter()
        backlog_rows = conn.execute(
            """
            SELECT c.domestic_open_at
            FROM listing_history_cases c
            LEFT JOIN dex_launch_case_status d ON d.case_key=c.case_key
            WHERE c.identity_verified=1
              AND c.status NOT IN ('rejected_identity','rejected_notice')
              AND d.case_key IS NULL
            """
        ).fetchall()
        for row in backlog_rows:
            backlog_months[_month_bucket(row["domestic_open_at"])] += 1
    finally:
        conn.close()

    dominant_month, dominant_count = (month_counts.most_common(1)[0] if month_counts else ("unknown", 0))
    temporal_target_total = usable_count
    if dominant_count > 0 and MAX_MONTH_SHARE > 0:
        temporal_target_total = max(usable_count, int(math.ceil(dominant_count / MAX_MONTH_SHARE)))
    additional_non_dominant_needed = max(0, temporal_target_total - usable_count)
    per_month_cap_at_target = int(math.floor(MAX_MONTH_SHARE * temporal_target_total + 1e-9)) if temporal_target_total else 0
    existing_month_additional_capacity = {
        month: (0 if month == dominant_month else max(0, per_month_cap_at_target - count))
        for month, count in sorted(month_counts.items())
    }
    known_non_dominant_backlog = sum(count for month, count in backlog_months.items() if month != dominant_month)

    current_launch_required = int(math.ceil(MIN_LAUNCH_FEATURE_COVERAGE * usable_count)) if usable_count else 0
    launch_required_at_temporal_target = int(math.ceil(MIN_LAUNCH_FEATURE_COVERAGE * temporal_target_total)) if temporal_target_total else 0
    additional_launch_needed_current = max(0, current_launch_required - launch_count)
    additional_launch_needed_target = max(0, launch_required_at_temporal_target - launch_count)
    recoverable_existing = int(launch_classes.get("recoverable_recent") or 0)
    remaining_launch_needed_after_recovery = max(0, additional_launch_needed_target - recoverable_existing)

    temporal_blocked = any(str(reason).startswith("temporal_concentration_above_max:") for reason in readiness.get("blocking_reasons") or [])
    launch_blocked = any(str(reason).startswith("launch_feature_coverage_below_min:") for reason in readiness.get("blocking_reasons") or [])
    historical_expansion_likely_required = bool(
        temporal_blocked and known_non_dominant_backlog < additional_non_dominant_needed
    )

    if readiness.get("shadow_readiness_advisory"):
        action = "manual_shadow_implementation_review"
    elif temporal_blocked and launch_blocked:
        action = "historical_expansion_plus_launch_recovery"
    elif temporal_blocked:
        action = "historical_expansion_for_temporal_balance"
    elif launch_blocked and recoverable_existing >= additional_launch_needed_current:
        action = "recover_existing_launch_features"
    elif launch_blocked:
        action = "expand_launch_feature_sample"
    else:
        action = "review_other_build53_blockers"

    return {
        **base,
        "readiness": {
            "shadow_readiness_advisory": bool(readiness.get("shadow_readiness_advisory")),
            "blocking_reasons": list(readiness.get("blocking_reasons") or []),
        },
        "temporal_remediation": {
            "current_usable_cases": usable_count,
            "listing_month_counts": dict(sorted(month_counts.items())),
            "dominant_month": dominant_month,
            "dominant_month_cases": dominant_count,
            "max_month_share": MAX_MONTH_SHARE,
            "minimum_target_usable_cases": temporal_target_total,
            "additional_non_dominant_usable_cases_needed": additional_non_dominant_needed,
            "per_month_case_cap_at_target": per_month_cap_at_target,
            "existing_month_additional_capacity_at_target": existing_month_additional_capacity,
            "verified_without_dex_status_by_month": dict(sorted(backlog_months.items())),
            "known_non_dominant_backlog_cases": known_non_dominant_backlog,
            "historical_expansion_likely_required": historical_expansion_likely_required,
        },
        "launch_remediation": {
            "current_launch_feature_cases": launch_count,
            "current_required_launch_cases": current_launch_required,
            "additional_launch_cases_needed_current_sample": additional_launch_needed_current,
            "target_total_after_temporal_balance": temporal_target_total,
            "required_launch_cases_at_temporal_target": launch_required_at_temporal_target,
            "additional_launch_cases_needed_at_temporal_target": additional_launch_needed_target,
            "missing_launch_case_classification": dict(sorted(launch_classes.items())),
            "recoverable_existing_cases": recoverable_existing,
            "remaining_launch_cases_needed_after_full_existing_recovery": remaining_launch_needed_after_recovery,
            "history_window_seconds": DEX_OHLCV_HISTORY_SECONDS,
        },
        "recommended_next_action": action,
        "review": {
            "wire_shadow_score_now": False,
            "reason": "build54_is_read_only_remediation_planning_only",
        },
    }
