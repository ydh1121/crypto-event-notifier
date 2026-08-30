from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "b3_trader" / "dex_shadow_score_v2_preregistration.py"
VERIFY = ROOT / "scripts" / "verify-dex-shadow-score-v2-preregistration-build65.py"


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    verify = VERIFY.read_text(encoding="utf-8")
    checks = {
        "build65_v1_retirement_fail_closed": (
            "audit_dex_shadow_score_failure_diagnostic" in source
            and '"v1_retirement_blocked"' in source
            and '"retired": False' in source
        ),
        "build65_v2_preregistered_before_forward_scorer": (
            '"v2_preregistered_forward_only"' in source
            and '"forward_scorer_implemented": False' in source
            and '"v2_score_wired": False' in source
        ),
        "build65_fixed_forward_cutoff": 'FORWARD_CUTOFF_UTC = "2026-08-31T00:00:00Z"' in source,
        "build65_pre_cutoff_validation_excluded": (
            '"all_pre_cutoff_cases_validation_excluded": True' in source
            and '"historical_rows_eligible_for_v2_validation": False' in source
            and '"historical_rows_scored_as_v2": False' in source
        ),
        "build65_fixed_v2_components": (
            '"pre_short_exhaustion"' in source
            and '"weight": 0.60' in source
            and '"pre_medium_exhaustion"' in source
            and '"weight": 0.40' in source
        ),
        "build65_unstable_components_excluded": (
            '"pre_acceleration": "build64_temporal_direction_instability; excluded_from_v2_score"' in source
            and '"launch_continuity": "build64_mixed_or_weak_direction; excluded_from_v2_score"' in source
        ),
        "build65_no_retrospective_validation_claim": (
            '"retrospective_validation_claimed": False' in source
            and '"retrospective_design_motivation_only": True' in source
            and '"used_as_validation": False' in source
        ),
        "build65_not_whole_score_inversion": '"mechanical_whole_score_inversion": False' in source,
        "build65_forward_validation_protocol_frozen": (
            '"minimum_event_labels_per_core": 30' in source
            and '"minimum_asset_labels_per_core": 20' in source
            and '"minimum_positive_rank_windows": 2' in source
            and '"minimum_spearman_rho": 0.10' in source
            and '"strong_negative_spearman_rho": -0.20' in source
        ),
        "build65_no_paper_ab_or_live_promotion": (
            '"paper_ab_wired": False' in source
            and '"live_promotion_allowed": False' in source
            and '"can_place_orders": False' in source
        ),
        "build65_read_only": (
            '"read_only": True' in source
            and '"database_mutation": False' in source
            and "INSERT INTO" not in source
            and "UPDATE dex_" not in source
            and "DELETE FROM" not in source
        ),
        "build65_no_network_or_cloudflare": (
            '"network_fetches": False' in source
            and '"cloudflare_publishing": False' in source
        ),
        "build65_no_strategy_or_position_mutation": (
            '"strategy_signal_mutation": False' in source
            and '"position_sizing_mutation": False' in source
        ),
        "build65_no_fitting_or_trade_threshold": (
            '"training_or_fitting": False' in source
            and '"trade_threshold": None' in source
        ),
        "build65_no_order_calls": (
            ".place_order(" not in source
            and " place_order(" not in source
            and ".submit_order(" not in source
            and " submit_order(" not in source
        ),
        "build65_no_check_same_thread_override": "check_same_thread" not in source,
        "build65_runtime_verifier": "DEX_SHADOW_SCORE_V2_PREREGISTRATION_BUILD65_RUNTIME=PASS" in verify,
        "build65_direct_import_bootstrap": "DEX_SHADOW_SCORE_V2_PREREGISTRATION_BUILD65_IMPORT=PASS" in verify,
    }
    print("=== DEX SHADOW SCORE V2 PREREGISTRATION BUILD 65 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_SHADOW_SCORE_V2_PREREGISTRATION_BUILD65=FAIL")
    print("DEX_SHADOW_SCORE_V2_PREREGISTRATION_BUILD65=PASS")


if __name__ == "__main__":
    main()
