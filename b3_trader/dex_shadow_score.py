from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from .auto_demo_v2 import DB_PATH
from .dex_launch_quality import evaluate_dex_launch_quality
from .dex_shadow_readiness_audit import audit_dex_shadow_readiness


SCORE_VERSION = 1
SCORE_NAME = "dex_prelisting_shadow_hypothesis_v1"

COMPONENT_WEIGHTS = {
    "pre_short_momentum": 0.45,
    "pre_medium_momentum": 0.20,
    "pre_acceleration": 0.15,
    "launch_continuity": 0.20,
}
PRE_SHORT_SCALES = {"t1h": 8.0, "t6h": 15.0, "t1d": 25.0}
PRE_MEDIUM_SCALES = {"t3d": 40.0, "t7d": 70.0}
LAUNCH_SCALES = {"p5m": 20.0, "p1h": 30.0, "p6h": 45.0, "p24h": 70.0}
OUTCOME_WINDOWS = ("p5m", "p1h", "p6h", "p24h", "p3d", "p7d")

ReadinessFn = Callable[[Path | str], dict[str, Any]]
QualityFn = Callable[[Path | str], dict[str, Any]]


def _json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clip(value: float, low: float, high: float) -> float:
    return min(high, max(low, float(value)))


def _average(values: list[float]) -> float | None:
    return mean(values) if values else None


def _normalized_return(value: float, scale: float) -> float:
    return math.tanh(float(value) / max(1e-9, float(scale)))


def _return_from_point(point: Any, key: str) -> float | None:
    if not isinstance(point, dict):
        return None
    return _finite(point.get(key))


def _window_returns(
    feature_rows: list[dict[str, Any]],
    *,
    section: str,
    side: str,
    windows: tuple[str, ...],
    value_key: str,
) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for window in windows:
        values: list[float] = []
        for row in feature_rows:
            feature = row.get("feature") if isinstance(row.get("feature"), dict) else {}
            block = feature.get(section) if isinstance(feature.get(section), dict) else {}
            side_data = block.get(side) if isinstance(block.get(side), dict) else {}
            value = _return_from_point(side_data.get(window), value_key)
            if value is not None:
                values.append(value)
        result[window] = _average(values)
    return result


def _signal_from_windows(values: dict[str, float | None], scales: dict[str, float]) -> float | None:
    normalized = [
        _normalized_return(float(values[key]), scale)
        for key, scale in scales.items()
        if values.get(key) is not None
    ]
    return _average(normalized)


def _launch_candidate(
    rows: list[dict[str, Any]],
    *,
    domestic_open_at: float,
) -> dict[str, Any] | None:
    candidates: list[tuple[int, int, float, str, dict[str, Any], dict[str, float | None]]] = []
    for row in rows:
        feature = row.get("feature") if isinstance(row.get("feature"), dict) else {}
        launch = feature.get("pool_launch_window") if isinstance(feature.get("pool_launch_window"), dict) else {}
        if launch.get("status") != "collected":
            continue

        safe_returns: dict[str, float | None] = {}
        windows = launch.get("windows") if isinstance(launch.get("windows"), dict) else {}
        created = _finite(launch.get("pool_created_at"))
        if created is None:
            created = _finite(row.get("pool_created_at"))
        for name, offset in (("p5m", 300.0), ("p1h", 3600.0), ("p6h", 21600.0), ("p24h", 86400.0)):
            point = windows.get(name) if isinstance(windows.get(name), dict) else None
            target_ts = _finite(point.get("target_ts")) if isinstance(point, dict) else None
            if target_ts is None and created is not None:
                target_ts = created + offset
            if target_ts is None or target_ts > domestic_open_at:
                safe_returns[name] = None
                continue
            safe_returns[name] = _return_from_point(point, "return_from_launch_pct")

        available = sum(value is not None for value in safe_returns.values())
        if available <= 0:
            continue
        selected_primary = int(row.get("selected_primary") or 0)
        pool_created_at = float(created or 0.0)
        pool_address = str(row.get("pool_address") or "")
        candidates.append((-available, -selected_primary, pool_created_at, pool_address, row, safe_returns))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[:4])
    _, _, _, _, row, safe_returns = candidates[0]
    return {
        "row": row,
        "returns": safe_returns,
        "source_kind": "primary" if int(row.get("selected_primary") or 0) == 1 else "alternate_accepted",
    }


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    position = _clip(float(q), 0.0, 1.0) * (len(ordered) - 1)
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return ordered[lo]
    fraction = position - lo
    return ordered[lo] * (1.0 - fraction) + ordered[hi] * fraction


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "p10": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p90": None,
            "max": None,
            "mean": None,
        }
    return {
        "count": len(values),
        "min": round(min(values), 6),
        "p10": round(float(_percentile(values, 0.10)), 6),
        "p25": round(float(_percentile(values, 0.25)), 6),
        "median": round(float(_percentile(values, 0.50)), 6),
        "p75": round(float(_percentile(values, 0.75)), 6),
        "p90": round(float(_percentile(values, 0.90)), 6),
        "max": round(max(values), 6),
        "mean": round(mean(values), 6),
    }


