from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "b3_trader/dex_shadow_remediation_runner.py"
VERIFY = ROOT / "scripts/verify-dex-shadow-remediation-runner-build55.py"
QUALITY = ROOT / "b3_trader/dex_launch_quality.py"
DIVERSITY = ROOT / "b3_trader/dex_diversity_backfill.py"
READINESS = ROOT / "b3_trader/dex_shadow_readiness_audit.py"
REMEDIATION = ROOT / "b3_trader/dex_shadow_remediation_plan.py"
PIPELINE = ROOT / "b3_trader/research_pipeline_accelerator.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    runner = _text(RUNNER)
    verify = _text(VERIFY)
    quality = _text(QUALITY)
    diversity = _text(DIVERSITY)
    readiness = _text(READINESS)
    remediation = _text(REMEDIATION)
    pipeline = _text(PIPELINE)
    ast.parse(runner)
    ast.parse(verify)

    checks = {
        "build55_bounded_launch_recovery": "MAX_LAUNCH_RECOVERY_CASES = 2" in runner and "max_launch_cases" in runner,
        "build55_launch_cooldown": "LAUNCH_RETRY_AFTER_SECONDS = 6 * 3600" in runner and "launch_attempted_at" in runner,
        "build55_selected_primary_only": "p.selected_primary=1" in runner,
        "build55_case_level_missing_only": 'if any(_launch_collected(feature) for _, feature in parsed_rows):' in runner and '"case_level_missing_only": True' in runner,
        "build55_shared_source_fetch_reuse": "source_cache" in runner and '"shared_source_fetch_reuse": True' in runner and '"distinct_launch_source_fetches"' in runner,
        "build55_preserves_domestic_feature": 'feature["pool_launch_window"] = launch' in runner and "launch_window_features" in runner,
        "build55_reuses_build47_official_history": "HistoricalListingBackfill" in runner and "official_sources_only" in runner,
        "build55_one_history_page_per_exchange": "HISTORICAL_PAGES_PER_EXCHANGE = 1" in runner,
        "build55_supervisor_guard": "listing-history-research" in runner and "dex-launch-research" in runner and "supervisor_busy" in runner,
        "build55_no_check_same_thread_override": "check_same_thread=False" not in runner,
        "build55_build45_thresholds_unchanged": "MIN_USABLE_CASES = 20" in quality and "MIN_EXACT_P5M_COVERAGE = 0.60" in quality,
        "build55_build51_policy_unchanged": "new_unique_asset" in diversity and "partial_completion_retry" in diversity,
        "build55_build53_thresholds_unchanged": "MIN_LAUNCH_FEATURE_COVERAGE = 0.30" in readiness and "MAX_MONTH_SHARE = 0.40" in readiness,
        "build55_build54_plan_unchanged": "historical_expansion_plus_launch_recovery" in remediation,
        "build55_pipeline_not_wired": "dex_shadow_remediation_runner" not in pipeline,
        "build55_direct_verifier_bootstrap": "sys.path.insert" in verify and "--import-check" in verify,
        "build55_no_score_decision_order_wiring": '"can_place_orders": False' in runner and '"score_wired": False' in runner,
    }
    print("=== DEX SHADOW REMEDIATION RUNNER BUILD 55 CONTRACT ===")
    print(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_SHADOW_REMEDIATION_RUNNER_BUILD55=FAIL")
    print("DEX_SHADOW_REMEDIATION_RUNNER_BUILD55=PASS")


if __name__ == "__main__":
    main()
