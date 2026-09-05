from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_event_cluster import (
    CLUSTER_POLICY,
    REPRESENTATIVE_POLICY,
    MarketFlowEventClusterStore,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-reduction", action="store_true")
    parser.add_argument("--require-cross-exchange", action="store_true")
    args = parser.parse_args()

    store = MarketFlowEventClusterStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    checks = {
        "tables_ready": audit.get("tables_ready") is True,
        "audit_ok": audit.get("ok") is True,
        "membership_contract_clean": int(audit.get("membership_contract_violations") or 0) == 0,
        "representative_contract_clean": int(audit.get("representative_contract_violations") or 0) == 0,
        "representative_selection_clean": int(audit.get("representative_selection_violations") or 0) == 0,
        "event_mean_contract_clean": int(audit.get("event_mean_contract_violations") or 0) == 0,
        "cross_exchange_contract_clean": int(audit.get("cross_exchange_contract_violations") or 0) == 0,
        "fixed_anchor_nonoverlap_clean": int(audit.get("fixed_anchor_overlap_violations") or 0) == 0,
        "stats_contract_clean": int(audit.get("stats_contract_violations") or 0) == 0,
        "no_wiring_columns": not audit.get("suspicious_wiring_columns"),
        "cluster_policy_exact": audit.get("cluster_policy") == CLUSTER_POLICY,
        "representative_policy_exact": audit.get("representative_policy") == REPRESENTATIVE_POLICY,
        "not_independence_claim_or_trading_score": audit.get("interpretation") == "overlap_clustered_independentish_research_events_not_independence_claim_not_trading_score",
        "paper_only": audit.get("paper_only") is True,
        "shadow_only": audit.get("shadow_only") is True,
        "score_unwired": audit.get("score_wired") is False,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "cannot_modify_strategy": audit.get("can_modify_strategy") is False,
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
        "data_present": int(audit.get("event_count") or 0) > 0,
        "reduction_present": int(audit.get("event_count") or 0) < int(audit.get("member_count") or 0),
        "cross_exchange_present": int(audit.get("cross_exchange_event_count") or 0) > 0,
    }
    required = [
        "tables_ready","audit_ok","membership_contract_clean","representative_contract_clean",
        "representative_selection_clean","event_mean_contract_clean","cross_exchange_contract_clean",
        "fixed_anchor_nonoverlap_clean","stats_contract_clean","no_wiring_columns",
        "cluster_policy_exact","representative_policy_exact","not_independence_claim_or_trading_score",
        "paper_only","shadow_only","score_unwired","cannot_place_orders",
        "cannot_modify_strategy","raw_cloud_projection_disabled",
    ]
    if args.require_data:
        required.append("data_present")
    if args.require_reduction:
        required.append("reduction_present")
    if args.require_cross_exchange:
        required.append("cross_exchange_present")

    ok = all(bool(checks[name]) for name in required)
    payload = {
        "status": "runtime_verified" if ok else "runtime_verification_failed",
        "checks": checks,
        "audit": audit,
        "expected_current_semantics": {
            "same_market_regime_horizon_only": True,
            "fixed_anchor_reaction_end_never_extended": True,
            "signal_at_anchor_end_starts_new_event": True,
            "one_representative_per_exchange_per_event": True,
            "representative_selected_without_performance": True,
            "event_return_equal_weights_exchange_representatives": True,
            "cross_exchange_presence_preserved_as_confirmation": True,
            "statistical_independence_not_claimed": True,
            "event_cluster_is_not_probability_or_trading_score": True,
        },
        "read_only": True,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"MARKET_FLOW_EVENT_CLUSTER_RUNTIME={'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