def _case_score(*, case: dict[str, Any], feature_rows: list[dict[str, Any]]) -> dict[str, Any]:
    domestic_open_at = float(case.get("domestic_open_at") or 0.0)
    primary_rows = [
        row
        for row in feature_rows
        if int(row.get("selected_primary") or 0) == 1
        and str(row.get("gate_status") or "") == "accepted"
        and isinstance(row.get("feature"), dict)
        and isinstance(row["feature"].get("domestic_listing_window"), dict)
        and row["feature"]["domestic_listing_window"].get("status") == "collected"
        and bool(
            (
                row["feature"].get("pool_quality")
                if isinstance(row["feature"].get("pool_quality"), dict)
                else {}
            ).get("passed")
        )
    ]

    pre_short_values = _window_returns(
        primary_rows,
        section="domestic_listing_window",
        side="pre",
        windows=tuple(PRE_SHORT_SCALES),
        value_key="return_to_domestic_open_pct",
    )
    pre_medium_values = _window_returns(
        primary_rows,
        section="domestic_listing_window",
        side="pre",
        windows=tuple(PRE_MEDIUM_SCALES),
        value_key="return_to_domestic_open_pct",
    )
    short_signal = _signal_from_windows(pre_short_values, PRE_SHORT_SCALES)
    medium_signal = _signal_from_windows(pre_medium_values, PRE_MEDIUM_SCALES)
    acceleration_signal = (
        _clip(short_signal - medium_signal, -1.0, 1.0)
        if short_signal is not None and medium_signal is not None
        else None
    )

    launch_pick = _launch_candidate(feature_rows, domestic_open_at=domestic_open_at)
    launch_values = (
        launch_pick["returns"]
        if isinstance(launch_pick, dict) and isinstance(launch_pick.get("returns"), dict)
        else {key: None for key in LAUNCH_SCALES}
    )
    launch_signal = _signal_from_windows(launch_values, LAUNCH_SCALES)

    signals = {
        "pre_short_momentum": short_signal,
        "pre_medium_momentum": medium_signal,
        "pre_acceleration": acceleration_signal,
        "launch_continuity": launch_signal,
    }
    contributions: dict[str, dict[str, Any]] = {}
    available_weight = 0.0
    signed_sum = 0.0
    missing_components: list[str] = []
    for name, weight in COMPONENT_WEIGHTS.items():
        signal = signals.get(name)
        if signal is None:
            missing_components.append(name)
            contributions[name] = {"available": False, "weight": weight, "signal": None, "points": 0.0}
            continue
        signal = _clip(float(signal), -1.0, 1.0)
        points = 50.0 * weight * signal
        available_weight += weight
        signed_sum += weight * signal
        contributions[name] = {
            "available": True,
            "weight": weight,
            "signal": round(signal, 6),
            "points": round(points, 6),
        }

    score = _clip(50.0 + 50.0 * signed_sum, 0.0, 100.0)
    outcome_labels = _window_returns(
        primary_rows,
        section="domestic_listing_window",
        side="post",
        windows=OUTCOME_WINDOWS,
        value_key="return_from_domestic_open_pct",
    )

    launch_source: dict[str, Any] | None = None
    if isinstance(launch_pick, dict):
        source_row = launch_pick.get("row") if isinstance(launch_pick.get("row"), dict) else {}
        launch_source = {
            "source_kind": str(launch_pick.get("source_kind") or ""),
            "network_id": str(source_row.get("network_id") or ""),
            "pool_address": str(source_row.get("pool_address") or ""),
            "dex_id": str(source_row.get("dex_id") or ""),
            "pool_created_at": float(source_row.get("pool_created_at") or 0.0),
        }

    return {
        "score_version": SCORE_VERSION,
        "score_name": SCORE_NAME,
        "case_key": str(case.get("case_key") or ""),
        "coingecko_id": str(case.get("coingecko_id") or ""),
        "domestic_exchange": str(case.get("domestic_exchange") or ""),
        "domestic_market": str(case.get("domestic_market") or ""),
        "symbol": str(case.get("symbol") or ""),
        "domestic_open_at": domestic_open_at,
        "shadow_score": round(score, 6),
        "confidence": round(available_weight, 6),
        "components": contributions,
        "inputs": {
            "pre_short_returns_pct": pre_short_values,
            "pre_medium_returns_pct": pre_medium_values,
            "launch_returns_pct_prelisting_only": launch_values,
            "launch_source": launch_source,
            "primary_feature_rows": len(primary_rows),
        },
        "missing_feature_flags": missing_components,
        "evaluation_only_outcomes": {
            "excluded_from_score": True,
            "post_listing_returns_pct": outcome_labels,
        },
        "explanation": {
            "base_score": 50.0,
            "component_points_sum": round(50.0 * signed_sum, 6),
            "higher_score_means": "stronger_prelisting_and_prelisting_safe_launch_momentum_under_v1_hypothesis",
            "trade_threshold": None,
            "trade_recommendation": None,
        },
    }


