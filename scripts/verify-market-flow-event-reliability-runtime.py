from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_event_reliability import (
    INTERPRETATION,
    OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS,
    OBSERVATION_MIN_EVENTS,
    PROMOTION_CROSS_POSITIVE_WILSON_LOWER_PCT,
    PROMOTION_EVENT_WILSON_LOWER_PCT,
    PROMOTION_MIN_CROSS_EXCHANGE_EVENTS,
    PROMOTION_MIN_EVENTS,
    MarketFlowEventReliabilityStore,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-observation", action="store_true")
    args = parser.parse_args()

    store = MarketFlowEventReliabilityStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    thresholds = audit.get("thresholds") or {}
    checks = {
        "table_ready": audit.get("table_exists") is True,
        "audit_ok": audit.get("ok") is True,
        "promotion_contract_clean": int(audit.get("promotion_contract_violations") or 0) == 0,
        "observation_contract_clean": int(audit.get("observation_contract_violations") or 0) == 0,
        "direction_contract_clean": int(audit.get("direction_contract_violations") or 0) == 0,
        "threshold_contract_exact": (
            int(thresholds.get("observation_min_events") or 0) == OBSERVATION_MIN_EVENTS
            and int(thresholds.get("observation_min_cross_exchange_events") or 0) == OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS
            and int(thresholds.get("promotion_min_events") or 0) == PROMOTION_MIN_EVENTS
            and int(thresholds.get("promotion_min_cross_exchange_events") or 0) == PROMOTION_MIN_CROSS_EXCHANGE_EVENTS
            and float(thresholds.get("promotion_event_wilson_lower_pct") or 0.0) == PROMOTION_EVENT_WILSON_LOWER_PCT
            and float(thresholds.get("promotion_cross_positive_wilson_lower_pct") or 0.0) == PROMOTION_CROSS_POSITIVE_WILSON_LOWER_PCT
        ),
        "no_wiring_columns": not audit.get("suspicious_wiring_columns"),
        "not_full_cost_probability_or_trading_score": audit.get("interpretation") == INTERPRETATION,
        "paper_only": audit.get("paper_only") is True,
        "shadow_only": audit.get("shadow_only") is True,
        "score_unwired": audit.get("score_wired") is False,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "cannot_modify_strategy": audit.get("can_modify_strategy") is False,
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
        "data_present": int(audit.get("row_count") or 0) > 0,
        "observation_present": int(audit.get("observation_ready_rows") or 0) > 0,
    }
    required = [
        "table_ready","audit_ok","promotion_contract_clean","observation_contract_clean",
        "direction_contract_clean","threshold_contract_exact","no_wiring_columns",
        "not_full_cost_probability_or_trading_score","paper_only","shadow_only","score_unwired",
        "cannot_place_orders","cannot_modify_strategy","raw_cloud_projection_disabled",
    ]
    if args.require_data:
        required.append("data_present")
    if args.require_observation:
        required.append("observation_present")

    ok = all(bool(checks[name]) for name in required)
    payload = {
        "status": "runtime_verified" if ok else "runtime_verification_failed",
        "checks": checks,
        "audit": audit,
        "expected_current_semantics": {
            "clustered_event_is_primary_observation": True,
            "cross_exchange_positive_requires_both_venues_positive": True,
            "observation_threshold_events": OBSERVATION_MIN_EVENTS,
            "observation_threshold_cross_exchange_events": OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS,
            "promotion_threshold_events": PROMOTION_MIN_EVENTS,
            "promotion_threshold_cross_exchange_events": PROMOTION_MIN_CROSS_EXCHANGE_EVENTS,
            "both_wilson_lower_bounds_must_exceed_chance_for_promotion": True,
            "fee_and_historical_ladder_slippage_still_missing": True,
            "event_reliability_is_not_probability_or_trading_score": True,
        },
        "read_only": True,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"MARKET_FLOW_EVENT_RELIABILITY_RUNTIME={'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
