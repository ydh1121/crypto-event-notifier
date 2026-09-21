from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_full_cost_event_cluster import MarketFlowFullCostEventClusterStore
from b3_trader.market_flow_full_cost_event_reliability import MarketFlowFullCostEventReliabilityStore
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

        cluster_store = MarketFlowFullCostEventClusterStore()
        reliability_store = MarketFlowFullCostEventReliabilityStore()
        try:
            cluster_result = cluster_store.compute()
            cluster_audit = cluster_store.audit()
            reliability_result = reliability_store.compute()
            reliability_audit = reliability_store.audit()
        finally:
            reliability_store.close()
            cluster_store.close()

    return {
        "ok": all((
            bool(cluster_result.get("ok")),
            bool(cluster_audit.get("ok")),
            bool(reliability_result.get("ok")),
            bool(reliability_audit.get("ok")),
        )),
        "status": "full_cost_event_validation_manual_qa_complete",
        "shared_research_work_lock": True,
        "network_fetches": False,
        "database_mutation": True,
        "cluster_result": cluster_result,
        "cluster_audit": cluster_audit,
        "reliability_result": reliability_result,
        "reliability_audit": reliability_audit,
        "paper_only": True,
        "shadow_only": True,
        "score_wired": False,
        "can_place_orders": False,
    }


def main() -> None:
    payload = run_once()
    print("=== MARKET FLOW FULL COST EVENT VALIDATION LOCKED QA ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload.get("ok"):
        print("MARKET_FLOW_FULL_COST_EVENT_VALIDATION_LOCKED=FAIL")
        raise SystemExit(1)
    if payload.get("status") == "deferred_research_work_lock_busy":
        print("MARKET_FLOW_FULL_COST_EVENT_VALIDATION_LOCKED=DEFERRED")
        raise SystemExit(75)
    print("MARKET_FLOW_FULL_COST_EVENT_VALIDATION_LOCKED=PASS")


if __name__ == "__main__":
    main()
