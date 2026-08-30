from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "b3_trader" / "dex_launch_coverage_audit.py"
VERIFY = ROOT / "scripts" / "verify-dex-launch-coverage-audit-build60.py"


def require(text: str, needle: str, key: str, checks: dict[str, bool]) -> None:
    checks[key] = needle in text


def main() -> None:
    module = MODULE.read_text(encoding="utf-8")
    verify = VERIFY.read_text(encoding="utf-8")
    checks: dict[str, bool] = {}

    require(module, '"read_only": True', "build60_read_only", checks)
    require(module, '"network_fetches": False', "build60_no_network_fetches", checks)
    require(module, '"can_place_orders": False', "build60_no_orders", checks)
    require(module, '"score_wired": False', "build60_no_score_wiring", checks)
    require(module, '"changes_build53_thresholds": False', "build60_no_threshold_retune", checks)
    require(module, '"changes_feature_criteria": False', "build60_feature_criteria_unchanged", checks)
    require(module, 'feature_json.pool_launch_window.status == collected', "build60_exact_launch_count_rule", checks)
    require(module, 'partial_candles_without_launch_reference', "build60_partial_reference_gap", checks)
    require(module, 'accepted_non_primary_pool', "build60_alternate_pool_audit", checks)
    require(module, 'source_previously_attempted', "build60_attempt_history_audit", checks)
    require(module, 'Build54 treats unavailable primary pools inside the 183-day window as recoverable', "build60_build54_warning", checks)
    checks["build60_no_check_same_thread_override"] = "check_same_thread" not in module
    checks["build60_no_http_client"] = all(token not in module for token in ("requests.", "httpx.", "urllib.request", ".ohlcv("))
    require(verify, "DEX_LAUNCH_COVERAGE_AUDIT_BUILD60_RUNTIME=PASS", "build60_runtime_verifier", checks)
    require(verify, "--import-check", "build60_direct_import_bootstrap", checks)

    print("=== DEX LAUNCH COVERAGE AUDIT BUILD 60 CONTRACT ===")
    import json

    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not checks or not all(checks.values()):
        raise SystemExit("DEX_LAUNCH_COVERAGE_AUDIT_BUILD60=FAIL")
    print("DEX_LAUNCH_COVERAGE_AUDIT_BUILD60=PASS")


if __name__ == "__main__":
    main()
