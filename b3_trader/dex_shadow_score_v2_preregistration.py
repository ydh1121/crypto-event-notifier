from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .auto_demo_v2 import DB_PATH
from .dex_shadow_score_failure_diagnostic import audit_dex_shadow_score_failure_diagnostic


PREREGISTRATION_VERSION = 1
PREREGISTRATION_NAME = "dex_shadow_score_v2_preregistration_v1"
V1_SCORE_VERSION = 1
V1_SCORE_NAME = "dex_prelisting_shadow_hypothesis_v1"
V2_SCORE_VERSION = 2
V2_SCORE_NAME = "dex_prelisting_exhaustion_shadow_hypothesis_v2"
FORWARD_CUTOFF_UTC = "2026-08-31T00:00:00Z"
FORWARD_CUTOFF_TS = datetime(2026, 8, 31, 0, 0, 0, tzinfo=timezone.utc).timestamp()
CORE_WINDOWS = ("p1h", "p6h", "p24h")

V2_COMPONENTS = {
    "pre_short_exhaustion": {
        "weight": 0.60,
        "source_component": "pre_short_momentum",
        "transform": "negative_of_clipped_pre_short_momentum",
        "direction": "higher_v2_component_means_less_prelisting_exhaustion_risk",
    },
    "pre_medium_exhaustion": {
        "weight": 0.40,
        "source_component": "pre_medium_momentum",
        "transform": "negative_of_clipped_pre_medium_momentum",
        "direction": "higher_v2_component_means_less_prelisting_exhaustion_risk",
    },
}

V2_EXCLUDED_COMPONENTS = {
    "pre_acceleration": "build64_temporal_direction_instability; excluded_from_v2_score",
    "launch_continuity": "build64_mixed_or_weak_direction; excluded_from_v2_score",
}

FORWARD_VALIDATION_PROTOCOL = {
    "core_windows": list(CORE_WINDOWS),
    "primary_level": "asset_dedup",
    "minimum_event_labels_per_core": 30,
    "minimum_asset_labels_per_core": 20,
    "minimum_positive_rank_windows": 2,
    "minimum_spearman_rho": 0.10,
    "strong_negative_spearman_rho": -0.20,
    "require_positive_p24h_top_bottom_spread": True,
    "require_late_half_positive_rank_window": True,
    "require_no_strong_negative_core_rank_signal": True,
    "trade_threshold_selection_before_forward_pass": False,
    "paper_ab_before_forward_pass": False,
    "live_promotion_before_forward_pass": False,
}

DiagnosticFn = Callable[[Path | str], dict[str, Any]]


def declare_dex_shadow_score_v2_preregistration(
    path: Path | str = DB_PATH,
    *,
    diagnostic_fn: DiagnosticFn = audit_dex_shadow_score_failure_diagnostic,
) -> dict[str, Any]:
    """Retire Build62 v1 and declare a forward-only v2 hypothesis.

    Build64 retrospective evidence is allowed only as design motivation. No
    historical case is scored or counted as v2 validation here. The v2 formula,
    component directions, weights, cutoff, and validation protocol are frozen
    before any Build66 forward scorer is implemented.
    """

    diagnostic = diagnostic_fn(Path(path))
    v1_reject_ready = bool(
        diagnostic.get("ok")
        and diagnostic.get("status") == "diagnosed_read_only"
        and diagnostic.get("score_version") == V1_SCORE_VERSION
        and diagnostic.get("score_name") == V1_SCORE_NAME
        and (diagnostic.get("diagnostic_protocol") or {}).get("v1_reject_advisory")
        and (diagnostic.get("review") or {}).get("v2_design_allowed")
    )

    base = {
        "ok": False,
        "status": "v1_retirement_blocked",
        "preregistration_version": PREREGISTRATION_VERSION,
        "preregistration_name": PREREGISTRATION_NAME,
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
        "training_or_fitting": False,
        "trade_threshold": None,
        "v2_score_wired": False,
        "forward_scorer_implemented": False,
        "historical_rows_scored_as_v2": False,
        "historical_rows_eligible_for_v2_validation": False,
        "retrospective_validation_claimed": False,
        "retrospective_design_motivation_only": True,
        "mechanical_whole_score_inversion": False,
    }
    if not v1_reject_ready:
        return {
            **base,
            "v1": {
                "score_version": V1_SCORE_VERSION,
                "score_name": V1_SCORE_NAME,
                "retired": False,
                "retirement_reason": "build64_v1_reject_advisory_not_ready",
            },
            "review": {
                "next_action": "repair_or_complete_build64_before_v2_preregistration",
                "build66_forward_scorer_allowed": False,
            },
        }

    return {
        **base,
        "ok": True,
        "status": "v2_preregistered_forward_only",
        "v1": {
            "score_version": V1_SCORE_VERSION,
            "score_name": V1_SCORE_NAME,
            "retired": True,
            "retirement_reason": "build63_validation_failed_and_build64_v1_reject_advisory",
            "may_be_reactivated_without_new_hypothesis": False,
        },
        "v2": {
            "score_version": V2_SCORE_VERSION,
            "score_name": V2_SCORE_NAME,
            "hypothesis": "prelisting_positive_momentum_can_encode_exhaustion_risk_before_domestic_listing",
            "score_semantics": {
                "base": 50.0,
                "range": [0.0, 100.0],
                "higher_score_means": "less_prelisting_exhaustion_under_preregistered_v2_hypothesis",
                "missing_components": "neutral_zero_contribution",
                "confidence": "available_component_weight",
            },
            "components": V2_COMPONENTS,
            "excluded_components": V2_EXCLUDED_COMPONENTS,
            "weights_sum": round(sum(float(spec["weight"]) for spec in V2_COMPONENTS.values()), 6),
            "weights_frozen_before_forward_scoring": True,
            "directions_frozen_before_forward_scoring": True,
            "formula_frozen_before_forward_scoring": True,
        },
        "forward_boundary": {
            "cutoff_utc": FORWARD_CUTOFF_UTC,
            "cutoff_unix": FORWARD_CUTOFF_TS,
            "eligibility_rule": "domestic_open_at_gte_forward_cutoff",
            "all_pre_cutoff_cases_design_only": True,
            "all_pre_cutoff_cases_validation_excluded": True,
        },
        "forward_validation_protocol": FORWARD_VALIDATION_PROTOCOL,
        "build64_design_motivation": {
            "contrarian_components": list((diagnostic.get("diagnostic_protocol") or {}).get("retrospective_contrarian_components") or []),
            "continuation_components": list((diagnostic.get("diagnostic_protocol") or {}).get("retrospective_continuation_components") or []),
            "v1_sign_flip_is_not_validated_v2": bool((diagnostic.get("diagnostic_protocol") or {}).get("v1_sign_flip_is_not_validated_v2")),
            "used_as_validation": False,
        },
        "review": {
            "build66_forward_scorer_allowed": True,
            "paper_ab_wired": False,
            "live_promotion_allowed": False,
            "next_action": "implement_build66_forward_only_v2_shadow_scorer_without_backscoring_pre_cutoff_cases",
        },
    }
