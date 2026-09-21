from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "b3_trader" / "dex_shadow_score_validation.py"
VERIFY = ROOT / "scripts" / "verify-dex-shadow-score-validation-build63.py"


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    verify = VERIFY.read_text(encoding="utf-8")
    checks = {
        "build63_build62_frozen_input": (
            "audit_dex_shadow_scores" in source
            and '"score_formula_changed": False' in source
            and '"score_weights_changed": False' in source
        ),
        "build63_postlisting_evaluation_only": '"post_listing_outcomes_used_for_evaluation_only": True' in source,
        "build63_no_fitting": '"training_or_fitting": False' in source,
        "build63_no_trade_threshold": '"trade_threshold": None' in source,
        "build63_event_and_asset_dedup": (
            '"event_level": event_metrics' in source
            and '"asset_level_dedup": asset_metrics' in source
            and "_aggregate_assets" in source
        ),
        "build63_chronological_sensitivity": '"chronological_halves"' in source and "_chronological_halves" in source,
        "build63_exchange_sensitivity": '"exchange_sensitivity": exchange_metrics' in source,
        "build63_confidence_sensitivity": '"confidence_sensitivity": confidence_metrics' in source,
        "build63_launch_sensitivity": '"launch_availability_sensitivity": launch_metrics' in source,
        "build63_fixed_protocol": (
            'CORE_WINDOWS = ("p1h", "p6h", "p24h")' in source
            and "MIN_EVENT_LABELS_PER_CORE = 30" in source
            and "MIN_ASSET_LABELS_PER_CORE = 20" in source
            and "MIN_RHO = 0.10" in source
            and "STRONG_NEGATIVE_RHO = -0.20" in source
        ),
        "build63_forward_validation_required": (
            '"forward_validation_required": True' in source
            and '"promotion_to_live_blocked": True' in source
            and '"live_promotion_allowed": False' in source
        ),
        "build63_paper_shadow_only": '"paper_only": True' in source and '"shadow_only": True' in source,
        "build63_no_orders": (
            '"can_place_orders": False' in source
            and ".place_order(" not in source
            and " place_order(" not in source
            and ".submit_order(" not in source
            and " submit_order(" not in source
        ),
        "build63_not_wired": '"paper_ab_wired": False' in source,
        "build63_read_only": (
            '"read_only": True' in source
            and '"database_mutation": False' in source
            and "INSERT INTO" not in source
            and "UPDATE dex_" not in source
            and "DELETE FROM" not in source
        ),
        "build63_no_network": '"network_fetches": False' in source,
        "build63_no_cloudflare": '"cloudflare_publishing": False' in source,
        "build63_no_strategy_mutation": '"strategy_signal_mutation": False' in source,
        "build63_no_position_sizing_mutation": '"position_sizing_mutation": False' in source,
        "build63_retrospective_caveat": '"retrospective_source_selection_caveat"' in source,
        "build63_no_check_same_thread_override": "check_same_thread" not in source,
        "build63_runtime_verifier": "DEX_SHADOW_SCORE_VALIDATION_BUILD63_RUNTIME=PASS" in verify,
        "build63_direct_import_bootstrap": "DEX_SHADOW_SCORE_VALIDATION_BUILD63_IMPORT=PASS" in verify,
    }
    print("=== DEX SHADOW SCORE VALIDATION BUILD 63 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_SHADOW_SCORE_VALIDATION_BUILD63=FAIL")
    print("DEX_SHADOW_SCORE_VALIDATION_BUILD63=PASS")


if __name__ == "__main__":
    main()
