from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "b3_trader" / "forward_sample_enrichment.py").read_text(encoding="utf-8")
VERIFIER = (ROOT / "scripts" / "verify-dex-forward-sample-enrichment-build68.py").read_text(encoding="utf-8")


def main() -> None:
    checks = {
        "build68_fixed_forward_cutoff": "FORWARD_CUTOFF_TS" in SOURCE,
        "build68_forward_case_filter": "domestic_open_at>=?" in SOURCE and "announcement_at>=?" in SOURCE,
        "build68_hard_max_one_case": "HARD_MAX_CASES_PER_RUN = 1" in SOURCE,
        "build68_reuses_existing_owners": "ListingHistoryResearchCycle" in SOURCE and "DexLaunchResearchCycle" in SOURCE,
        "build68_does_not_call_generic_run_once": "listing_cycle.run_once(" not in SOURCE and "dex_cycle.run_once(" not in SOURCE,
        "build68_no_v2_score_calculation": "_forward_case_score" not in SOURCE and "audit_dex_shadow_score_v2_forward" not in SOURCE,
        "build68_no_paper_ab_or_live_wiring": "\"paper_ab_wired\": False" in SOURCE and "\"score_wired\": False" in SOURCE,
        "build68_no_orders": ".place_order(" not in SOURCE and "place_order(" not in SOURCE,
        "build68_no_cloudflare_publish": "\"cloudflare_publishing\": False" in SOURCE,
        "build68_retry_cooldown": "RETRY_AFTER_SECONDS = 6 * 3600" in SOURCE,
        "build68_build47_cursor_isolated": "\"build47_historical_cursor_read\": False" in SOURCE and "\"build47_historical_cursor_mutation\": False" in SOURCE,
        "build68_no_check_same_thread_override": "check_same_thread" not in SOURCE,
        "build68_runtime_verifier": "DEX_FORWARD_SAMPLE_ENRICHMENT_BUILD68_RUNTIME=PASS" in VERIFIER,
        "build68_direct_import_bootstrap": "DEX_FORWARD_SAMPLE_ENRICHMENT_BUILD68_IMPORT=PASS" in VERIFIER,
    }
    print("=== DEX FORWARD SAMPLE ENRICHMENT BUILD 68 CONTRACT ===")
    import json
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_FORWARD_SAMPLE_ENRICHMENT_BUILD68=FAIL")
    print("DEX_FORWARD_SAMPLE_ENRICHMENT_BUILD68=PASS")


if __name__ == "__main__":
    main()
