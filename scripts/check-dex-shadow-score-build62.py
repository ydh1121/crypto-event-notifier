from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "b3_trader" / "dex_shadow_score.py"
VERIFY = ROOT / "scripts" / "verify-dex-shadow-score-build62.py"


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    verify = VERIFY.read_text(encoding="utf-8")
    checks = {
        "build62_readiness_fail_closed": (
            "audit_dex_shadow_readiness" in source
            and '"status": "readiness_blocked"' in source
            and '"scoring_enabled_for_audit": False' in source
        ),
        "build62_paper_shadow_only": '"paper_only": True' in source and '"shadow_only": True' in source,
        "build62_no_orders": (
            '"can_place_orders": False' in source
            and ".place_order(" not in source
            and " place_order(" not in source
            and ".submit_order(" not in source
            and " submit_order(" not in source
        ),
        "build62_not_wired": '"score_wired": False' in source and '"paper_ab_wired": False' in source,
        "build62_read_only": (
            '"read_only": True' in source
            and "INSERT INTO" not in source
            and "UPDATE dex_" not in source
            and "DELETE FROM" not in source
        ),
        "build62_no_network": '"network_fetches": False' in source,
        "build62_no_strategy_mutation": '"strategy_signal_mutation": False' in source,
        "build62_no_position_sizing_mutation": '"position_sizing_mutation": False' in source,
        "build62_no_cloudflare_publish": '"cloudflare_publishing": False' in source,
        "build62_no_primary_mutation": '"selected_primary_mutation": False' in source,
        "build62_no_post_listing_score_input": (
            '"uses_post_listing_features_in_score": False' in source
            and '"excluded_from_score": True' in source
            and "evaluation_only_outcomes" in source
        ),
        "build62_unfitted_hypothesis": '"training_or_fitting": False' in source and '"unfitted_hypothesis": True' in source,
        "build62_no_trade_threshold": '"trade_threshold": None' in source and '"trade_recommendation": None' in source,
        "build62_missing_is_neutral": '"missing_components_are_neutral_zero_contribution": True' in source,
        "build62_bounded_score": "_clip(50.0 + 50.0 * signed_sum, 0.0, 100.0)" in source,
        "build62_prelisting_launch_guard": "target_ts > domestic_open_at" in source,
        "build62_no_check_same_thread_override": "check_same_thread" not in source,
        "build62_runtime_verifier": "DEX_SHADOW_SCORE_BUILD62_RUNTIME=PASS" in verify,
        "build62_direct_import_bootstrap": "DEX_SHADOW_SCORE_BUILD62_IMPORT=PASS" in verify,
    }
    print("=== DEX SHADOW SCORE BUILD 62 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_SHADOW_SCORE_BUILD62=FAIL")
    print("DEX_SHADOW_SCORE_BUILD62=PASS")


if __name__ == "__main__":
    main()
