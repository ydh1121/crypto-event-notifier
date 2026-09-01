from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_fee_schedule import MarketFeeScheduleStore
from b3_trader.market_flow_full_cost_edge import MarketFlowFullCostEdgeStore
from b3_trader.market_orderbook_ladder import MarketOrderbookLadderStore


def verify(*, require_ladder_data: bool, require_full_cost: bool) -> tuple[bool, dict]:
    fee_store = MarketFeeScheduleStore()
    ladder_store = MarketOrderbookLadderStore()
    full_store = MarketFlowFullCostEdgeStore()
    try:
        fee = fee_store.audit()
        ladder = ladder_store.audit()
        full = full_store.audit()
    finally:
        full_store.close()
        ladder_store.close()
        fee_store.close()

    checks = {
        "fee_catalog_ready": bool(fee.get("ok")) and int(fee.get("catalog_rows") or 0) >= 3,
        "upbit_fee_profile_resolves": fee.get("upbit_krw_profile") == "standard",
        "bithumb_fee_profile_fail_closed_or_selected": (
            fee.get("bithumb_krw_profile") in {None, "standard", "coupon_0_04"}
        ),
        "fee_forward_only_no_historical_backfill": fee.get("historical_fee_backfill") is False,
        "ladder_tables_ready": bool(ladder.get("tables_ready")),
        "ladder_contract_clean": bool(ladder.get("ok")),
        "ladder_prior_only": ladder.get("prior_only_minute_boundary") is True,
        "ladder_historical_backfill_disabled": ladder.get("historical_backfill") is False,
        "full_cost_audit_ok": bool(full.get("ok")),
        "full_cost_readiness_contract_clean": int(full.get("readiness_contract_violations") or 0) == 0,
        "full_cost_formula_contract_clean": int(full.get("formula_contract_violations") or 0) == 0,
        "full_cost_future_ladder_contract_clean": int(full.get("future_ladder_violations") or 0) == 0,
        "no_wiring_columns": not bool(full.get("suspicious_wiring_columns")),
        "paper_only": full.get("paper_only") is True,
        "shadow_only": full.get("shadow_only") is True,
        "score_unwired": full.get("score_wired") is False,
        "cannot_place_orders": full.get("can_place_orders") is False,
        "raw_cloud_projection_disabled": full.get("raw_cloud_projection") is False,
    }
    if require_ladder_data:
        checks["ladder_data_present"] = int(ladder.get("row_count") or 0) > 0
    if require_full_cost:
        checks["full_cost_data_present"] = int(full.get("full_cost_ready_rows") or 0) > 0
    ok = all(checks.values())
    return ok, {
        "status": "runtime_verified" if ok else "runtime_failed",
        "checks": checks,
        "fee_audit": fee,
        "ladder_audit": ladder,
        "full_cost_audit": full,
        "expected_current_semantics": {
            "current_fee_catalog_is_forward_only": True,
            "bithumb_coupon_is_never_assumed": True,
            "top5_ladder_is_one_latest_snapshot_per_minute": True,
            "cost_lookup_uses_immediately_prior_minute_only": True,
            "cost_lookup_requires_source_strictly_before_boundary": True,
            "cost_lookup_max_age_seconds": 5.0,
            "historical_ladder_backfill_forbidden": True,
            "full_cost_is_not_probability_or_trading_score": True,
        },
        "read_only_except_schema_open": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-ladder-data", action="store_true")
    parser.add_argument("--require-full-cost", action="store_true")
    args = parser.parse_args()
    ok, payload = verify(
        require_ladder_data=bool(args.require_ladder_data),
        require_full_cost=bool(args.require_full_cost),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not ok:
        print("MARKET_FLOW_FULL_COST_RUNTIME=FAIL")
        raise SystemExit(1)
    print("MARKET_FLOW_FULL_COST_RUNTIME=PASS")


if __name__ == "__main__":
    main()
