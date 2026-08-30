from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIORITY = ROOT / "b3_trader/dex_launch_recovery_priority.py"
RUNNER = ROOT / "b3_trader/dex_shadow_remediation_runner.py"
VERIFY = ROOT / "scripts/verify-dex-launch-recovery-priority-build59.py"
READINESS = ROOT / "b3_trader/dex_shadow_readiness_audit.py"
TEMPORAL = ROOT / "b3_trader/dex_temporal_diversity_backfill.py"
IDENTITY = ROOT / "b3_trader/temporal_identity_preparation.py"
PIPELINE = ROOT / "b3_trader/research_pipeline_accelerator.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    priority = _text(PRIORITY)
    runner = _text(RUNNER)
    verify = _text(VERIFY)
    readiness = _text(READINESS)
    temporal = _text(TEMPORAL)
    identity = _text(IDENTITY)
    pipeline = _text(PIPELINE)
    ast.parse(priority)
    ast.parse(verify)

    checks = {
        "build59_extends_bounded_build55": "DexShadowRemediationRunner" in priority,
        "build59_unattempted_first": 'BUILD59_PRIORITY_POLICY = "unattempted_distinct_source_first"' in priority and '"previously_attempted"' in priority,
        "build59_distinct_source_grouping": "grouped[_source_key(candidate)].append(candidate)" in priority and '"source_group_case_count"' in priority,
        "build59_previous_attempt_source_deprioritized": '"source_previously_attempted"' in priority and '"previously_attempted_sources_deprioritized": True' in priority,
        "build59_no_threshold_retune": "MIN_LAUNCH_FEATURE_COVERAGE = 0.30" in readiness and "MAX_MONTH_SHARE = 0.40" in readiness,
        "build59_build57_policy_unchanged": "july_fallback_execution_enabled" in temporal and "new_unique_asset_only" in temporal,
        "build59_build58_identity_fail_closed": "ticker_only_forbidden" in identity and "verified_coingecko_only_on_write" in identity,
        "build59_build55_hard_limit_preserved": "MAX_LAUNCH_RECOVERY_CASES = 2" in runner,
        "build59_build55_cooldown_preserved": "LAUNCH_RETRY_AFTER_SECONDS = 6 * 3600" in runner,
        "build59_selected_primary_preserved": "p.selected_primary=1" in runner,
        "build59_no_check_same_thread_override": "check_same_thread=False" not in priority and "check_same_thread=False" not in runner,
        "build59_pipeline_not_wired": "dex_launch_recovery_priority" not in pipeline,
        "build59_no_score_order_wiring": '"can_place_orders": False' not in priority and '"score_wired": False' not in priority,
        "build59_direct_verifier_bootstrap": "sys.path.insert" in verify and "--import-check" in verify,
    }
    print("=== DEX LAUNCH RECOVERY PRIORITY BUILD 59 CONTRACT ===")
    print(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_LAUNCH_RECOVERY_PRIORITY_BUILD59=FAIL")
    print("DEX_LAUNCH_RECOVERY_PRIORITY_BUILD59=PASS")


if __name__ == "__main__":
    main()
