from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    module = _text("b3_trader/research_pipeline_accelerator.py")
    verifier = _text("scripts/verify-research-pipeline-build49.py")
    listing_accel = _text("b3_trader/listing_history_accelerator.py")
    dex_backfill = _text("b3_trader/dex_launch_backfill.py")
    supervisor = _text("b3_trader/research_supervisor.py")
    quality = _text("b3_trader/dex_launch_quality.py")

    checks = {
        "build49_additive_pipeline_accelerator": "class ResearchPipelineAccelerator" in module,
        "build49_backlog_aware_dex_first": "DEX_BACKLOG_SKIP_LISTING_THRESHOLD = 2" in module and 'action = "dex_backfill_only"' in module,
        "build49_listing_only_when_needed": 'action = "listing_then_dex"' in module,
        "build49_reuses_build48_listing_accelerator": "ListingHistoryAccelerator" in module,
        "build49_reuses_build46_dex_backfill": "DexLaunchBackfillRunner" in module,
        "build49_listing_budget_bounded": "MAX_LISTING_CYCLES = 2" in module,
        "build49_dex_budget_preserved": "MAX_DEX_CASES = MAX_CASES_PER_RUN" in module and "MAX_CASES_PER_RUN = 2" in dex_backfill,
        "build49_both_supervisor_guards": '"listing-history-research"' in module and '"dex-launch-research"' in module,
        "build49_sample_ready_fail_closed": 'action = "sample_ready_stop"' in module,
        "build49_existing_listing_limits_unchanged": "MAX_CYCLES_PER_RUN = 4" in listing_accel and "INTER_CYCLE_SECONDS = 15.0" in listing_accel,
        "build49_quality_thresholds_unchanged": "MIN_USABLE_CASES = 20" in quality and "MIN_EXACT_P5M_COVERAGE = 0.60" in quality,
        "build49_no_supervisor_wiring": "ResearchPipelineAccelerator" not in supervisor,
        "build49_direct_verifier_bootstrap": "sys.path.insert" in verifier and "--import-check" in verifier,
        "build49_no_score_decision_order_wiring": '"can_place_orders": False' in module and '"score_wired": False' in module and ".place_order(" not in module,
    }
    print("=== RESEARCH PIPELINE BUILD 49 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("RESEARCH_PIPELINE_BUILD49=FAIL")
    print("RESEARCH_PIPELINE_BUILD49=PASS")


if __name__ == "__main__":
    main()
