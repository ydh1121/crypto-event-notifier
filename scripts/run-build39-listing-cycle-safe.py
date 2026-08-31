from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.listing_history_research_cycle import ListingHistoryResearchCycle, MAX_CASES_PER_RUN
from b3_trader.research_work_lock import ResearchWorkLock


def run_once() -> dict:
    with ResearchWorkLock() as work_lock:
        if not work_lock.acquired:
            return {
                "ok": True,
                "status": "deferred_forward_research_work_lock_busy",
                "manual_build39_qa": True,
                "paper_only": True,
                "shadow_only": True,
                "can_place_orders": False,
                "network_fetches": False,
                "database_mutation": False,
                "max_cases_per_run": MAX_CASES_PER_RUN,
            }
        cycle = ListingHistoryResearchCycle()
        try:
            result = cycle.run_once()
        finally:
            cycle.close()
    result = result if isinstance(result, dict) else {"status": "invalid_result"}
    violations: list[str] = []
    if result.get("paper_only") is not True:
        violations.append("paper_only")
    if result.get("can_place_orders") is not False:
        violations.append("can_place_orders")
    if int(result.get("processed") or 0) > MAX_CASES_PER_RUN:
        violations.append("processed_bound")
    return {
        "ok": not violations,
        "status": "build39_manual_qa_complete" if not violations else "build39_manual_qa_contract_failed",
        "manual_build39_qa": True,
        "shared_research_work_lock": True,
        "max_cases_per_run": MAX_CASES_PER_RUN,
        "violations": violations,
        "result": result,
    }


def main() -> None:
    payload = run_once()
    print("=== BUILD 39 LOCKED LISTING-HISTORY QA ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload.get("ok"):
        print("BUILD39_LOCKED_LISTING_CYCLE=FAIL")
        raise SystemExit(1)
    if payload.get("status") == "deferred_forward_research_work_lock_busy":
        print("BUILD39_LOCKED_LISTING_CYCLE=DEFERRED")
        raise SystemExit(75)
    print("BUILD39_LOCKED_LISTING_CYCLE=PASS")


if __name__ == "__main__":
    main()
