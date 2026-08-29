from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "b3_trader/dex_temporal_backfill.py"
VERIFY = ROOT / "scripts/verify-dex-temporal-backfill-build56.py"
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
        "build56_temporal_only": "non_dominant_verified_no_dex" in runner and "dominant_month" in runner,
        "build56_verified_identity_only": "identity_verified=1" in runner and "provider_id" in runner,
        "build56_no_existing_dex_status": "d.case_key IS NULL" in runner,
        "build56_month_cap": "per_month_case_cap_at_target" in runner and "remaining_month_capacity" in runner,
        "build56_bounded_two_cases": "MAX_CASES_PER_RUN = 2" in runner,
        "build56_cooldown": "RETRY_AFTER_SECONDS = 6 * 3600" in runner,
        "build56_supervisor_guard": "listing-history-research" in runner and "dex-launch-research" in runner,
        "build56_reuses_existing_dex_cycle": "DexLaunchResearchCycle" in runner and "_research_case" in runner,
        "build56_no_ticker_only_identity": "provider_id" in runner and "symbol" not in runner.split("identity =", 1)[-1].split("candidates.append", 1)[0],
        "build56_build45_thresholds_unchanged": "MIN_USABLE_CASES = 20" in quality and "MIN_EXACT_P5M_COVERAGE = 0.60" in quality,
        "build56_build53_thresholds_unchanged": "MIN_LAUNCH_FEATURE_COVERAGE = 0.30" in readiness and "MAX_MONTH_SHARE = 0.40" in readiness,
        "build56_pipeline_not_wired": "dex_temporal_backfill" not in pipeline,
        "build56_direct_verifier_bootstrap": "sys.path.insert" in verify and "--import-check" in verify,
        "build56_no_score_decision_order_wiring": '"can_place_orders": False' in runner and '"score_wired": False' in runner,
        "build56_no_check_same_thread_override": "check_same_thread=False" not in runner,
    }
    print("=== DEX TEMPORAL BACKFILL BUILD 56 CONTRACT ===")
    print(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_TEMPORAL_BACKFILL_BUILD56=FAIL")
    print("DEX_TEMPORAL_BACKFILL_BUILD56=PASS")


if __name__ == "__main__":
    main()
