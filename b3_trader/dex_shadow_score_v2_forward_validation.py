from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .auto_demo_v2 import DB_PATH
from .dex_shadow_score_validation import _aggregate_assets, _chronological_halves, _finite, _window_stats
from .dex_shadow_score_v2_forward import audit_dex_shadow_score_v2_forward
from .dex_shadow_score_v2_preregistration import (
    CORE_WINDOWS,
    FORWARD_CUTOFF_TS,
    FORWARD_CUTOFF_UTC,
    FORWARD_VALIDATION_PROTOCOL,
    V2_SCORE_NAME,
    V2_SCORE_VERSION,
)
from .forward_sample_ledger import audit_forward_sample_ledger


BUILD71_VERSION = 1
BUILD71_NAME = "dex_shadow_score_v2_preregistered_forward_validation_v1"

ScoreAuditFn = Callable[[Path | str], dict[str, Any]]
LedgerAuditFn = Callable[..., dict[str, Any]]


def _safe_count(value: Any) -> int:
    number = _finite(value)
    return int(number) if number is not None and number >= 0.0 else 0


def _core_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Reuse Build63's frozen pure metrics, restricted to Build65 core windows."""

    return {
        "row_count": len(rows),
        "windows": {window: _window_stats(rows, window) for window in CORE_WINDOWS},
    }


def _ledger_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": ledger.get("status"),
        "event_count": _safe_count(ledger.get("event_count")),
        "unique_asset_count": _safe_count(ledger.get("unique_asset_count")),
        "label_coverage": ledger.get("label_coverage") or {},
        "requirements": ledger.get("requirements") or {},
        "remaining": ledger.get("remaining") or {},
        "confidence": ledger.get("confidence") or {},
        "readiness": ledger.get("readiness") or {},
    }


def _score_contract_ready(score: dict[str, Any]) -> bool:
    boundary = score.get("forward_boundary") if isinstance(score.get("forward_boundary"), dict) else {}
    rows = [row for row in score.get("case_scores") or [] if isinstance(row, dict)]
    cutoff = _finite(boundary.get("cutoff_unix"))
    return bool(
        score.get("ok")
        and score.get("status") in {"scored_forward_only", "forward_waiting_no_eligible_cases"}
        and score.get("score_version") == V2_SCORE_VERSION
        and score.get("score_name") == V2_SCORE_NAME
        and score.get("forward_only") is True
        and score.get("all_forward_eligible_cases_scored") is True
        and not score.get("historical_rows_scored_as_v2")
        and not score.get("historical_rows_eligible_for_v2_validation")
        and not score.get("score_wired")
        and not score.get("paper_ab_wired")
        and not score.get("can_place_orders")
        and cutoff == FORWARD_CUTOFF_TS
        and _finite(score.get("case_score_count")) == float(len(rows))
        and _finite(score.get("forward_eligible_case_count")) == float(len(rows))
    )


def _protocol_contract_ready() -> bool:
    minimum_event = _finite(FORWARD_VALIDATION_PROTOCOL.get("minimum_event_labels_per_core"))
    minimum_asset = _finite(FORWARD_VALIDATION_PROTOCOL.get("minimum_asset_labels_per_core"))
    minimum_positive = _finite(FORWARD_VALIDATION_PROTOCOL.get("minimum_positive_rank_windows"))
    minimum_rho = _finite(FORWARD_VALIDATION_PROTOCOL.get("minimum_spearman_rho"))
    strong_negative = _finite(FORWARD_VALIDATION_PROTOCOL.get("strong_negative_spearman_rho"))
    return bool(
        FORWARD_VALIDATION_PROTOCOL.get("core_windows") == list(CORE_WINDOWS)
        and FORWARD_VALIDATION_PROTOCOL.get("primary_level") == "asset_dedup"
        and minimum_event is not None
        and minimum_event > 0.0
        and minimum_asset is not None
        and minimum_asset > 0.0
        and minimum_positive is not None
        and 1.0 <= minimum_positive <= len(CORE_WINDOWS)
        and minimum_rho is not None
        and strong_negative is not None
        and strong_negative < minimum_rho
        and FORWARD_VALIDATION_PROTOCOL.get("require_positive_p24h_top_bottom_spread") is True
        and FORWARD_VALIDATION_PROTOCOL.get("require_late_half_positive_rank_window") is True
        and FORWARD_VALIDATION_PROTOCOL.get("require_no_strong_negative_core_rank_signal") is True
        and FORWARD_VALIDATION_PROTOCOL.get("trade_threshold_selection_before_forward_pass") is False
        and FORWARD_VALIDATION_PROTOCOL.get("paper_ab_before_forward_pass") is False
        and FORWARD_VALIDATION_PROTOCOL.get("live_promotion_before_forward_pass") is False
    )


