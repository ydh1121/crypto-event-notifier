from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from .auto_demo_v2 import DB_PATH
from .dex_shadow_score import OUTCOME_WINDOWS, audit_dex_shadow_scores


VALIDATION_VERSION = 1
VALIDATION_NAME = "dex_shadow_score_validation_v1"
CORE_WINDOWS = ("p1h", "p6h", "p24h")
MIN_EVENT_LABELS_PER_CORE = 30
MIN_ASSET_LABELS_PER_CORE = 20
MIN_POSITIVE_CORE_WINDOWS = 2
MIN_LATE_POSITIVE_CORE_WINDOWS = 1
MIN_RHO = 0.10
STRONG_NEGATIVE_RHO = -0.20
HIGH_CONFIDENCE = 0.80

ScoreAuditFn = Callable[[Path | str], dict[str, Any]]


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _average(values: list[float]) -> float | None:
    return mean(values) if values else None


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx = mean(xs)
    my = mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denom_x = math.sqrt(sum(v * v for v in dx))
    denom_y = math.sqrt(sum(v * v for v in dy))
    if denom_x <= 0.0 or denom_y <= 0.0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / (denom_x * denom_y)


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda idx: (values[idx], idx))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        average_rank = (start + 1 + end) / 2.0
        for pos in range(start, end):
            ranks[order[pos]] = average_rank
        start = end
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    return _pearson(_ranks(xs), _ranks(ys))


def _outcome(row: dict[str, Any], window: str) -> float | None:
    outcomes = row.get("evaluation_only_outcomes")
    if isinstance(outcomes, dict):
        post = outcomes.get("post_listing_returns_pct")
        if isinstance(post, dict):
            return _finite(post.get(window))
    direct = row.get("post_listing_returns_pct")
    if isinstance(direct, dict):
        return _finite(direct.get(window))
    return None


def _launch_available(row: dict[str, Any]) -> bool:
    components = row.get("components")
    if not isinstance(components, dict):
        return False
    component = components.get("launch_continuity")
    return bool(isinstance(component, dict) and component.get("available"))


def _quartile_stats(rows: list[dict[str, Any]], window: str) -> dict[str, Any]:
    labeled: list[tuple[float, float]] = []
    for row in rows:
        score = _finite(row.get("shadow_score"))
        outcome = _outcome(row, window)
        if score is not None and outcome is not None:
            labeled.append((score, outcome))
    if not labeled:
        return {
            "labeled_count": 0,
            "quartile_size": 0,
            "top_mean_return_pct": None,
            "bottom_mean_return_pct": None,
            "top_minus_bottom_mean_return_pct": None,
            "top_positive_rate": None,
            "bottom_positive_rate": None,
        }
    labeled.sort(key=lambda item: (item[0], item[1]))
    size = max(1, int(math.ceil(len(labeled) * 0.25)))
    bottom = labeled[:size]
    top = labeled[-size:]
    top_mean = mean(value for _, value in top)
    bottom_mean = mean(value for _, value in bottom)
    return {
        "labeled_count": len(labeled),
        "quartile_size": size,
        "top_mean_return_pct": round(top_mean, 6),
        "bottom_mean_return_pct": round(bottom_mean, 6),
        "top_minus_bottom_mean_return_pct": round(top_mean - bottom_mean, 6),
        "top_positive_rate": round(sum(value > 0.0 for _, value in top) / len(top), 6),
        "bottom_positive_rate": round(sum(value > 0.0 for _, value in bottom) / len(bottom), 6),
    }


def _window_stats(rows: list[dict[str, Any]], window: str) -> dict[str, Any]:
    xs: list[float] = []
    ys: list[float] = []
    for row in rows:
        score = _finite(row.get("shadow_score"))
        outcome = _outcome(row, window)
        if score is not None and outcome is not None:
            xs.append(score)
            ys.append(outcome)
    return {
        "labeled_count": len(xs),
        "pearson": _rounded(_pearson(xs, ys)),
        "spearman": _rounded(_spearman(xs, ys)),
        "quartiles": _quartile_stats(rows, window),
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "row_count": len(rows),
        "windows": {window: _window_stats(rows, window) for window in OUTCOME_WINDOWS},
    }


