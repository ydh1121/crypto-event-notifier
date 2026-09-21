from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "b3_trader" / "forward_sample_intake.py"
VERIFY = ROOT / "scripts" / "verify-dex-forward-sample-intake-build67.py"


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    verify = VERIFY.read_text(encoding="utf-8")
    checks = {
        "build67_fixed_forward_cutoff": (
            "FORWARD_CUTOFF_TS" in source
            and '"trade_open_at_gte_cutoff"' in source
            and '"announcement_gte_cutoff_open_time_pending"' in source
        ),
        "build67_latest_official_pages_only": (
            "BithumbHistoricalListingSource" in source
            and "UpbitHistoricalListingSource" in source
            and '"latest_pages_start_at": 1' in source
            and "for page in range(1, self.pages_per_exchange + 1)" in source
        ),
        "build67_build47_cursor_isolated": (
            "HistoricalListingBackfill(" not in source
            and "historical-listing-backfill-state.json" not in source
            and '"build47_historical_cursor_read": False' in source
            and '"build47_historical_cursor_mutation": False' in source
        ),
        "build67_bounded_pages": (
            "DEFAULT_PAGES_PER_EXCHANGE = 2" in source
            and "MAX_PAGES_PER_EXCHANGE = 3" in source
        ),
        "build67_krw_listing_filter": "is_krw_listing_notice" in source,
        "build67_seed_pending_identity_only": (
            'status="pending_identity"' in source
            and "ListingIdentityResolver" not in source
            and "listing_identity_resolver" not in source
        ),
        "build67_no_dex_fetch": (
            "DexLaunchResearchCycle" not in source
            and "GeckoTerminal" not in source
            and '"dex_fetch_calls": 0' in source
        ),
        "build67_no_score_calculation": (
            "audit_dex_shadow_score_v2_forward" not in source
            and '"score_calculations": 0' in source
            and '"score_wired": False' in source
        ),
        "build67_paper_shadow_only": (
            '"paper_only": True' in source
            and '"shadow_only": True' in source
            and '"can_place_orders": False' in source
        ),
        "build67_no_strategy_position_cloudflare_mutation": (
            '"strategy_signal_mutation": False' in source
            and '"position_sizing_mutation": False' in source
            and '"cloudflare_publishing": False' in source
        ),
        "build67_separate_state": "forward-sample-intake-build67-state.json" in source,
        "build67_no_order_calls": (
            ".place_order(" not in source
            and " place_order(" not in source
            and ".submit_order(" not in source
            and " submit_order(" not in source
        ),
        "build67_no_check_same_thread_override": "check_same_thread" not in source,
        "build67_runtime_verifier": "DEX_FORWARD_SAMPLE_INTAKE_BUILD67_RUNTIME=PASS" in verify,
        "build67_direct_import_bootstrap": "DEX_FORWARD_SAMPLE_INTAKE_BUILD67_IMPORT=PASS" in verify,
    }
    print("=== DEX FORWARD SAMPLE INTAKE BUILD 67 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_FORWARD_SAMPLE_INTAKE_BUILD67=FAIL")
    print("DEX_FORWARD_SAMPLE_INTAKE_BUILD67=PASS")


if __name__ == "__main__":
    main()
