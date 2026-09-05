from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "b3_trader/dex_temporal_diversity_backfill.py"
VERIFY = ROOT / "scripts/verify-dex-temporal-diversity-build57.py"
QUALITY = ROOT / "b3_trader/dex_launch_quality.py"
READINESS = ROOT / "b3_trader/dex_shadow_readiness_audit.py"
PIPELINE = ROOT / "b3_trader/research_pipeline_accelerator.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    runner = _text(RUNNER)
    verify = _text(VERIFY)
    quality = _text(QUALITY)
    readiness = _text(READINESS)
    pipeline = _text(PIPELINE)
    ast.parse(runner)
    ast.parse(verify)

    checks = {
        "build57_verified_coingecko_only": 'provider != "coingecko"' in runner and "provider_id" in runner,
        "build57_new_unique_only": "provider_id in usable_ids" in runner and "new_unique_asset_only" in runner,
        "build57_one_event_per_provider_id": "scheduled_ids" in runner and "one_event_per_provider_id" in runner,
        "build57_june_or_earlier_primary": 'PRIMARY_HISTORY_CUTOFF_MONTH = "2026-07"' in runner and "month < PRIMARY_HISTORY_CUTOFF_MONTH" in runner,
        "build57_july_not_executed": 'FALLBACK_MONTH = "2026-07"' in runner and '"july_fallback_execution_enabled": False' in runner,
        "build57_dominant_month_excluded": "dominant_month" in runner and 'month in {"unknown", dominant_month}' in runner,
        "build57_no_existing_dex_status": "d.case_key IS NULL" in runner,
        "build57_bounded_two_cases": "MAX_CASES_PER_RUN = 2" in runner,
        "build57_cooldown": "RETRY_AFTER_SECONDS = 6 * 3600" in runner,
        "build57_supervisor_guard": "listing-history-research" in runner and "dex-launch-research" in runner,
        "build57_reuses_existing_dex_cycle": "DexLaunchResearchCycle" in runner and "_research_case" in runner,
        "build57_build45_thresholds_unchanged": "MIN_USABLE_CASES = 20" in quality and "MIN_EXACT_P5M_COVERAGE = 0.60" in quality,
        "build57_build53_thresholds_unchanged": "MIN_LAUNCH_FEATURE_COVERAGE = 0.30" in readiness and "MAX_MONTH_SHARE = 0.40" in readiness,
        "build57_pipeline_not_wired": "dex_temporal_diversity_backfill" not in pipeline,
        "build57_direct_verifier_bootstrap": "sys.path.insert" in verify and "--import-check" in verify,
        "build57_no_score_decision_order_wiring": '"can_place_orders": False' in runner and '"score_wired": False' in runner,
        "build57_no_check_same_thread_override": "check_same_thread=False" not in runner,
    }
    print("=== DEX TEMPORAL DIVERSITY BUILD 57 CONTRACT ===")
    print(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_TEMPORAL_DIVERSITY_BUILD57=FAIL")
    print("DEX_TEMPORAL_DIVERSITY_BUILD57=PASS")


if __name__ == "__main__":
    main()