def _aggregate_assets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        asset_key = str(row.get("coingecko_id") or "").strip() or f"case:{row.get('case_key') or ''}"
        grouped[asset_key].append(row)

    assets: list[dict[str, Any]] = []
    for asset_key in sorted(grouped):
        members = grouped[asset_key]
        scores = [value for value in (_finite(row.get("shadow_score")) for row in members) if value is not None]
        confidences = [value for value in (_finite(row.get("confidence")) for row in members) if value is not None]
        opens = [value for value in (_finite(row.get("domestic_open_at")) for row in members) if value is not None]
        exchanges = sorted({str(row.get("domestic_exchange") or "") for row in members if row.get("domestic_exchange")})
        outcome_map: dict[str, float | None] = {}
        for window in OUTCOME_WINDOWS:
            values = [value for value in (_outcome(row, window) for row in members) if value is not None]
            outcome_map[window] = _average(values)
        assets.append(
            {
                "asset_key": asset_key,
                "member_event_count": len(members),
                "shadow_score": _average(scores),
                "confidence": _average(confidences),
                "domestic_open_at": min(opens) if opens else 0.0,
                "domestic_exchange": exchanges[0] if len(exchanges) == 1 else "mixed",
                "launch_available": any(_launch_available(row) for row in members),
                "post_listing_returns_pct": outcome_map,
            }
        )
    return assets


