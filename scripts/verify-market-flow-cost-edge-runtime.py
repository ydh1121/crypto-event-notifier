from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_cost_edge import MarketFlowCostEdgeStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-spread-ready", action="store_true")
    args = parser.parse_args()

    store = MarketFlowCostEdgeStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    checks = {
        "table_ready": audit.get("table_exists") is True,
        "audit_ok": audit.get("ok") is True,
        "spread_contract_clean": int(audit.get("spread_contract_violations") or 0) == 0,
        "incomplete_cost_contract_clean": int(audit.get("incomplete_cost_contract_violations") or 0) == 0,
        "full_cost_fail_closed": int(audit.get("full_cost_ready_rows") or 0) == 0,
        "no_wiring_columns": not audit.get("suspicious_wiring_columns"),
        "not_complete_cost_or_trading_score": audit.get("interpretation") == "spread_adjusted_research_edge_not_complete_transaction_cost_not_trading_score",
        "paper_only": audit.get("paper_only") is True,
        "shadow_only": audit.get("shadow_only") is True,
        "score_unwired": audit.get("score_wired") is False,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "cannot_modify_strategy": audit.get("can_modify_strategy") is False,
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
        "data_present": int(audit.get("row_count") or 0) > 0,
        "spread_ready_present": int(audit.get("orderbook_friction_ready_rows") or 0) > 0,
    }
    required = [
        "table_ready","audit_ok","spread_contract_clean","incomplete_cost_contract_clean",
        "full_cost_fail_closed","no_wiring_columns","not_complete_cost_or_trading_score",
        "paper_only","shadow_only","score_unwired","cannot_place_orders",
        "cannot_modify_strategy","raw_cloud_projection_disabled",
    ]
    if args.require_data:
        required.append("data_present")
    if args.require_spread_ready:
        required.append("spread_ready_present")

    ok = all(bool(checks[name]) for name in required)
    payload = {
        "status": "runtime_verified" if ok else "runtime_verification_failed",
        "checks": checks,
        "audit": audit,
        "expected_current_semantics": {
            "exact_continuous_1m_entry_and_exit_orderbook_only": True,
            "roundtrip_spread_penalty_is_half_entry_plus_half_exit": True,
            "historical_depth_ladder_slippage_not_invented": True,
            "fee_schedule_not_invented": True,
            "full_cost_edge_fail_closed_until_both_models_exist": True,
            "cost_edge_is_not_probability_or_trading_score": True,
        },
        "read_only": True,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"MARKET_FLOW_COST_EDGE_RUNTIME={'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
