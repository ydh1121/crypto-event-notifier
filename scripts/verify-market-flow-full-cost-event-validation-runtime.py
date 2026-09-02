from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_full_cost_event_cluster import (
    CLUSTER_POLICY,
    REPRESENTATIVE_POLICY,
    MarketFlowFullCostEventClusterStore,
)
from b3_trader.market_flow_full_cost_event_reliability import (
    INTERPRETATION,
    OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS,
    OBSERVATION_MIN_EVENTS,
    PROMOTION_CROSS_POSITIVE_WILSON_LOWER_PCT,
    PROMOTION_EVENT_WILSON_LOWER_PCT,
    PROMOTION_MIN_CROSS_EXCHANGE_EVENTS,
    PROMOTION_MIN_EVENTS,
    MarketFlowFullCostEventReliabilityStore,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-source", action="store_true")
    parser.add_argument("--require-event", action="store_true")
    parser.add_argument("--require-cross-exchange", action="store_true")
    parser.add_argument("--require-observation", action="store_true")
    args = parser.parse_args()

    cluster_store = MarketFlowFullCostEventClusterStore()
    reliability_store = MarketFlowFullCostEventReliabilityStore()
    try:
        cluster = cluster_store.audit()
        reliability = reliability_store.audit()
    finally:
        reliability_store.close()
        cluster_store.close()

    source_members = int(cluster.get("member_count") or 0)
    event_count = int(cluster.get("event_count") or 0)
    cross_count = int(cluster.get("cross_exchange_event_count") or 0)
    observation_count = int(reliability.get("observation_ready_rows") or 0)

    thresholds = reliability.get("thresholds") or {}
    checks = {
        "cluster_tables_ready": cluster.get("tables_ready") is True,
        "cluster_audit_ok": cluster.get("ok") is True,
        "membership_contract_clean": int(cluster.get("membership_contract_violations") or 0) == 0,
        "representative_contract_clean": int(cluster.get("representative_contract_violations") or 0) == 0,
        "event_mean_contract_clean": int(cluster.get("event_mean_contract_violations") or 0) == 0,
        "cross_exchange_contract_clean": int(cluster.get("cross_exchange_contract_violations") or 0) == 0,
        "full_cost_source_contract_clean": int(cluster.get("full_cost_source_contract_violations") or 0) == 0,
        "cluster_policy_exact": cluster.get("cluster_policy") == CLUSTER_POLICY,
        "representative_policy_exact": cluster.get("representative_policy") == REPRESENTATIVE_POLICY,
        "reliability_table_ready": reliability.get("table_exists") is True,
        "reliability_audit_ok": reliability.get("ok") is True,
        "promotion_contract_clean": int(reliability.get("promotion_contract_violations") or 0) == 0,
        "observation_contract_clean": int(reliability.get("observation_contract_violations") or 0) == 0,
        "direction_contract_clean": int(reliability.get("direction_contract_violations") or 0) == 0,
        "reliability_full_cost_source_contract_clean": int(reliability.get("full_cost_source_contract_violations") or 0) == 0,
        "threshold_contract_exact": (
            int(thresholds.get("observation_min_events") or 0) == OBSERVATION_MIN_EVENTS
            and int(thresholds.get("observation_min_cross_exchange_events") or 0) == OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS
            and int(thresholds.get("promotion_min_events") or 0) == PROMOTION_MIN_EVENTS
            and int(thresholds.get("promotion_min_cross_exchange_events") or 0) == PROMOTION_MIN_CROSS_EXCHANGE_EVENTS
            and float(thresholds.get("promotion_event_wilson_lower_pct") or 0.0) == PROMOTION_EVENT_WILSON_LOWER_PCT
            and float(thresholds.get("promotion_cross_positive_wilson_lower_pct") or 0.0) == PROMOTION_CROSS_POSITIVE_WILSON_LOWER_PCT
        ),
        "interpretation_exact": reliability.get("interpretation") == INTERPRETATION,
        "historical_backfill_disabled": (
            cluster.get("historical_full_cost_backfill") is False
            and reliability.get("historical_full_cost_backfill") is False
        ),
        "not_probability_or_trading_score": reliability.get("probability_interpretation") is False,
        "paper_only": reliability.get("paper_only") is True,
        "shadow_only": reliability.get("shadow_only") is True,
        "score_unwired": reliability.get("score_wired") is False,
        "cannot_place_orders": reliability.get("can_place_orders") is False,
        "cannot_modify_strategy": reliability.get("can_modify_strategy") is False,
        "raw_cloud_projection_disabled": reliability.get("raw_cloud_projection") is False,
        "source_present": source_members > 0,
        "event_present": event_count > 0,
        "cross_exchange_present": cross_count > 0,
        "observation_present": observation_count > 0,
    }

    required = [
        "cluster_tables_ready","cluster_audit_ok","membership_contract_clean",
        "representative_contract_clean","event_mean_contract_clean","cross_exchange_contract_clean",
        "full_cost_source_contract_clean","cluster_policy_exact","representative_policy_exact",
        "reliability_table_ready","reliability_audit_ok","promotion_contract_clean",
        "observation_contract_clean","direction_contract_clean","reliability_full_cost_source_contract_clean",
        "threshold_contract_exact","interpretation_exact","historical_backfill_disabled",
        "not_probability_or_trading_score","paper_only","shadow_only","score_unwired",
        "cannot_place_orders","cannot_modify_strategy","raw_cloud_projection_disabled",
    ]
    if args.require_source:
        required.append("source_present")
    if args.require_event:
        required.append("event_present")
    if args.require_cross_exchange:
        required.append("cross_exchange_present")
    if args.require_observation:
        required.append("observation_present")

    ok = all(bool(checks[name]) for name in required)
    payload = {
        "status": "runtime_verified" if ok else "runtime_verification_failed",
        "checks": checks,
        "cluster_audit": cluster,
        "reliability_audit": reliability,
        "expected_current_semantics": {
            "source_requires_full_cost_edge_ready": True,
            "historical_full_cost_backfill_forbidden": True,
            "fixed_anchor_overlap_policy": True,
            "representative_selection_uses_no_performance": True,
            "cross_exchange_requires_both_full_cost_venues": True,
            "bithumb_unverified_fee_profile_can_keep_cross_exchange_at_zero": True,
            "observation_threshold_events": OBSERVATION_MIN_EVENTS,
            "observation_threshold_cross_exchange_events": OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS,
            "promotion_threshold_events": PROMOTION_MIN_EVENTS,
            "promotion_threshold_cross_exchange_events": PROMOTION_MIN_CROSS_EXCHANGE_EVENTS,
            "both_wilson_lower_bounds_must_exceed_chance": True,
            "full_cost_reliability_is_not_probability_or_trading_score": True,
        },
        "read_only": True,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"MARKET_FLOW_FULL_COST_EVENT_VALIDATION_RUNTIME={'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