def _sample_integrity_issues(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    seen_case_keys: set[str] = set()

    def add(case_key: str, reason: str) -> None:
        if len(issues) < 20:
            issues.append({"case_key": case_key, "reason": reason})

    for index, row in enumerate(rows):
        case_key = str(row.get("case_key") or "").strip()
        label = case_key or f"row:{index}"
        if not case_key:
            add(label, "missing_case_key")
        elif case_key in seen_case_keys:
            add(label, "duplicate_case_key")
        seen_case_keys.add(case_key)

        if row.get("score_version") != V2_SCORE_VERSION or row.get("score_name") != V2_SCORE_NAME:
            add(label, "score_identity_mismatch")
        if row.get("forward_eligible") is not True:
            add(label, "forward_eligibility_not_proven")

        domestic_open_at = _finite(row.get("domestic_open_at"))
        if domestic_open_at is None or domestic_open_at < FORWARD_CUTOFF_TS:
            add(label, "pre_cutoff_or_missing_domestic_open")

        score = _finite(row.get("shadow_score"))
        if score is None or not 0.0 <= score <= 100.0:
            add(label, "invalid_shadow_score")
        confidence = _finite(row.get("confidence"))
        if confidence is None or not 0.0 <= confidence <= 1.0:
            add(label, "invalid_confidence")
        if not str(row.get("coingecko_id") or "").strip():
            add(label, "identity_incomplete")

        outcomes = row.get("evaluation_only_outcomes")
        if not isinstance(outcomes, dict) or outcomes.get("excluded_from_score") is not True:
            add(label, "evaluation_only_boundary_missing")
        elif not isinstance(outcomes.get("post_listing_returns_pct"), dict):
            add(label, "evaluation_labels_missing")

    return issues


def _positive_rank_windows(metrics: dict[str, Any], minimum_rho: float) -> list[str]:
    windows = metrics.get("windows") if isinstance(metrics.get("windows"), dict) else {}
    return [
        window
        for window in CORE_WINDOWS
        if (_finite((windows.get(window) or {}).get("spearman")) or -999.0) >= minimum_rho
    ]


def _p24h_spread(metrics: dict[str, Any]) -> float | None:
    windows = metrics.get("windows") if isinstance(metrics.get("windows"), dict) else {}
    quartiles = (windows.get("p24h") or {}).get("quartiles")
    if not isinstance(quartiles, dict):
        return None
    return _finite(quartiles.get("top_minus_bottom_mean_return_pct"))


def _strong_negative_core_windows(
    event_metrics: dict[str, Any],
    asset_metrics: dict[str, Any],
    threshold: float,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for level, metrics in (("event", event_metrics), ("asset_dedup", asset_metrics)):
        windows = metrics.get("windows") if isinstance(metrics.get("windows"), dict) else {}
        for window in CORE_WINDOWS:
            rho = _finite((windows.get(window) or {}).get("spearman"))
            if rho is not None and rho <= threshold:
                result.append({"level": level, "window": window, "spearman": round(rho, 6)})
    return result


def audit_dex_shadow_score_v2_forward_validation(
    path: Path | str = DB_PATH,
    *,
    score_audit_fn: ScoreAuditFn = audit_dex_shadow_score_v2_forward,
    ledger_audit_fn: LedgerAuditFn = audit_forward_sample_ledger,
) -> dict[str, Any]:
    """Build71 validation of the frozen v2 hypothesis on forward-only cases.

    The Build70 minimum-sample gate is evaluated before any correlation, rank,
    quartile, spread, or chronological statistic is calculated. Build71 uses the
    exact Build65 protocol and never fits weights, selects a trade threshold,
    mutates research data, wires PAPER A/B, or changes an order path.
    """

    db_path = Path(path)
    score = score_audit_fn(db_path)
    ledger = ledger_audit_fn(db_path, score_audit_fn=lambda _: score)
    base = {
        "ok": False,
        "status": "build66_score_contract_blocked",
        "build71_version": BUILD71_VERSION,
        "build71_name": BUILD71_NAME,
        "score_version": V2_SCORE_VERSION,
        "score_name": V2_SCORE_NAME,
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_wired": False,
        "paper_ab_wired": False,
        "live_promotion_allowed": False,
        "read_only": True,
        "network_fetches": False,
        "database_mutation": False,
        "cloudflare_publishing": False,
        "strategy_signal_mutation": False,
        "position_sizing_mutation": False,
        "order_path_mutation": False,
        "score_formula_changed": False,
        "score_weights_changed": False,
        "training_or_fitting": False,
        "trade_threshold": None,
        "post_listing_outcomes_used_for_evaluation_only": True,
        "retrospective_rows_used": False,
        "validation_statistics_calculated": False,
        "statistics": None,
        "forward_only": True,
        "forward_boundary": {
            "cutoff_utc": FORWARD_CUTOFF_UTC,
            "cutoff_unix": FORWARD_CUTOFF_TS,
            "pre_cutoff_cases_counted": False,
            "pre_cutoff_cases_validation_excluded": True,
        },
        "isolation": {
            "build47_historical_cursor_read": False,
            "build47_historical_cursor_mutation": False,
        },
        "preregistered_protocol": FORWARD_VALIDATION_PROTOCOL,
        "sample_ledger": _ledger_summary(ledger),
    }

    if not _protocol_contract_ready():
        return {
            **base,
            "status": "build65_preregistered_protocol_blocked",
            "review": {
                "build72_parallel_paper_ab_allowed": False,
                "next_action": "repair_build65_preregistered_protocol_before_validation",
            },
        }

    if not _score_contract_ready(score):
        return {
            **base,
            "review": {
                "build72_parallel_paper_ab_allowed": False,
                "next_action": "repair_build66_forward_score_contract_before_validation",
            },
        }

    ledger_readiness = ledger.get("readiness") if isinstance(ledger.get("readiness"), dict) else {}
    sample_size_ready = bool(ledger_readiness.get("sample_size_ready"))
    ledger_contract_ready = bool(
        ledger.get("ok")
        and ledger.get("score_version") == V2_SCORE_VERSION
        and ledger.get("score_name") == V2_SCORE_NAME
        and ledger.get("validation_statistics_calculated") is False
        and ledger.get("status")
        in {"accumulating_forward_sample", "forward_sample_ready_for_validation"}
        and (ledger.get("status") == "forward_sample_ready_for_validation") == sample_size_ready
        and bool((ledger.get("review") or {}).get("build71_forward_validation_allowed")) == sample_size_ready
    )
    if not ledger_contract_ready:
        return {
            **base,
            "status": "build70_ledger_contract_blocked",
            "score_audit_ready": True,
            "review": {
                "build72_parallel_paper_ab_allowed": False,
                "next_action": "repair_build70_readiness_contract_before_validation",
            },
        }

    if not sample_size_ready:
        return {
            **base,
            "ok": True,
            "status": "waiting_for_forward_sample",
            "score_audit_ready": True,
            "build70_readiness_gate_passed": False,
            "validation_gate": {
                "forward_validation_passed": False,
                "paper_ab_candidate_advisory": False,
                "build72_parallel_paper_ab_allowed": False,
                "reason": "build70_sample_size_not_ready",
            },
            "review": {
                "build72_parallel_paper_ab_allowed": False,
                "paper_ab_wired": False,
                "live_promotion_allowed": False,
                "next_action": "continue_build69_forward_pipeline_until_build70_sample_ready",
            },
        }

    rows = [row for row in score.get("case_scores") or [] if isinstance(row, dict)]
    integrity_issues = _sample_integrity_issues(rows)
    if integrity_issues:
        return {
            **base,
            "status": "forward_sample_integrity_blocked",
            "score_audit_ready": True,
            "build70_readiness_gate_passed": True,
            "sample_integrity": {
                "passed": False,
                "issue_count_preview": len(integrity_issues),
                "issues_preview": integrity_issues,
            },
            "review": {
                "build72_parallel_paper_ab_allowed": False,
                "next_action": "repair_forward_sample_integrity_without_using_validation_statistics",
            },
        }

    asset_rows = _aggregate_assets(rows)
    expected_event_count = _safe_count(ledger.get("event_count"))
    expected_asset_count = _safe_count(ledger.get("unique_asset_count"))
    if len(rows) != expected_event_count or len(asset_rows) != expected_asset_count:
        return {
            **base,
            "status": "forward_sample_snapshot_mismatch_blocked",
            "score_audit_ready": True,
            "build70_readiness_gate_passed": True,
            "sample_integrity": {
                "passed": False,
                "score_event_count": len(rows),
                "ledger_event_count": expected_event_count,
                "score_asset_count": len(asset_rows),
                "ledger_asset_count": expected_asset_count,
            },
            "review": {
                "build72_parallel_paper_ab_allowed": False,
                "next_action": "rerun_build71_on_one_consistent_forward_score_snapshot",
            },
        }

    event_metrics = _core_metrics(rows)
    asset_metrics = _core_metrics(asset_rows)
    event_early, event_late = _chronological_halves(rows)
    asset_early, asset_late = _chronological_halves(asset_rows)
    event_chronological = {"early": _core_metrics(event_early), "late": _core_metrics(event_late)}
    asset_chronological = {"early": _core_metrics(asset_early), "late": _core_metrics(asset_late)}

    minimum_event = int(FORWARD_VALIDATION_PROTOCOL["minimum_event_labels_per_core"])
    minimum_asset = int(FORWARD_VALIDATION_PROTOCOL["minimum_asset_labels_per_core"])
    minimum_positive = int(FORWARD_VALIDATION_PROTOCOL["minimum_positive_rank_windows"])
    minimum_rho = float(FORWARD_VALIDATION_PROTOCOL["minimum_spearman_rho"])
    strong_negative_rho = float(FORWARD_VALIDATION_PROTOCOL["strong_negative_spearman_rho"])

    event_windows = event_metrics["windows"]
    asset_windows = asset_metrics["windows"]
    event_labels_ready = all(
        int((event_windows.get(window) or {}).get("labeled_count") or 0) >= minimum_event
        for window in CORE_WINDOWS
    )
    asset_labels_ready = all(
        int((asset_windows.get(window) or {}).get("labeled_count") or 0) >= minimum_asset
        for window in CORE_WINDOWS
    )
    primary_positive_windows = _positive_rank_windows(asset_metrics, minimum_rho)
    event_positive_windows = _positive_rank_windows(event_metrics, minimum_rho)
    late_primary_positive_windows = _positive_rank_windows(asset_chronological["late"], minimum_rho)
    event_p24h_spread = _p24h_spread(event_metrics)
    primary_p24h_spread = _p24h_spread(asset_metrics)
    strong_negative = _strong_negative_core_windows(event_metrics, asset_metrics, strong_negative_rho)

    require_p24h_spread = bool(FORWARD_VALIDATION_PROTOCOL["require_positive_p24h_top_bottom_spread"])
    require_late_half = bool(FORWARD_VALIDATION_PROTOCOL["require_late_half_positive_rank_window"])
    require_no_strong_negative = bool(
        FORWARD_VALIDATION_PROTOCOL["require_no_strong_negative_core_rank_signal"]
    )
    criteria = {
        "event_core_label_coverage": event_labels_ready,
        "asset_core_label_coverage": asset_labels_ready,
        "primary_asset_dedup_positive_rank_signal": len(primary_positive_windows) >= minimum_positive,
        "primary_asset_dedup_positive_p24h_top_bottom_spread": (
            not require_p24h_spread
            or (primary_p24h_spread is not None and primary_p24h_spread > 0.0)
        ),
        "primary_asset_dedup_late_half_positive_rank_signal": (
            not require_late_half or bool(late_primary_positive_windows)
        ),
        "no_strong_negative_event_or_asset_core_rank_signal": (
            not require_no_strong_negative or not strong_negative
        ),
    }
    forward_validation_passed = all(criteria.values())

    validation_protocol = {
        "frozen_from_build65": True,
        "primary_level": FORWARD_VALIDATION_PROTOCOL["primary_level"],
        "thresholds": {
            "core_windows": list(CORE_WINDOWS),
            "minimum_event_labels_per_core": minimum_event,
            "minimum_asset_labels_per_core": minimum_asset,
            "minimum_positive_rank_windows": minimum_positive,
            "minimum_spearman_rho": minimum_rho,
            "strong_negative_spearman_rho": strong_negative_rho,
            "require_positive_p24h_top_bottom_spread": require_p24h_spread,
            "require_late_half_positive_rank_window": require_late_half,
            "require_no_strong_negative_core_rank_signal": require_no_strong_negative,
        },
        "observed": {
            "event_positive_rank_windows": event_positive_windows,
            "primary_asset_dedup_positive_rank_windows": primary_positive_windows,
            "primary_asset_dedup_late_half_positive_rank_windows": late_primary_positive_windows,
            "event_p24h_top_minus_bottom_mean_return_pct": (
                None if event_p24h_spread is None else round(event_p24h_spread, 6)
            ),
            "primary_asset_dedup_p24h_top_minus_bottom_mean_return_pct": (
                None if primary_p24h_spread is None else round(primary_p24h_spread, 6)
            ),
            "strong_negative_core_windows": strong_negative,
        },
        "criteria": criteria,
        "all_criteria_pass": forward_validation_passed,
    }

    return {
        **base,
        "ok": True,
        "status": "forward_validation_passed" if forward_validation_passed else "forward_validation_failed",
        "score_audit_ready": True,
        "build70_readiness_gate_passed": True,
        "validation_statistics_calculated": True,
        "statistics": {
            "event_level": event_metrics,
            "asset_level_dedup": asset_metrics,
            "chronological_halves": {
                "event_level": event_chronological,
                "asset_level_dedup": asset_chronological,
            },
        },
        "sample_integrity": {
            "passed": True,
            "event_count": len(rows),
            "unique_asset_count": len(asset_rows),
            "identity_complete": True,
            "pre_cutoff_case_count": 0,
        },
        "validation_protocol": validation_protocol,
        "validation_gate": {
            "forward_validation_passed": forward_validation_passed,
            "paper_ab_candidate_advisory": forward_validation_passed,
            "build72_parallel_paper_ab_allowed": forward_validation_passed,
            "paper_ab_wired": False,
            "live_promotion_allowed": False,
        },
        "review": {
            "build72_parallel_paper_ab_allowed": forward_validation_passed,
            "paper_ab_wired": False,
            "orders_changed": False,
            "existing_strategy_signal_changed": False,
            "position_sizing_changed": False,
            "live_promotion_allowed": False,
            "next_action": (
                "implement_build72_parallel_paper_ab_without_order_wiring"
                if forward_validation_passed
                else "reject_v2_or_preregister_a_new_hypothesis_with_a_new_forward_cutoff"
            ),
        },
    }
