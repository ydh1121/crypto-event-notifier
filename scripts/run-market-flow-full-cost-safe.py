from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_fee_schedule import MarketFeeScheduleStore
from b3_trader.market_flow_full_cost_edge import MarketFlowFullCostEdgeStore
from b3_trader.market_orderbook_ladder import MarketOrderbookLadderStore
from b3_trader.research_work_lock import ResearchWorkLock


def run_once() -> dict:
    with ResearchWorkLock() as work_lock:
        if not work_lock.acquired:
            return {
                "ok": True,
                "status": "deferred_research_work_lock_busy",
                "shared_research_work_lock": True,
                "network_fetches": False,
                "database_mutation": False,
                "paper_only": True,
                "shadow_only": True,
                "score_wired": False,
                "can_place_orders": False,
            }
        fee_store = MarketFeeScheduleStore()
        ladder_store = MarketOrderbookLadderStore()
        full_store = MarketFlowFullCostEdgeStore()
        try:
            fee_store.ensure_current_catalog()
            fee_audit = fee_store.audit()
            ladder_audit = ladder_store.audit()
            result = full_store.compute()
            audit = full_store.audit()
        finally:
            full_store.close()
            ladder_store.close()
            fee_store.close()
    return {
        "ok": bool(fee_audit.get("ok")) and bool(ladder_audit.get("ok")) and bool(result.get("ok")) and bool(audit.get("ok")),
        "status": "flow_full_cost_manual_qa_complete",
        "shared_research_work_lock": True,
        "network_fetches": False,
        "database_mutation": True,
        "fee_audit": fee_audit,
        "ladder_audit": ladder_audit,
        "result": result,
        "audit": audit,
        "paper_only": True,
        "shadow_only": True,
        "score_wired": False,
        "can_place_orders": False,
    }


def main() -> None:
    payload = run_once()
    print("=== MARKET FLOW FULL COST LOCKED QA ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload.get("ok"):
        print("MARKET_FLOW_FULL_COST_LOCKED=FAIL")
        raise SystemExit(1)
    if payload.get("status") == "deferred_research_work_lock_busy":
        print("MARKET_FLOW_FULL_COST_LOCKED=DEFERRED")
        raise SystemExit(75)
    print("MARKET_FLOW_FULL_COST_LOCKED=PASS")


if __name__ == "__main__":
    main()
