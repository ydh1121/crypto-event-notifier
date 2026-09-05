from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_family_dedup import (
    AGGREGATION_METHOD,
    CORRELATION_POLICY,
    MarketFlowFamilyDedupStore,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-suppression", action="store_true")
    args = parser.parse_args()

    store = MarketFlowFamilyDedupStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    rows = audit.get("rows") if isinstance(audit.get("rows"), list) else []
    members = audit.get("members") if isinstance(audit.get("members"), list) else []
    suppressed_members = sum(1 for row in members if int(row.get("suppressed_correlated_member") or 0) == 1)
    checks = {
        "summary_table_ready": audit.get("summary_table_exists") is True,
        "member_table_ready": audit.get("member_table_exists") is True,
        "audit_ok": audit.get("ok") is True,
        "paper_only": audit.get("paper_only") is True,
        "shadow_only": audit.get("shadow_only") is True,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "cannot_modify_strategy": audit.get("can_modify_strategy") is False,
        "score_unwired": audit.get("score_wired") is False and not audit.get("wiring_columns"),
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
        "representative_contract_clean": int(audit.get("representative_contract_violations") or 0) == 0,
        "weight_contract_clean": int(audit.get("effective_weight_contract_violations") or 0) == 0,
        "suppression_contract_clean": int(audit.get("suppression_contract_violations") or 0) == 0,
        "summary_contract_clean": int(audit.get("summary_contract_violations") or 0) == 0,
        "member_count_contract_clean": int(audit.get("member_count_mismatches") or 0) == 0,
        "base_gate_lifecycle_clean": int(audit.get("base_gate_lifecycle_mismatches") or 0) == 0,
        "correlation_policy_exact": audit.get("correlation_policy") == CORRELATION_POLICY,
        "aggregation_method_exact": audit.get("aggregation_method") == AGGREGATION_METHOD,
        "empirical_correlation_not_claimed": audit.get("empirical_correlation_estimated") is False,
        "not_probability": audit.get("probability_interpretation") is False,
        "data_present": int(audit.get("family_count") or 0) > 0 and int(audit.get("member_count") or 0) > 0,
        "suppression_observed": suppressed_members > 0 or any(int(row.get("suppressed_member_count") or 0) > 0 for row in rows),
    }
    required = [
        "summary_table_ready","member_table_ready","audit_ok","paper_only","shadow_only",
        "cannot_place_orders","cannot_modify_strategy","score_unwired","raw_cloud_projection_disabled",
        "representative_contract_clean","weight_contract_clean","suppression_contract_clean",
        "summary_contract_clean","member_count_contract_clean","base_gate_lifecycle_clean",
        "correlation_policy_exact","aggregation_method_exact","empirical_correlation_not_claimed",
        "not_probability",
    ]
    if args.require_data:
        required.append("data_present")
    if args.require_suppression:
        required.append("suppression_observed")

    ok = all(bool(checks[name]) for name in required)
    payload = {
        "status": "runtime_verified" if ok else "runtime_verification_failed",
        "checks": checks,
        "audit": audit,
        "expected_current_semantics": {
            "same_market_regime_horizon_is_one_family": True,
            "one_representative_member_has_weight_one": True,
            "correlated_sibling_members_have_weight_zero": True,
            "opposite_regimes_are_not_netted": True,
            "different_reaction_horizons_are_not_merged": True,
            "base_gate_started_is_propagated_independently_from_current_base_ready": True,
            "effective_family_confidence_is_not_a_probability_or_trading_score": True,
        },
        "read_only": True,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"MARKET_FLOW_FAMILY_DEDUP_RUNTIME={'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
