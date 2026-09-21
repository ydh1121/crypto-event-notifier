from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
backfill = (ROOT / "b3_trader/dex_launch_backfill.py").read_text(encoding="utf-8")
quality = (ROOT / "b3_trader/dex_launch_quality.py").read_text(encoding="utf-8")
cycle = (ROOT / "b3_trader/dex_launch_research_cycle.py").read_text(encoding="utf-8")

checks = {
    "build46_additive_backfill_runner": "class DexLaunchBackfillRunner" in backfill,
    "build46_bounded_default_one_cap_two": (
        "DEFAULT_MAX_CASES_PER_RUN = 1" in backfill and "MAX_CASES_PER_RUN = 2" in backfill
    ),
    "build46_reuses_exact_contract_cycle": "self.cycle._research_case(listing, time.time())" in backfill,
    "build46_prioritizes_normal_retryable": "eligible_unresearched_or_retryable" in backfill,
    "build46_retries_complete_partial": "complete_partial_retry" in backfill,
    "build46_preserves_stored_complete": "stored_complete_preserved" in backfill and "_restore_complete" in backfill,
    "build46_avoids_supervisor_overlap": "supervisor_busy" in backfill and "dex-launch-research" in backfill,
    "build46_retry_cooldown": "BACKFILL_RETRY_AFTER_SECONDS = 6 * 3600" in backfill,
    "build46_quality_thresholds_unchanged": (
        "MIN_USABLE_CASES = 20" in quality and "MIN_EXACT_P5M_COVERAGE = 0.60" in quality
    ),
    "build46_existing_collection_limit_unchanged": "MAX_CASES_PER_RUN = 1" in cycle,
    "build46_no_score_decision_order_wiring": (
        "can_place_orders\": False" in backfill
        and "score_wired\": False" in backfill
        and "place_order(" not in backfill
        and ".place_order(" not in backfill
    ),
}

print("=== DEX BACKFILL BUILD 46 CONTRACT ===")
print(json.dumps(checks, ensure_ascii=False, indent=2))
if not all(checks.values()):
    raise SystemExit("DEX_BACKFILL_BUILD46=FAIL")
print("DEX_BACKFILL_BUILD46=PASS")
