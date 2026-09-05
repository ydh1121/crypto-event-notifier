from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "b3_trader/dex_sample_audit.py"
VERIFY = ROOT / "scripts/verify-dex-sample-audit-build50.py"
QUALITY = ROOT / "b3_trader/dex_launch_quality.py"
PIPELINE = ROOT / "b3_trader/research_pipeline_accelerator.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    audit = _text(AUDIT)
    verify = _text(VERIFY)
    quality = _text(QUALITY)
    pipeline = _text(PIPELINE)
    ast.parse(audit)
    ast.parse(verify)

    checks = {
        "build50_read_only_sample_audit": "sqlite3.connect" in audit and "INSERT INTO" not in audit and "UPDATE " not in audit and "DELETE FROM" not in audit,
        "build50_reports_unique_assets": '"unique_assets"' in audit and '"duplicate_asset_groups"' in audit,
        "build50_reports_exchange_distribution": '"exchange_distribution"' in audit and '"max_exchange_share"' in audit,
        "build50_reports_completion_distribution": '"completion_distribution"' in audit and '"complete_partial_ratio"' in audit,
        "build50_reports_failure_distribution": '"not_usable_status_distribution"' in audit,
        "build50_reports_launch_coverage": '"launch_feature_coverage"' in audit,
        "build50_advisory_only": '"advisory_only": True' in audit and '"changes_build45_thresholds": False' in audit,
        "build50_build45_thresholds_unchanged": "MIN_USABLE_CASES = 20" in quality and "MIN_EXACT_P5M_COVERAGE = 0.60" in quality,
        "build50_pipeline_does_not_import_audit": "dex_sample_audit" not in pipeline,
        "build50_direct_verifier_bootstrap": "sys.path.insert" in verify and "--import-check" in verify,
        "build50_no_score_decision_order_wiring": "can_place_orders\": False" in audit and "score_wired\": False" in audit,
    }
    print("=== DEX SAMPLE AUDIT BUILD 50 CONTRACT ===")
    print(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_SAMPLE_AUDIT_BUILD50=FAIL")
    print("DEX_SAMPLE_AUDIT_BUILD50=PASS")


if __name__ == "__main__":
    main()
