from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_cost_edge import MarketFlowCostEdgeStore
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
        store = MarketFlowCostEdgeStore()
        try:
            result = store.compute()
            audit = store.audit()
        finally:
            store.close()
    return {
        "ok": bool(result.get("ok")) and bool(audit.get("ok")),
        "status": "flow_cost_edge_manual_qa_complete",
        "shared_research_work_lock": True,
        "network_fetches": False,
        "database_mutation": True,
        "result": result,
        "audit": audit,
        "paper_only": True,
        "shadow_only": True,
        "score_wired": False,
        "can_place_orders": False,
    }


def main() -> None:
    payload = run_once()
    print("=== MARKET FLOW COST EDGE LOCKED QA ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload.get("ok"):
        print("MARKET_FLOW_COST_EDGE_LOCKED=FAIL")
        raise SystemExit(1)
    if payload.get("status") == "deferred_research_work_lock_busy":
        print("MARKET_FLOW_COST_EDGE_LOCKED=DEFERRED")
        raise SystemExit(75)
    print("MARKET_FLOW_COST_EDGE_LOCKED=PASS")


if __name__ == "__main__":
    main()
