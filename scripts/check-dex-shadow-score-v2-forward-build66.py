from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "b3_trader" / "dex_shadow_score_v2_forward.py"
VERIFY = ROOT / "scripts" / "verify-dex-shadow-score-v2-forward-build66.py"


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    verify = VERIFY.read_text(encoding="utf-8")
    checks = {
        "build66_requires_build65_preregistration": (
            "declare_dex_shadow_score_v2_preregistration" in source
            and '"preregistration_blocked"' in source
            and '"preregistration_ready": False' in source
        ),
        "build66_fixed_forward_cutoff": (
            "FORWARD_CUTOFF_TS" in source
            and '"eligibility_rule": "domestic_open_at_gte_forward_cutoff"' in source
            and 'raise ValueError("build66_refuses_pre_cutoff_case")' in source
        ),
        "build66_pre_cutoff_never_scored": (
            '"pre_cutoff_cases_design_only": True' in source
            and '"pre_cutoff_cases_validation_excluded": True' in source
            and '"historical_rows_scored_as_v2": False' in source
            and '"historical_rows_eligible_for_v2_validation": False' in source
        ),
        "build66_uses_only_preregistered_v2_components": (
            '"pre_short_exhaustion"' in source
            and '"pre_medium_exhaustion"' in source
            and '"excluded_components": ["pre_acceleration", "launch_continuity"]' in source
            and "transformed_signal = -clipped_source" in source
        ),
        "build66_no_whole_v1_score_inversion": (
            "audit_dex_shadow_scores" not in source
            and "from .dex_shadow_score import _case_score" not in source
            and "100.0 -" not in source
        ),
        "build66_postlisting_labels_evaluation_only": (
            '"post_listing_inputs_used_in_score": False' in source
            and '"evaluation_only_outcomes"' in source
            and '"excluded_from_score": True' in source
        ),
        "build66_read_only": (
            '"read_only": True' in source
            and '"database_mutation": False' in source
            and "INSERT INTO" not in source
            and "UPDATE dex_" not in source
            and "DELETE FROM" not in source
        ),
        "build66_no_network_or_cloudflare": (
            '"network_fetches": False' in source
            and '"cloudflare_publishing": False' in source
        ),
        "build66_no_strategy_order_or_position_mutation": (
            '"strategy_signal_mutation": False' in source
            and '"order_path_mutation": False' in source
            and '"position_sizing_mutation": False' in source
            and '"selected_primary_mutation": False' in source
        ),
        "build66_no_fitting_or_trade_threshold": (
            '"training_or_fitting": False' in source
            and '"trade_threshold": None' in source
        ),
        "build66_no_paper_ab_or_live_promotion": (
            '"paper_ab_wired": False' in source
            and '"live_promotion_allowed": False' in source
            and '"can_place_orders": False' in source
        ),
        "build66_wait_state_supported": '"forward_waiting_no_eligible_cases"' in source,
        "build66_no_order_calls": (
            ".place_order(" not in source
            and " place_order(" not in source
            and ".submit_order(" not in source
            and " submit_order(" not in source
        ),
        "build66_no_check_same_thread_override": "check_same_thread" not in source,
        "build66_runtime_verifier": "DEX_SHADOW_SCORE_V2_FORWARD_BUILD66_RUNTIME=PASS" in verify,
        "build66_direct_import_bootstrap": "DEX_SHADOW_SCORE_V2_FORWARD_BUILD66_IMPORT=PASS" in verify,
    }
    print("=== DEX SHADOW SCORE V2 FORWARD BUILD 66 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_SHADOW_SCORE_V2_FORWARD_BUILD66=FAIL")
    print("DEX_SHADOW_SCORE_V2_FORWARD_BUILD66=PASS")


if __name__ == "__main__":
    main()
