from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.listing_history_accelerator import (  # noqa: E402
    DEFAULT_CYCLES_PER_RUN,
    MAX_CYCLES_PER_RUN,
    ListingHistoryAccelerator,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--cycles", type=int, default=DEFAULT_CYCLES_PER_RUN)
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("LISTING_ACCELERATOR_BUILD48_IMPORT=PASS")
        return

    runner = ListingHistoryAccelerator()
    try:
        plan = runner.plan()
        payload = {
            "ok": True,
            "mode": "run" if args.run else "plan",
            "plan": plan,
            "safety": {
                "paper_only": bool(plan.get("paper_only")),
                "shadow_only": bool(plan.get("shadow_only")),
                "can_place_orders": bool(plan.get("can_place_orders")),
                "score_wired": bool(plan.get("score_wired")),
            },
        }
        if args.run:
            payload["run"] = runner.run_once(cycles=args.cycles)
    finally:
        runner.close()

    print("=== LISTING ACCELERATOR BUILD 48 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    safe = bool(
        payload["safety"]["paper_only"]
        and payload["safety"]["shadow_only"]
        and not payload["safety"]["can_place_orders"]
        and not payload["safety"]["score_wired"]
        and int(plan.get("default_cycles_per_run") or 0) == DEFAULT_CYCLES_PER_RUN
        and int(plan.get("max_cycles_per_run") or 0) == MAX_CYCLES_PER_RUN
        and int(plan.get("cases_per_existing_cycle") or 0) == 3
        and int(plan.get("max_case_budget") or 0) == 12
    )
    if args.run:
        result = payload.get("run") if isinstance(payload.get("run"), dict) else {}
        safe = bool(
            safe
            and result.get("paper_only")
            and result.get("shadow_only")
            and not result.get("can_place_orders")
            and not result.get("score_wired")
            and int(result.get("requested_cycles") or 0) <= MAX_CYCLES_PER_RUN
            and int(result.get("case_budget") or 0) <= 12
        )
        if str(result.get("status") or "") == "supervisor_busy":
            safe = bool(safe and int(result.get("processed") or 0) == 0)
    if not safe:
        raise SystemExit("LISTING_ACCELERATOR_BUILD48_RUNTIME=FAIL")
    print("LISTING_ACCELERATOR_BUILD48_RUNTIME=PASS")


if __name__ == "__main__":
    main()
