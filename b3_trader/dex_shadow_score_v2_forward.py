from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .auto_demo_v2 import DB_PATH
from .dex_launch_quality import evaluate_dex_launch_quality
from .dex_shadow_score import (
    OUTCOME_WINDOWS,
    PRE_MEDIUM_SCALES,
    PRE_SHORT_SCALES,
    _clip,
    _distribution,
    _json,
    _signal_from_windows,
    _window_returns,
)
from .dex_shadow_score_v2_preregistration import (
    FORWARD_CUTOFF_TS,
    FORWARD_CUTOFF_UTC,
    V2_COMPONENTS,
    V2_SCORE_NAME,
    V2_SCORE_VERSION,
    declare_dex_shadow_score_v2_preregistration,
)


FORWARD_SCORER_VERSION = 1
FORWARD_SCORER_NAME = "dex_shadow_score_v2_forward_scorer_v1"

PreregistrationFn = Callable[[Path | str], dict[str, Any]]
QualityFn = Callable[[Path | str], dict[str, Any]]


def _eligible_primary_rows(feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
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


def _forward_case_score(*, case: dict[str, Any], feature_rows: list[dict[str, Any]]) -> dict[str, Any]:
    domestic_open_at = float(case.get("domestic_open_at") or 0.0)
    if domestic_open_at < FORWARD_CUTOFF_TS:
        raise ValueError("build66_refuses_pre_cutoff_case")

    primary_rows = _eligible_primary_rows(feature_rows)
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
    short_source_signal = _signal_from_windows(pre_short_values, PRE_SHORT_SCALES)
    medium_source_signal = _signal_from_windows(pre_medium_values, PRE_MEDIUM_SCALES)
    source_signals = {
        "pre_short_exhaustion": short_source_signal,
        "pre_medium_exhaustion": medium_source_signal,
    }

    contributions: dict[str, dict[str, Any]] = {}
    missing_components: list[str] = []
    available_weight = 0.0
    signed_sum = 0.0
    for name, spec in V2_COMPONENTS.items():
        weight = float(spec["weight"])
        source_signal = source_signals.get(name)
        if source_signal is None:
            missing_components.append(name)
            contributions[name] = {
                "available": False,
                "weight": weight,
                "source_component": str(spec["source_component"]),
                "transform": str(spec["transform"]),
                "source_signal": None,
                "signal": None,
                "points": 0.0,
            }
            continue

        clipped_source = _clip(float(source_signal), -1.0, 1.0)
        transformed_signal = -clipped_source
        points = 50.0 * weight * transformed_signal
        available_weight += weight
        signed_sum += weight * transformed_signal
        contributions[name] = {
            "available": True,
            "weight": weight,
            "source_component": str(spec["source_component"]),
            "transform": str(spec["transform"]),
            "source_signal": round(clipped_source, 6),
            "signal": round(transformed_signal, 6),
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

    return {
        "score_version": V2_SCORE_VERSION,
        "score_name": V2_SCORE_NAME,
        "forward_scorer_version": FORWARD_SCORER_VERSION,
        "forward_scorer_name": FORWARD_SCORER_NAME,
        "case_key": str(case.get("case_key") or ""),
        "coingecko_id": str(case.get("coingecko_id") or ""),
        "domestic_exchange": str(case.get("domestic_exchange") or ""),
        "domestic_market": str(case.get("domestic_market") or ""),
        "symbol": str(case.get("symbol") or ""),
        "domestic_open_at": domestic_open_at,
        "forward_cutoff_utc": FORWARD_CUTOFF_UTC,
        "forward_eligible": True,
        "shadow_score": round(score, 6),
        "confidence": round(available_weight, 6),
        "components": contributions,
        "inputs": {
            "pre_short_returns_pct": pre_short_values,
            "pre_medium_returns_pct": pre_medium_values,
            "primary_feature_rows": len(primary_rows),
            "post_listing_inputs_used_in_score": False,
        },
        "missing_feature_flags": missing_components,
        "evaluation_only_outcomes": {
            "excluded_from_score": True,
            "post_listing_returns_pct": outcome_labels,
        },
        "explanation": {
            "base_score": 50.0,
            "component_points_sum": round(50.0 * signed_sum, 6),
            "higher_score_means": "less_prelisting_exhaustion_under_preregistered_v2_hypothesis",
            "trade_threshold": None,
            "trade_recommendation": None,
        },
    }


def audit_dex_shadow_score_v2_forward(
    path: Path | str = DB_PATH,
    *,
    preregistration_fn: PreregistrationFn = declare_dex_shadow_score_v2_preregistration,
    quality_fn: QualityFn = evaluate_dex_launch_quality,
) -> dict[str, Any]:
    """Build66 read-only forward scorer for the preregistered v2 hypothesis.

    Cases before Build65's frozen cutoff are design-only and are never scored as
    v2. Build66 performs no fitting, persistence, strategy wiring, or order work.
    """

    db_path = Path(path)
    preregistration = preregistration_fn(db_path)
    prereg_ready = bool(
        preregistration.get("ok")
        and preregistration.get("status") == "v2_preregistered_forward_only"
        and (preregistration.get("v1") or {}).get("retired")
        and (preregistration.get("v2") or {}).get("score_version") == V2_SCORE_VERSION
        and (preregistration.get("v2") or {}).get("score_name") == V2_SCORE_NAME
        and (preregistration.get("review") or {}).get("build66_forward_scorer_allowed")
        and float((preregistration.get("forward_boundary") or {}).get("cutoff_unix") or -1.0)
        == FORWARD_CUTOFF_TS
    )

    base = {
        "ok": False,
        "forward_scorer_version": FORWARD_SCORER_VERSION,
        "forward_scorer_name": FORWARD_SCORER_NAME,
        "score_version": V2_SCORE_VERSION,
        "score_name": V2_SCORE_NAME,
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "paper_ab_wired": False,
        "score_wired": False,
        "read_only": True,
        "network_fetches": False,
        "database_mutation": False,
        "cloudflare_publishing": False,
        "strategy_signal_mutation": False,
        "order_path_mutation": False,
        "position_sizing_mutation": False,
        "selected_primary_mutation": False,
        "training_or_fitting": False,
        "trade_threshold": None,
        "retrospective_validation_claimed": False,
        "forward_only": True,
        "forward_boundary": {
            "cutoff_utc": FORWARD_CUTOFF_UTC,
            "cutoff_unix": FORWARD_CUTOFF_TS,
            "eligibility_rule": "domestic_open_at_gte_forward_cutoff",
            "pre_cutoff_cases_design_only": True,
            "pre_cutoff_cases_validation_excluded": True,
        },
    }
    if not prereg_ready:
        return {
            **base,
            "status": "preregistration_blocked",
            "preregistration_ready": False,
            "historical_rows_scored_as_v2": False,
            "case_score_count": 0,
            "case_scores": [],
            "distribution": _distribution([]),
            "review": {
                "build67_forward_validation_allowed": False,
                "next_action": "repair_build65_preregistration_before_forward_scoring",
            },
        }
    if not db_path.exists():
        return {
            **base,
            "status": "database_missing",
            "preregistration_ready": True,
            "historical_rows_scored_as_v2": False,
            "case_score_count": 0,
            "case_scores": [],
            "distribution": _distribution([]),
            "review": {
                "build67_forward_validation_allowed": False,
                "next_action": "provide_local_research_database",
            },
        }

    quality = quality_fn(db_path)
    usable_rows = [
        row
        for row in quality.get("cases") or []
        if isinstance(row, dict) and row.get("usable_for_shadow_analysis") and row.get("case_key")
    ]
    usable_keys = sorted({str(row["case_key"]) for row in usable_rows})
    coingecko_by_case = {str(row["case_key"]): str(row.get("coingecko_id") or "") for row in usable_rows}

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
                "preregistration_ready": True,
                "missing_tables": missing_tables,
                "historical_rows_scored_as_v2": False,
                "case_score_count": 0,
                "case_scores": [],
                "distribution": _distribution([]),
                "review": {
                    "build67_forward_validation_allowed": False,
                    "next_action": "repair_research_schema",
                },
            }

        cases: dict[str, dict[str, Any]] = {}
        if usable_keys:
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
            for row in case_rows:
                item = dict(row)
                case_key = str(item.get("case_key") or "")
                item["coingecko_id"] = coingecko_by_case.get(case_key, "")
                cases[case_key] = item

        pre_cutoff_keys = sorted(
            key for key, case in cases.items() if float(case.get("domestic_open_at") or 0.0) < FORWARD_CUTOFF_TS
        )
        forward_keys = sorted(
            key for key, case in cases.items() if float(case.get("domestic_open_at") or 0.0) >= FORWARD_CUTOFF_TS
        )
        feature_rows_by_case: dict[str, list[dict[str, Any]]] = {key: [] for key in forward_keys}
        if forward_keys:
            placeholders = ",".join("?" for _ in forward_keys)
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
                tuple(forward_keys),
            ).fetchall()
            for row in rows:
                item = dict(row)
                item["feature"] = _json(item.pop("feature_json"))
                case_key = str(item.get("case_key") or "")
                if case_key in feature_rows_by_case:
                    feature_rows_by_case[case_key].append(item)

        scores = [
            _forward_case_score(case=cases[key], feature_rows=feature_rows_by_case.get(key, []))
            for key in forward_keys
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

    status = "scored_forward_only" if scores else "forward_waiting_no_eligible_cases"
    return {
        **base,
        "ok": True,
        "status": status,
        "preregistration_ready": True,
        "scoring_enabled_for_forward_audit": True,
        "usable_case_count_total": len(usable_keys),
        "usable_case_rows_found": len(cases),
        "pre_cutoff_design_only_case_count": len(pre_cutoff_keys),
        "forward_eligible_case_count": len(forward_keys),
        "case_score_count": len(scores),
        "all_forward_eligible_cases_scored": len(scores) == len(forward_keys),
        "historical_rows_scored_as_v2": False,
        "historical_rows_eligible_for_v2_validation": False,
        "component_weights": {name: float(spec["weight"]) for name, spec in V2_COMPONENTS.items()},
        "excluded_components": ["pre_acceleration", "launch_continuity"],
        "distribution": _distribution(score_values),
        "confidence_distribution": _distribution(confidence_values),
        "component_available_case_counts": dict(sorted(component_available.items())),
        "missing_component_case_counts": dict(sorted(missing_counter.items())),
        "evaluation_label_available_case_counts": dict(sorted(outcome_available.items())),
        "case_scores": scores,
        "review": {
            "build67_forward_validation_allowed": bool(scores),
            "paper_ab_wired": False,
            "live_promotion_allowed": False,
            "next_action": (
                "accumulate_forward_cases_for_build67_validation"
                if scores
                else "collect_post_cutoff_usable_cases_then_reaudit_build66"
            ),
        },
    }
