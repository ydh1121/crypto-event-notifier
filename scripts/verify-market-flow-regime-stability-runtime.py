from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_regime_stability import (
    HISTORY_BUCKET_SECONDS,
    MIN_CONTIGUOUS_BUCKETS,
    STABILITY_WINDOW_BUCKETS,
    MarketFlowRegimeStabilityStore,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-data", action="store_true")
    args = parser.parse_args()

    store = MarketFlowRegimeStabilityStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    thresholds = audit.get("thresholds") if isinstance(audit.get("thresholds"), dict) else {}
    checks = {
        "table_ready": audit.get("table_exists") is True,
        "audit_ok": audit.get("ok") is True,
        "history_bucket_exact": int(thresholds.get("history_bucket_seconds") or 0) == HISTORY_BUCKET_SECONDS,
        "minimum_history_exact": int(thresholds.get("min_contiguous_buckets") or 0) == MIN_CONTIGUOUS_BUCKETS,
        "stability_window_exact": int(thresholds.get("stability_window_buckets") or 0) == STABILITY_WINDOW_BUCKETS,
        "hard_degradation_contract_clean": int(audit.get("hard_degradation_contract_violations") or 0) == 0,
        "soft_degradation_contract_clean": int(audit.get("soft_degradation_contract_violations") or 0) == 0,
        "readiness_contract_clean": int(audit.get("readiness_contract_violations") or 0) == 0,
        "safety_contract_clean": int(audit.get("safety_contract_violations") or 0) == 0,
        "no_wiring_columns": not audit.get("suspicious_wiring_columns"),
        "not_probability_or_trading_score": audit.get("interpretation") == "longitudinal_evidence_stability_not_probability_not_trading_score",
        "paper_only": audit.get("paper_only") is True,
        "shadow_only": audit.get("shadow_only") is True,
        "score_unwired": audit.get("score_wired") is False,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "cannot_modify_strategy": audit.get("can_modify_strategy") is False,
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
        "data_present": int(audit.get("row_count") or 0) > 0,
    }
    required = [
        "table_ready","audit_ok","history_bucket_exact","minimum_history_exact",
        "stability_window_exact","hard_degradation_contract_clean",
        "soft_degradation_contract_clean","readiness_contract_clean",
        "safety_contract_clean","no_wiring_columns","not_probability_or_trading_score",
        "paper_only","shadow_only","score_unwired","cannot_place_orders",
        "cannot_modify_strategy","raw_cloud_projection_disabled",
    ]
    if args.require_data:
        required.append("data_present")

    ok = all(bool(checks[name]) for name in required)
    payload = {
        "status": "runtime_verified" if ok else "runtime_verification_failed",
        "checks": checks,
        "audit": audit,
        "expected_current_semantics": {
            "exact_15m_contiguous_history_only": True,
            "four_buckets_minimum_observation": True,
            "twelve_buckets_stability_window": True,
            "oos_mixed_overrides_numeric_confidence_as_hard_degradation": True,
            "started_oos_gate_with_current_base_loss_is_soft_degradation": True,
            "stability_is_not_probability_or_trading_score": True,
        },
        "read_only": True,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"MARKET_FLOW_REGIME_STABILITY_RUNTIME={'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
