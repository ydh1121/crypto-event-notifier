from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from .auto_demo_v2 import DB_PATH
from .dex_shadow_score_v2_forward import audit_dex_shadow_score_v2_forward
from .dex_shadow_score_v2_preregistration import (
    CORE_WINDOWS,
    FORWARD_CUTOFF_TS,
    FORWARD_CUTOFF_UTC,
    FORWARD_VALIDATION_PROTOCOL,
)


BUILD70_VERSION = 1
BUILD70_NAME = "dex_forward_sample_ledger_v1"

ScoreAuditFn = Callable[[Path | str], dict[str, Any]]


def _asset_key(row: dict[str, Any]) -> str:
    coingecko_id = str(row.get("coingecko_id") or "").strip()
    if coingecko_id:
        return f"coingecko:{coingecko_id}"
    return f"case:{str(row.get('case_key') or '').strip()}"


def audit_forward_sample_ledger(
    path: Path | str = DB_PATH,
    *,
    score_audit_fn: ScoreAuditFn = audit_dex_shadow_score_v2_forward,
) -> dict[str, Any]:
    """Read-only Build70 ledger for preregistered v2 forward validation.

    Build70 never computes correlation, selects thresholds, fits weights, mutates
    research state, or changes trading. It only counts forward-scored rows and
    evaluation-label coverage against Build65's frozen minimum sample sizes.
    """

    score = score_audit_fn(Path(path))
    base = {
        "ok": False,
        "status": "score_audit_blocked",
        "build70_version": BUILD70_VERSION,
        "build70_name": BUILD70_NAME,
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_wired": False,
        "paper_ab_wired": False,
        "live_promotion_allowed": False,
        "read_only": True,
        "network_fetches": False,
        "database_mutation": False,
        "training_or_fitting": False,
        "trade_threshold": None,
        "validation_statistics_calculated": False,
        "forward_only": True,
        "forward_boundary": {
            "cutoff_utc": FORWARD_CUTOFF_UTC,
            "cutoff_unix": FORWARD_CUTOFF_TS,
            "pre_cutoff_cases_counted": False,
        },
    }
    if not score.get("ok"):
        return {
            **base,
            "review": {
                "build71_forward_validation_allowed": False,
                "next_action": "repair_build66_forward_score_audit_before_ledger",
            },
        }
    if score.get("historical_rows_scored_as_v2"):
        return {
            **base,
            "status": "historical_contamination_blocked",
            "review": {
                "build71_forward_validation_allowed": False,
                "next_action": "repair_historical_contamination_before_forward_ledger",
            },
        }

    rows = [row for row in score.get("case_scores") or [] if isinstance(row, dict)]
    event_count = len(rows)
    asset_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        asset_rows[_asset_key(row)].append(row)
    asset_count = len(asset_rows)

    event_labels: dict[str, int] = {window: 0 for window in CORE_WINDOWS}
    asset_labels: dict[str, int] = {window: 0 for window in CORE_WINDOWS}
    for window in CORE_WINDOWS:
        for row in rows:
            outcomes = (
                row.get("evaluation_only_outcomes", {}).get("post_listing_returns_pct", {})
                if isinstance(row.get("evaluation_only_outcomes"), dict)
                else {}
            )
            if isinstance(outcomes, dict) and outcomes.get(window) is not None:
                event_labels[window] += 1
        for grouped in asset_rows.values():
            if any(
                isinstance(row.get("evaluation_only_outcomes"), dict)
                and isinstance(row["evaluation_only_outcomes"].get("post_listing_returns_pct"), dict)
                and row["evaluation_only_outcomes"]["post_listing_returns_pct"].get(window) is not None
                for row in grouped
            ):
                asset_labels[window] += 1

    min_event = int(FORWARD_VALIDATION_PROTOCOL["minimum_event_labels_per_core"])
    min_asset = int(FORWARD_VALIDATION_PROTOCOL["minimum_asset_labels_per_core"])
    event_remaining = {window: max(0, min_event - event_labels[window]) for window in CORE_WINDOWS}
    asset_remaining = {window: max(0, min_asset - asset_labels[window]) for window in CORE_WINDOWS}
    event_core_ready = all(value >= min_event for value in event_labels.values())
    asset_core_ready = all(value >= min_asset for value in asset_labels.values())
    sample_size_ready = event_core_ready and asset_core_ready

    confidence_values = [float(row.get("confidence") or 0.0) for row in rows]
    full_confidence = sum(1 for value in confidence_values if value >= 1.0)
    partial_confidence = event_count - full_confidence

    return {
        **base,
        "ok": True,
        "status": "forward_sample_ready_for_validation" if sample_size_ready else "accumulating_forward_sample",
        "score_version": score.get("score_version"),
        "score_name": score.get("score_name"),
        "event_count": event_count,
        "unique_asset_count": asset_count,
        "label_coverage": {
            "event": event_labels,
            "asset_dedup": asset_labels,
        },
        "requirements": {
            "minimum_event_labels_per_core": min_event,
            "minimum_asset_labels_per_core": min_asset,
            "core_windows": list(CORE_WINDOWS),
        },
        "remaining": {
            "event_labels_per_core": event_remaining,
            "asset_labels_per_core": asset_remaining,
        },
        "confidence": {
            "full_confidence_cases": full_confidence,
            "partial_confidence_cases": partial_confidence,
        },
        "readiness": {
            "event_core_label_coverage_ready": event_core_ready,
            "asset_core_label_coverage_ready": asset_core_ready,
            "sample_size_ready": sample_size_ready,
            "statistical_validation_not_run_early": True,
        },
        "review": {
            "build71_forward_validation_allowed": sample_size_ready,
            "paper_ab_wired": False,
            "live_promotion_allowed": False,
            "next_action": (
                "run_build71_preregistered_forward_validation"
                if sample_size_ready
                else "continue_build69_forward_pipeline_until_sample_minimums"
            ),
        },
    }
