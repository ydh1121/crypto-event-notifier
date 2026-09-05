from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "b3_trader/dex_shadow_remediation_plan.py"
VERIFY = ROOT / "scripts/verify-dex-shadow-remediation-build54.py"
QUALITY = ROOT / "b3_trader/dex_launch_quality.py"
DIVERSITY = ROOT / "b3_trader/dex_diversity_backfill.py"
READINESS = ROOT / "b3_trader/dex_shadow_readiness_audit.py"
PIPELINE = ROOT / "b3_trader/research_pipeline_accelerator.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    plan = _text(PLAN)
    verify = _text(VERIFY)
    quality = _text(QUALITY)
    diversity = _text(DIVERSITY)
    readiness = _text(READINESS)
    pipeline = _text(PIPELINE)
    ast.parse(plan)
    ast.parse(verify)

    checks = {
        "build54_read_only": "sqlite3.connect" in plan and "INSERT INTO" not in plan and "UPDATE " not in plan and "DELETE FROM" not in plan,
        "build54_reads_build53_blockers": "audit_dex_shadow_readiness" in plan and "blocking_reasons" in plan,
        "build54_plans_temporal_target": "minimum_target_usable_cases" in plan and "additional_non_dominant_usable_cases_needed" in plan,
        "build54_plans_launch_target": "required_launch_cases_at_temporal_target" in plan and "recoverable_existing_cases" in plan,
        "build54_classifies_launch_missing": "history_window_expired" in plan and "recoverable_recent" in plan,
        "build54_reports_existing_backlog": "verified_without_dex_status_by_month" in plan,
        "build54_advisory_only": '"advisory_only": True' in plan and '"wire_shadow_score_now": False' in plan,
        "build54_build45_thresholds_unchanged": "MIN_USABLE_CASES = 20" in quality and "MIN_EXACT_P5M_COVERAGE = 0.60" in quality,
        "build54_build51_policy_unchanged": "new_unique_asset" in diversity and "partial_completion_retry" in diversity,
        "build54_build53_thresholds_unchanged": "MIN_LAUNCH_FEATURE_COVERAGE = 0.30" in readiness and "MAX_MONTH_SHARE = 0.40" in readiness,
        "build54_pipeline_not_wired": "dex_shadow_remediation_plan" not in pipeline,
        "build54_direct_verifier_bootstrap": "sys.path.insert" in verify and "--import-check" in verify,
        "build54_no_score_decision_order_wiring": '"can_place_orders": False' in plan and '"score_wired": False' in plan,
    }
    print("=== DEX SHADOW REMEDIATION BUILD 54 CONTRACT ===")
    print(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_SHADOW_REMEDIATION_BUILD54=FAIL")
    print("DEX_SHADOW_REMEDIATION_BUILD54=PASS")


if __name__ == "__main__":
    main()