def _chronological_halves(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            float(_finite(row.get("domestic_open_at")) or 0.0),
            str(row.get("case_key") or row.get("asset_key") or ""),
        ),
    )
    midpoint = max(1, len(ordered) // 2)
    return ordered[:midpoint], ordered[midpoint:]


def _group_metrics(rows: list[dict[str, Any]], key_fn: Callable[[dict[str, Any]], str]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[key_fn(row)].append(row)
    return {name: _metrics(group) for name, group in sorted(groups.items())}


def _criterion_summary(
    *,
    event_metrics: dict[str, Any],
    asset_metrics: dict[str, Any],
    late_metrics: dict[str, Any],
) -> dict[str, Any]:
    event_windows = event_metrics.get("windows") if isinstance(event_metrics.get("windows"), dict) else {}
    asset_windows = asset_metrics.get("windows") if isinstance(asset_metrics.get("windows"), dict) else {}
    late_windows = late_metrics.get("windows") if isinstance(late_metrics.get("windows"), dict) else {}

    event_labels_ok = all(
        int((event_windows.get(window) or {}).get("labeled_count") or 0) >= MIN_EVENT_LABELS_PER_CORE
        for window in CORE_WINDOWS
    )
    asset_labels_ok = all(
        int((asset_windows.get(window) or {}).get("labeled_count") or 0) >= MIN_ASSET_LABELS_PER_CORE
        for window in CORE_WINDOWS
    )

    event_positive_rho = sum(
        (_finite((event_windows.get(window) or {}).get("spearman")) or -999.0) >= MIN_RHO
        for window in CORE_WINDOWS
    )
    asset_positive_rho = sum(
        (_finite((asset_windows.get(window) or {}).get("spearman")) or -999.0) >= MIN_RHO
        for window in CORE_WINDOWS
    )
    late_positive_rho = sum(
        (_finite((late_windows.get(window) or {}).get("spearman")) or -999.0) >= MIN_RHO
        for window in CORE_WINDOWS
    )

    event_positive_spread = sum(
        (
            _finite(
                ((event_windows.get(window) or {}).get("quartiles") or {}).get(
                    "top_minus_bottom_mean_return_pct"
                )
            )
            or -999.0
        )
        > 0.0
        for window in CORE_WINDOWS
    )
    asset_positive_spread = sum(
        (
            _finite(
                ((asset_windows.get(window) or {}).get("quartiles") or {}).get(
                    "top_minus_bottom_mean_return_pct"
                )
            )
            or -999.0
        )
        > 0.0
        for window in CORE_WINDOWS
    )

    strong_negative = []
    for level_name, windows in (("event", event_windows), ("asset", asset_windows)):
        for window in CORE_WINDOWS:
            rho = _finite((windows.get(window) or {}).get("spearman"))
            if rho is not None and rho <= STRONG_NEGATIVE_RHO:
                strong_negative.append({"level": level_name, "window": window, "spearman": round(rho, 6)})

    criteria = {
        "event_core_label_coverage": event_labels_ok,
        "asset_core_label_coverage": asset_labels_ok,
        "event_positive_rank_signal": event_positive_rho >= MIN_POSITIVE_CORE_WINDOWS,
        "asset_positive_rank_signal": asset_positive_rho >= MIN_POSITIVE_CORE_WINDOWS,
        "event_positive_top_bottom_spread": event_positive_spread >= MIN_POSITIVE_CORE_WINDOWS,
        "asset_positive_top_bottom_spread": asset_positive_spread >= MIN_POSITIVE_CORE_WINDOWS,
        "late_half_has_positive_rank_signal": late_positive_rho >= MIN_LATE_POSITIVE_CORE_WINDOWS,
        "no_strong_negative_core_rank_signal": not strong_negative,
    }
    return {
        "thresholds": {
            "core_windows": list(CORE_WINDOWS),
            "min_event_labels_per_core": MIN_EVENT_LABELS_PER_CORE,
            "min_asset_labels_per_core": MIN_ASSET_LABELS_PER_CORE,
            "min_positive_core_windows": MIN_POSITIVE_CORE_WINDOWS,
            "min_late_positive_core_windows": MIN_LATE_POSITIVE_CORE_WINDOWS,
            "min_spearman_rho": MIN_RHO,
            "strong_negative_spearman_rho": STRONG_NEGATIVE_RHO,
        },
        "observed": {
            "event_positive_rank_windows": event_positive_rho,
            "asset_positive_rank_windows": asset_positive_rho,
            "event_positive_spread_windows": event_positive_spread,
            "asset_positive_spread_windows": asset_positive_spread,
            "late_positive_rank_windows": late_positive_rho,
            "strong_negative_core_windows": strong_negative,
        },
        "criteria": criteria,
        "all_criteria_pass": all(criteria.values()),
    }


def audit_dex_shadow_score_validation(
    path: Path | str = DB_PATH,
    *,
    score_audit_fn: ScoreAuditFn = audit_dex_shadow_scores,
) -> dict[str, Any]:
    """Build63 read-only retrospective validation for Build62 shadow scores.

    The Build62 formula is treated as frozen. Post-listing outcomes are consumed
    only as evaluation labels. This module does not tune weights, fit a model,
    choose a trade threshold, mutate the database, or wire any order path.
    """

    score_payload = score_audit_fn(Path(path))
    base = {
        "ok": False,
        "validation_version": VALIDATION_VERSION,
        "validation_name": VALIDATION_NAME,
        "score_version": int(score_payload.get("score_version") or 0),
        "score_name": str(score_payload.get("score_name") or ""),
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "paper_ab_wired": False,
        "read_only": True,
        "network_fetches": False,
        "database_mutation": False,
        "cloudflare_publishing": False,
        "strategy_signal_mutation": False,
        "position_sizing_mutation": False,
        "score_formula_changed": False,
        "score_weights_changed": False,
        "training_or_fitting": False,
        "trade_threshold": None,
        "post_listing_outcomes_used_for_evaluation_only": True,
        "retrospective_source_selection_caveat": bool(score_payload.get("retrospective_source_selection")),
        "forward_validation_required": True,
        "promotion_to_live_blocked": True,
    }

    score_ready = bool(
        score_payload.get("ok")
        and score_payload.get("status") == "scored_read_only"
        and score_payload.get("all_usable_cases_scored")
        and not score_payload.get("score_wired")
        and not score_payload.get("can_place_orders")
    )
    if not score_ready:
        return {
            **base,
            "status": "build62_score_audit_blocked",
            "score_audit_ready": False,
            "event_level": _metrics([]),
            "asset_level_dedup": _metrics([]),
            "validation_gate": {
                "paper_ab_candidate_advisory": False,
                "reason": "build62_score_audit_not_ready",
            },
            "review": {
                "next_action": "repair_build62_score_audit_before_validation",
                "paper_ab_wired": False,
            },
        }

    rows = [row for row in score_payload.get("case_scores") or [] if isinstance(row, dict)]
    if not rows:
        return {
            **base,
            "status": "no_score_rows",
            "score_audit_ready": True,
            "event_level": _metrics([]),
            "asset_level_dedup": _metrics([]),
            "validation_gate": {
                "paper_ab_candidate_advisory": False,
                "reason": "no_score_rows",
            },
            "review": {
                "next_action": "repair_build62_case_score_output",
                "paper_ab_wired": False,
            },
        }

    event_metrics = _metrics(rows)
    asset_rows = _aggregate_assets(rows)
    asset_metrics = _metrics(asset_rows)

    event_early, event_late = _chronological_halves(rows)
    asset_early, asset_late = _chronological_halves(asset_rows)
    event_chrono = {"early": _metrics(event_early), "late": _metrics(event_late)}
    asset_chrono = {"early": _metrics(asset_early), "late": _metrics(asset_late)}

    exchange_metrics = _group_metrics(rows, lambda row: str(row.get("domestic_exchange") or "unknown"))
    confidence_metrics = _group_metrics(
        rows,
        lambda row: (
            "full_1.0"
            if (_finite(row.get("confidence")) or 0.0) >= 1.0
            else "high_0.8_to_lt1.0"
            if (_finite(row.get("confidence")) or 0.0) >= HIGH_CONFIDENCE
            else "low_lt0.8"
        ),
    )
    launch_metrics = _group_metrics(rows, lambda row: "with_launch" if _launch_available(row) else "without_launch")

    criterion_summary = _criterion_summary(
        event_metrics=event_metrics,
        asset_metrics=asset_metrics,
        late_metrics=event_chrono["late"],
    )
    advisory = bool(criterion_summary.get("all_criteria_pass"))

    return {
        **base,
        "ok": True,
        "status": "validated_read_only",
        "score_audit_ready": True,
        "event_case_count": len(rows),
        "asset_count_dedup": len(asset_rows),
        "duplicate_event_case_count": max(0, len(rows) - len(asset_rows)),
        "event_level": event_metrics,
        "asset_level_dedup": asset_metrics,
        "chronological_halves": {
            "event_level": event_chrono,
            "asset_level_dedup": asset_chrono,
        },
        "exchange_sensitivity": exchange_metrics,
        "confidence_sensitivity": confidence_metrics,
        "launch_availability_sensitivity": launch_metrics,
        "validation_protocol": criterion_summary,
        "validation_gate": {
            "paper_ab_candidate_advisory": advisory,
            "forward_validation_required": True,
            "retrospective_source_selection_caveat": bool(score_payload.get("retrospective_source_selection")),
            "live_promotion_allowed": False,
        },
        "review": {
            "paper_ab_wired": False,
            "orders_changed": False,
            "existing_strategy_signal_changed": False,
            "position_sizing_changed": False,
            "next_action": (
                "design_forward_parallel_paper_ab_build64_without_order_wiring"
                if advisory
                else "revise_or_reject_shadow_score_hypothesis_before_paper_ab"
            ),
        },
    }
