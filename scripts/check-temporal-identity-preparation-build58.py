from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "b3_trader/temporal_identity_preparation.py"
VERIFY = ROOT / "scripts/verify-temporal-identity-preparation-build58.py"
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
        "build58_pre_july_only": 'PRIMARY_MONTH_BEFORE = "2026-07"' in runner and "month < PRIMARY_MONTH_BEFORE" in runner,
        "build58_unverified_listing_only": "c.identity_verified=0" in runner,
        "build58_no_existing_dex_status": "d.case_key IS NULL" in runner,
        "build58_existing_identity_resolver": "ListingIdentityResolver" in runner and ".resolve(exchange, market)" in runner,
        "build58_verified_coingecko_only_on_write": 'identity.provider == "coingecko"' in runner and "identity.provider_id" in runner,
        "build58_identity_gate": "listing_identity_gate(identity)" in runner,
        "build58_no_ticker_only_matching": "resolver.resolve(exchange, market)" in runner and "symbol ==" not in runner,
        "build58_preserves_existing_case_fields": "domestic_notice_id=str(current.get" in runner and "status=str(current.get" in runner,
        "build58_bounded_two_cases": "MAX_CASES_PER_RUN = 2" in runner,
        "build58_cooldown": "RETRY_AFTER_SECONDS = 6 * 3600" in runner,
        "build58_supervisor_guard": "listing-history-research" in runner and "dex-launch-research" in runner,
        "build58_no_dex_research": "DexLaunchResearchCycle" not in runner and '"dex_research": False' in runner,
        "build58_build45_thresholds_unchanged": "MIN_USABLE_CASES = 20" in quality and "MIN_EXACT_P5M_COVERAGE = 0.60" in quality,
        "build58_build53_thresholds_unchanged": "MIN_LAUNCH_FEATURE_COVERAGE = 0.30" in readiness and "MAX_MONTH_SHARE = 0.40" in readiness,
        "build58_pipeline_not_wired": "temporal_identity_preparation" not in pipeline,
        "build58_direct_verifier_bootstrap": "sys.path.insert" in verify and "--import-check" in verify,
        "build58_no_score_decision_order_wiring": '"can_place_orders": False' in runner and '"score_wired": False' in runner,
        "build58_no_check_same_thread_override": "check_same_thread=False" not in runner,
    }
    print("=== TEMPORAL IDENTITY PREPARATION BUILD 58 CONTRACT ===")
    print(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise SystemExit("TEMPORAL_IDENTITY_PREPARATION_BUILD58=FAIL")
    print("TEMPORAL_IDENTITY_PREPARATION_BUILD58=PASS")


if __name__ == "__main__":
    main()
