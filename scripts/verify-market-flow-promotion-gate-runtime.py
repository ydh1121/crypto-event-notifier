from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_promotion_gate import (
    MarketFlowPromotionGateStore,
    OOS_MIN_PER_VENUE,
    OOS_MIN_POOLED,
    OOS_WILSON_LOWER_PCT,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-oos-sample-ready", action="store_true")
    parser.add_argument("--require-final-candidate", action="store_true")
    args = parser.parse_args()

    store = MarketFlowPromotionGateStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    thresholds = audit.get("thresholds") if isinstance(audit.get("thresholds"), dict) else {}
    checks = {
        "gate_table_ready": audit.get("gate_table_exists") is True,
        "transition_table_ready": audit.get("transition_table_exists") is True,
        "audit_ok": audit.get("ok") is True,
        "paper_only": audit.get("paper_only") is True,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "score_unwired": audit.get("score_wired") is False and not audit.get("score_wiring_columns"),
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
        "oos_contract_clean": int(audit.get("oos_contract_violations") or 0) == 0,
        "forward_cutoff_clean": int(audit.get("forward_cutoff_count_mismatches") or 0) == 0,
        "cutoff_contract_strict": audit.get("cutoff_contract") == "signal_feature_ts_strictly_greater_than_frozen_cutoff",
        "threshold_contract": (
            int(thresholds.get("oos_min_per_venue") or 0) == OOS_MIN_PER_VENUE
            and int(thresholds.get("oos_min_pooled") or 0) == OOS_MIN_POOLED
            and float(thresholds.get("oos_wilson_lower_pct") or 0.0) == OOS_WILSON_LOWER_PCT
        ),
        "data_present": int(audit.get("row_count") or 0) > 0,
        "oos_sample_ready_present": int(audit.get("oos_sample_ready_rows") or 0) > 0,
        "final_candidate_present": int(audit.get("final_candidate_ready_rows") or 0) > 0,
    }
    required = [
        "gate_table_ready","transition_table_ready","audit_ok","paper_only","cannot_place_orders",
        "score_unwired","raw_cloud_projection_disabled","oos_contract_clean","forward_cutoff_clean",
        "cutoff_contract_strict","threshold_contract",
    ]
    if args.require_data:
        required.append("data_present")
    if args.require_oos_sample_ready:
        required.append("oos_sample_ready_present")
    if args.require_final_candidate:
        required.append("final_candidate_present")

    ok = all(bool(checks[name]) for name in required)
    payload = {
        "status": "runtime_verified" if ok else "runtime_verification_failed",
        "checks": checks,
        "audit": audit,
        "expected_current_semantics": {
            "zero_active_gates_is_valid_until_base_promotion": True,
            "base_promotion_source": "research_market_flow_reliability_mx.promotion_ready",
            "oos_rows_must_be_strictly_after_frozen_cutoff": True,
            "final_candidate_is_still_shadow_only": True,
        },
        "read_only": True,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"MARKET_FLOW_PROMOTION_GATE_RUNTIME={'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
