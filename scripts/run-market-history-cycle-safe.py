from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_ohlcv_research_cycle import (
    MAX_MARKETS_PER_EXCHANGE_PER_RUN,
    MAX_PREMIUM_MARKETS_PER_RUN,
    MarketOhlcvResearchCycle,
)
from b3_trader.research_work_lock import ResearchWorkLock


def run_once() -> dict:
    with ResearchWorkLock() as work_lock:
        if not work_lock.acquired:
            return {
                "ok": True,
                "status": "deferred_forward_research_work_lock_busy",
                "manual_market_history_qa": True,
                "paper_only": True,
                "shadow_only": True,
                "can_place_orders": False,
                "network_fetches": False,
                "database_mutation": False,
                "max_markets_per_exchange_per_run": MAX_MARKETS_PER_EXCHANGE_PER_RUN,
                "max_premium_markets_per_run": MAX_PREMIUM_MARKETS_PER_RUN,
            }
        cycle = MarketOhlcvResearchCycle()
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
    if result.get("can_modify_strategy") is not False:
        violations.append("can_modify_strategy")
    if int(result.get("markets_processed") or 0) > MAX_MARKETS_PER_EXCHANGE_PER_RUN * 2:
        violations.append("market_processing_bound")
    if int(result.get("max_premium_markets_per_run") or 0) > MAX_PREMIUM_MARKETS_PER_RUN:
        violations.append("premium_processing_bound")
    return {
        "ok": not violations,
        "status": "market_history_manual_qa_complete" if not violations else "market_history_manual_qa_contract_failed",
        "manual_market_history_qa": True,
        "shared_research_work_lock": True,
        "max_markets_per_exchange_per_run": MAX_MARKETS_PER_EXCHANGE_PER_RUN,
        "max_premium_markets_per_run": MAX_PREMIUM_MARKETS_PER_RUN,
        "violations": violations,
        "result": result,
    }


def main() -> None:
    payload = run_once()
    print("=== MARKET HISTORY LOCKED QA ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload.get("ok"):
        print("MARKET_HISTORY_LOCKED_CYCLE=FAIL")
        raise SystemExit(1)
    if payload.get("status") == "deferred_forward_research_work_lock_busy":
        print("MARKET_HISTORY_LOCKED_CYCLE=DEFERRED")
        raise SystemExit(75)
    print("MARKET_HISTORY_LOCKED_CYCLE=PASS")


if __name__ == "__main__":
    main()
