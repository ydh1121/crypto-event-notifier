from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "b3_trader" / "dex_shadow_score_v2_forward_validation.py"
VERIFY = ROOT / "scripts" / "verify-dex-shadow-score-v2-forward-validation-build71.py"


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    verify = VERIFY.read_text(encoding="utf-8")
    readiness_guard = source.find("if not sample_size_ready:")
    first_statistics = source.find("event_metrics = _core_metrics(rows)")
    checks = {
        "build71_uses_build70_readiness_gate": (
            "audit_forward_sample_ledger" in source
            and '"sample_size_ready"' in source
            and '"build70_readiness_gate_passed"' in source
        ),
        "build71_reuses_one_build66_score_snapshot": (
            "audit_dex_shadow_score_v2_forward" in source
            and "score_audit_fn=lambda _: score" in source
        ),
        "build71_uses_frozen_build65_protocol": (
            "FORWARD_VALIDATION_PROTOCOL" in source
            and "V2_SCORE_VERSION" in source
            and "V2_SCORE_NAME" in source
        ),
        "build71_statistics_blocked_before_readiness": (
            readiness_guard >= 0
            and first_statistics >= 0
            and readiness_guard < first_statistics
            and '"validation_statistics_calculated": False' in source
            and '"statistics": None' in source
        ),
        "build71_event_and_asset_dedup_statistics": (
            '"event_level": event_metrics' in source
            and '"asset_level_dedup": asset_metrics' in source
            and "_aggregate_assets" in source
        ),
        "build71_preregistered_spearman_and_spread": (
            "_window_stats" in source
            and '"minimum_spearman_rho"' in source
            and '"primary_asset_dedup_p24h_top_minus_bottom_mean_return_pct"' in source
        ),
        "build71_chronological_late_half": (
            "_chronological_halves" in source
            and '"primary_asset_dedup_late_half_positive_rank_windows"' in source
        ),
        "build71_strong_negative_gate": (
            "_strong_negative_core_windows" in source
            and '"no_strong_negative_event_or_asset_core_rank_signal"' in source
        ),
        "build71_primary_level_asset_dedup": (
            'FORWARD_VALIDATION_PROTOCOL["primary_level"]' in source
            and '"primary_asset_dedup_positive_rank_signal"' in source
        ),
        "build71_pre_cutoff_and_identity_fail_closed": (
            '"pre_cutoff_or_missing_domestic_open"' in source
            and '"identity_incomplete"' in source
            and '"pre_cutoff_cases_validation_excluded": True' in source
        ),
        "build71_no_build47_cursor_access": (
            '"build47_historical_cursor_read": False' in source
            and '"build47_historical_cursor_mutation": False' in source
        ),
        "build71_read_only_no_network_or_cloudflare": (
            '"read_only": True' in source
            and '"network_fetches": False' in source
            and '"database_mutation": False' in source
            and '"cloudflare_publishing": False' in source
            and "INSERT INTO" not in source
            and "UPDATE dex_" not in source
            and "DELETE FROM" not in source
        ),
        "build71_no_strategy_position_or_order_mutation": (
            '"strategy_signal_mutation": False' in source
            and '"position_sizing_mutation": False' in source
            and '"order_path_mutation": False' in source
            and ".place_order(" not in source
            and " place_order(" not in source
            and ".submit_order(" not in source
            and " submit_order(" not in source
        ),
        "build71_no_fitting_or_threshold": (
            '"score_formula_changed": False' in source
            and '"score_weights_changed": False' in source
            and '"training_or_fitting": False' in source
            and '"trade_threshold": None' in source
        ),
        "build71_paper_ab_and_live_stay_unwired": (
            '"paper_ab_wired": False' in source
            and '"live_promotion_allowed": False' in source
            and '"can_place_orders": False' in source
        ),
        "build71_no_check_same_thread_override": "check_same_thread" not in source,
        "build71_runtime_verifier": "DEX_SHADOW_SCORE_V2_FORWARD_VALIDATION_BUILD71_RUNTIME=PASS" in verify,
        "build71_direct_import_bootstrap": "DEX_SHADOW_SCORE_V2_FORWARD_VALIDATION_BUILD71_IMPORT=PASS" in verify,
    }
    print("=== DEX SHADOW SCORE V2 FORWARD VALIDATION BUILD 71 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_SHADOW_SCORE_V2_FORWARD_VALIDATION_BUILD71=FAIL")
    print("DEX_SHADOW_SCORE_V2_FORWARD_VALIDATION_BUILD71=PASS")


if __name__ == "__main__":
    main()
