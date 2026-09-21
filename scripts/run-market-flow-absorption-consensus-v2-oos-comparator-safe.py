from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_absorption_consensus_v2_oos_comparator import (
    MarketFlowAbsorptionConsensusV2OosComparatorStore,
)
from b3_trader.research_work_lock import ResearchWorkLock


def run_once() -> dict:
    with ResearchWorkLock() as work_lock:
        if not work_lock.acquired:
            return {
                "ok": True,
                "status": "deferred_research_work_lock_busy",
                "shared_research_work_lock": True,
                "database_mutation": False,
                "paper_only": True,
                "shadow_only": True,
                "score_wired": False,
                "can_place_orders": False,
            }
        store = MarketFlowAbsorptionConsensusV2OosComparatorStore()
        try:
            result = store.compute()
            audit = store.audit()
        finally:
            store.close()
    return {
        "ok": bool(result.get("ok")) and bool(audit.get("ok")),
        "status": "absorption_consensus_v2_oos_comparator_manual_qa_complete",
        "shared_research_work_lock": True,
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
    print("=== MARKET FLOW V1 VS V2 OOS COMPARATOR LOCKED QA ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload.get("ok"):
        print("MARKET_FLOW_V1_VS_V2_OOS_COMPARATOR_LOCKED=FAIL")
        raise SystemExit(1)
    if payload.get("status") == "deferred_research_work_lock_busy":
        print("MARKET_FLOW_V1_VS_V2_OOS_COMPARATOR_LOCKED=DEFERRED")
        raise SystemExit(75)
    print("MARKET_FLOW_V1_VS_V2_OOS_COMPARATOR_LOCKED=PASS")


if __name__ == "__main__":
    main()
