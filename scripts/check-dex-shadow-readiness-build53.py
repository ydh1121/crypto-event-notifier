from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "b3_trader/dex_shadow_readiness_audit.py"
VERIFY = ROOT / "scripts/verify-dex-shadow-readiness-build53.py"
QUALITY = ROOT / "b3_trader/dex_launch_quality.py"
DIVERSITY = ROOT / "b3_trader/dex_diversity_backfill.py"
PIPELINE = ROOT / "b3_trader/research_pipeline_accelerator.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    audit = _text(AUDIT)
    verify = _text(VERIFY)
    quality = _text(QUALITY)
    diversity = _text(DIVERSITY)
    pipeline = _text(PIPELINE)
    ast.parse(audit)
    ast.parse(verify)

    checks = {
        "build53_read_only": "sqlite3.connect" in audit and "INSERT INTO" not in audit and "UPDATE " not in audit and "DELETE FROM" not in audit,
        "build53_requires_build45_sample_ready": '"build45_sample_ready"' in audit and "build45_sample_not_ready" in audit,
        "build53_unique_asset_gate": "MIN_UNIQUE_ASSET_RATIO" in audit and "unique_asset_ratio_below_min" in audit,
        "build53_exchange_concentration_gate": "MAX_EXCHANGE_SHARE" in audit and "exchange_concentration_above_max" in audit,
        "build53_completion_balance_gate": "MIN_FULL_COMPLETE_RATIO" in audit and "MAX_COMPLETE_PARTIAL_RATIO" in audit,
        "build53_exact_p5m_gate": "MIN_EXACT_P5M_COVERAGE" in audit and "exact_p5m_coverage_below_min" in audit,
        "build53_launch_feature_gate": "MIN_LAUNCH_FEATURE_COVERAGE" in audit and "launch_feature_coverage_below_min" in audit,
        "build53_network_and_dex_concentration": "MAX_PRIMARY_NETWORK_SHARE" in audit and "MAX_PRIMARY_DEX_SHARE" in audit,
        "build53_temporal_concentration": "MAX_MONTH_SHARE" in audit and "temporal_concentration_above_max" in audit,
        "build53_source_failure_bias": "MAX_SOURCE_WAITING_SHARE_OF_NOT_USABLE" in audit and "source_waiting_share_above_max" in audit,
        "build53_advisory_only": '"advisory_only": True' in audit and '"wire_shadow_score_now": False' in audit,
        "build53_build45_thresholds_unchanged": "MIN_USABLE_CASES = 20" in quality and "MIN_EXACT_P5M_COVERAGE = 0.60" in quality,
        "build53_build51_policy_unchanged": "new_unique_asset" in diversity and "partial_completion_retry" in diversity,
        "build53_pipeline_not_wired": "dex_shadow_readiness_audit" not in pipeline,
        "build53_direct_verifier_bootstrap": "sys.path.insert" in verify and "--import-check" in verify,
        "build53_no_score_decision_order_wiring": '"can_place_orders": False' in audit and '"score_wired": False' in audit,
    }
    print("=== DEX SHADOW READINESS BUILD 53 CONTRACT ===")
    print(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_SHADOW_READINESS_BUILD53=FAIL")
    print("DEX_SHADOW_READINESS_BUILD53=PASS")


if __name__ == "__main__":
    main()