def audit_dex_shadow_scores(
    path: Path | str = DB_PATH,
    *,
    readiness_fn: ReadinessFn = audit_dex_shadow_readiness,
    quality_fn: QualityFn = evaluate_dex_launch_quality,
) -> dict[str, Any]:
    """Build62 read-only DEX shadow-score audit.

    This is an unfitted research hypothesis. Only information timestamped at or
    before the domestic listing may contribute. Post-listing reaction fields are
    emitted only as evaluation labels and are never consumed by the score.
    """

    db_path = Path(path)
    readiness = readiness_fn(db_path)
    base = {
        "ok": False,
        "score_version": SCORE_VERSION,
        "score_name": SCORE_NAME,
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_wired": False,
        "read_only": True,
        "network_fetches": False,
        "strategy_signal_mutation": False,
        "order_path_mutation": False,
        "position_sizing_mutation": False,
        "cloudflare_publishing": False,
        "selected_primary_mutation": False,
        "training_or_fitting": False,
        "trade_threshold": None,
        "uses_post_listing_features_in_score": False,
        "uses_pool_quality_levels_in_score": False,
        "retrospective_source_selection": True,
        "readiness_gate": {
            "required": True,
            "shadow_readiness_advisory": bool(readiness.get("shadow_readiness_advisory")),
            "blocking_reasons": list(readiness.get("blocking_reasons") or []),
        },
    }
    if not readiness.get("shadow_readiness_advisory"):
        return {
            **base,
            "status": "readiness_blocked",
            "scoring_enabled_for_audit": False,
            "case_score_count": 0,
            "case_scores": [],
            "distribution": _distribution([]),
            "review": {"next_action": "repair_build53_readiness_before_shadow_scoring", "paper_ab_wired": False},
        }
    if not db_path.exists():
        return {
            **base,
            "status": "database_missing",
            "scoring_enabled_for_audit": False,
            "case_score_count": 0,
            "case_scores": [],
            "distribution": _distribution([]),
            "review": {"next_action": "provide_local_research_database", "paper_ab_wired": False},
        }

    quality = quality_fn(db_path)
    usable_rows = [
        row
        for row in quality.get("cases") or []
        if isinstance(row, dict) and row.get("usable_for_shadow_analysis") and row.get("case_key")
    ]
    usable_keys = sorted({str(row["case_key"]) for row in usable_rows})
    coingecko_by_case = {str(row["case_key"]): str(row.get("coingecko_id") or "") for row in usable_rows}
    if not usable_keys:
        return {
            **base,
            "status": "no_usable_cases",
            "scoring_enabled_for_audit": False,
            "case_score_count": 0,
            "case_scores": [],
            "distribution": _distribution([]),
            "review": {"next_action": "repair_usable_sample", "paper_ab_wired": False},
        }

    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {str(row["name"]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        required = {"listing_history_cases", "dex_launch_assets", "dex_launch_pools", "dex_launch_features"}
        missing_tables = sorted(required - tables)
        if missing_tables:
            return {
                **base,
                "status": "required_tables_missing",
                "scoring_enabled_for_audit": False,
                "missing_tables": missing_tables,
                "case_score_count": 0,
                "case_scores": [],
                "distribution": _distribution([]),
                "review": {"next_action": "repair_research_schema", "paper_ab_wired": False},
            }

        placeholders = ",".join("?" for _ in usable_keys)
        case_rows = conn.execute(
            f"""
            SELECT case_key,domestic_exchange,domestic_market,symbol,domestic_open_at
            FROM listing_history_cases
            WHERE case_key IN ({placeholders})
            ORDER BY case_key
            """,
            tuple(usable_keys),
        ).fetchall()
        cases: dict[str, dict[str, Any]] = {}
        for row in case_rows:
            item = dict(row)
            case_key = str(item.get("case_key") or "")
            item["coingecko_id"] = coingecko_by_case.get(case_key, "")
            cases[case_key] = item

        feature_rows_by_case: dict[str, list[dict[str, Any]]] = {key: [] for key in usable_keys}
        rows = conn.execute(
            f"""
            SELECT
              a.case_key,a.asset_key,a.network_id,
              p.pool_address,p.dex_id,p.pool_created_at,p.gate_status,p.selected_primary,
              f.feature_version,f.feature_json
            FROM dex_launch_assets a
            JOIN dex_launch_pools p ON p.asset_key=a.asset_key
            JOIN dex_launch_features f
              ON f.asset_key=p.asset_key AND f.pool_address=p.pool_address
            WHERE a.case_key IN ({placeholders})
              AND p.gate_status='accepted'
            ORDER BY a.case_key,p.selected_primary DESC,p.pool_created_at,p.pool_address
            """,
            tuple(usable_keys),
        ).fetchall()
        for row in rows:
            item = dict(row)
            item["feature"] = _json(item.pop("feature_json"))
            case_key = str(item.get("case_key") or "")
            if case_key in feature_rows_by_case:
                feature_rows_by_case[case_key].append(item)

        scores = [
            _case_score(case=cases[key], feature_rows=feature_rows_by_case.get(key, []))
            for key in usable_keys
            if key in cases
        ]
    finally:
        conn.close()

    score_values = [float(row["shadow_score"]) for row in scores]
    confidence_values = [float(row["confidence"]) for row in scores]
    missing_counter: Counter[str] = Counter()
    component_available: Counter[str] = Counter()
    outcome_available: Counter[str] = Counter()
    for row in scores:
        missing_counter.update(str(name) for name in row.get("missing_feature_flags") or [])
        for name, component in (row.get("components") or {}).items():
            if isinstance(component, dict) and component.get("available"):
                component_available[str(name)] += 1
        outcomes = (
            row.get("evaluation_only_outcomes", {}).get("post_listing_returns_pct", {})
            if isinstance(row.get("evaluation_only_outcomes"), dict)
            else {}
        )
        if isinstance(outcomes, dict):
            for name, value in outcomes.items():
                if value is not None:
                    outcome_available[str(name)] += 1

    ranked = sorted(scores, key=lambda row: (-float(row["shadow_score"]), str(row["case_key"])))
    preview = {
        "highest_5": [
            {
                "case_key": row["case_key"],
                "shadow_score": row["shadow_score"],
                "confidence": row["confidence"],
                "missing_feature_flags": row["missing_feature_flags"],
            }
            for row in ranked[:5]
        ],
        "lowest_5": [
            {
                "case_key": row["case_key"],
                "shadow_score": row["shadow_score"],
                "confidence": row["confidence"],
                "missing_feature_flags": row["missing_feature_flags"],
            }
            for row in sorted(scores, key=lambda row: (float(row["shadow_score"]), str(row["case_key"])))[:5]
        ],
    }

    return {
        **base,
        "ok": True,
        "status": "scored_read_only",
        "scoring_enabled_for_audit": True,
        "case_score_count": len(scores),
        "expected_usable_case_count": len(usable_keys),
        "all_usable_cases_scored": len(scores) == len(usable_keys),
        "component_weights": dict(COMPONENT_WEIGHTS),
        "score_semantics": {
            "base": 50.0,
            "range": [0.0, 100.0],
            "unfitted_hypothesis": True,
            "post_listing_outcomes_are_labels_only": True,
            "missing_components_are_neutral_zero_contribution": True,
            "confidence_is_available_component_weight": True,
        },
        "distribution": _distribution(score_values),
        "confidence_distribution": _distribution(confidence_values),
        "component_available_case_counts": dict(sorted(component_available.items())),
        "missing_component_case_counts": dict(sorted(missing_counter.items())),
        "evaluation_label_available_case_counts": dict(sorted(outcome_available.items())),
        "preview": preview,
        "case_scores": scores,
        "review": {
            "paper_ab_wired": False,
            "existing_strategy_signal_changed": False,
            "position_sizing_changed": False,
            "orders_changed": False,
            "next_action": "review_score_distribution_then_design_parallel_paper_ab_build63",
        },
    }
