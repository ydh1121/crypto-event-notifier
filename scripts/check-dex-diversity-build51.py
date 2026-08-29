from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIVERSITY = ROOT / "b3_trader/dex_diversity_backfill.py"
BACKFILL = ROOT / "b3_trader/dex_launch_backfill.py"
QUALITY = ROOT / "b3_trader/dex_launch_quality.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    diversity = _text(DIVERSITY)
    backfill = _text(BACKFILL)
    quality = _text(QUALITY)
    checks = {
        "build51_additive_diversity_runner": "class DexDiversityBackfillRunner(DexLaunchBackfillRunner)" in diversity,
        "build51_reuses_build46_execution": "super().run_once(max_cases=max_cases)" in diversity,
        "build51_new_unique_first": "PRIORITY_NEW_UNIQUE = 0" in diversity and "new_unique_asset" in diversity,
        "build51_duplicate_after_unique": "PRIORITY_DUPLICATE_EVENT = 2" in diversity and "duplicate_asset_event" in diversity,
        "build51_partial_retry_last": "PRIORITY_PARTIAL_RETRY = 3" in diversity and "partial_completion_retry" in diversity,
        "build51_resolves_verified_listing_identity": "_verified_listing_coingecko_id" in diversity,
        "build51_sample_ready_stop": "sample_ready_stop" in diversity,
        "build51_build46_budget_preserved": "MAX_CASES_PER_RUN = 2" in backfill and "MAX_CASES_PER_RUN" in diversity,
        "build51_build46_cooldown_preserved": "BACKFILL_RETRY_AFTER_SECONDS = 6 * 3600" in backfill,
        "build51_build45_thresholds_unchanged": "MIN_USABLE_CASES = 20" in quality and "MIN_EXACT_P5M_COVERAGE = 0.60" in quality,
        "build51_no_score_decision_order_wiring": (
            '"can_place_orders": False' in diversity
            and '"score_wired": False' in diversity
            and "place_order(" not in diversity
            and ".place_order(" not in diversity
        ),
    }
    print("=== DEX DIVERSITY BUILD 51 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_DIVERSITY_BUILD51=FAIL")
    print("DEX_DIVERSITY_BUILD51=PASS")


if __name__ == "__main__":
    main()
