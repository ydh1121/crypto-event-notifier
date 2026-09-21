from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_regime_confidence import MarketFlowRegimeConfidenceStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-data", action="store_true")
    args = parser.parse_args()

    store = MarketFlowRegimeConfidenceStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    checks = {
        "table_ready": bool(audit.get("table_exists")),
        "audit_ok": bool(audit.get("ok")),
        "paper_only": audit.get("paper_only") is True,
        "shadow_only": audit.get("shadow_only") is True,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "cannot_modify_strategy": audit.get("can_modify_strategy") is False,
        "score_unwired": audit.get("score_wired") is False and not audit.get("wiring_columns"),
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
        "aggregation_blocked": audit.get("family_aggregation_blocked") is True,
        "not_probability": audit.get("interpretation") == "evidence_maturity_not_probability_not_trading_score",
        "aggregation_contract_clean": int(audit.get("aggregation_contract_violations") or 0) == 0,
        "probability_contract_clean": int(audit.get("probability_contract_violations") or 0) == 0,
        "confidence_caps_clean": int(audit.get("confidence_cap_violations") or 0) == 0,
        "regime_mapping_clean": int(audit.get("regime_mapping_violations") or 0) == 0,
        "base_gate_semantics_clean": int(audit.get("base_gate_semantics_violations") or 0) == 0,
        "base_gate_semantics_declared": (
            audit.get("base_gate_started_semantics")
            == "ever_crossed_base_threshold_and_froze_forward_oos_cutoff"
            and audit.get("base_promotion_ready_semantics")
            == "current_full_sample_still_meets_base_threshold"
        ),
        "data_present": int(audit.get("row_count") or 0) > 0,
    }
    required = [
        "table_ready","audit_ok","paper_only","shadow_only","cannot_place_orders",
        "cannot_modify_strategy","score_unwired","raw_cloud_projection_disabled",
        "aggregation_blocked","not_probability","aggregation_contract_clean",
        "probability_contract_clean","confidence_caps_clean","regime_mapping_clean",
        "base_gate_semantics_clean","base_gate_semantics_declared",
    ]
    if args.require_data:
        required.append("data_present")

    ok = all(bool(checks[name]) for name in required)
    payload = {
        "status": "runtime_verified" if ok else "runtime_verification_failed",
        "checks": checks,
        "audit": audit,
        "expected_current_semantics": {
            "confidence_is_evidence_maturity_not_probability": True,
            "multi_timeframe_family_aggregation_is_blocked": True,
            "base_gate_started_is_monotonic_frozen_oos_lifecycle": True,
            "base_promotion_ready_is_current_sample_threshold_result": True,
            "base_gate_can_remain_started_after_current_base_ready_falls_false": True,
            "pre_oos_rows_are_capped_below_full_validation": True,
            "oos_validated_rows_remain_shadow_only": True,
        },
        "read_only": True,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"MARKET_FLOW_REGIME_CONFIDENCE_RUNTIME={'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
