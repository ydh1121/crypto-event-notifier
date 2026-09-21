from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_launch_backfill import (  # noqa: E402
    MAX_CASES_PER_RUN,
    DexLaunchBackfillRunner,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="Execute bounded public-source backfill instead of plan-only mode.")
    parser.add_argument("--max-cases", type=int, default=1)
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("DEX_BACKFILL_BUILD46_IMPORT=PASS")
        return

    runner = DexLaunchBackfillRunner()
    try:
        plan = runner.plan(limit=12)
        payload = {
            "ok": True,
            "mode": "run" if args.run else "plan",
            "plan": {
                "candidate_count": int(plan.get("candidate_count") or 0),
                "supervisor_busy": bool(plan.get("supervisor_busy")),
                "max_cases_per_run": int(plan.get("max_cases_per_run") or 0),
                "retry_after_seconds": int(plan.get("retry_after_seconds") or 0),
                "quality": plan.get("quality") or {},
                "candidates": plan.get("candidates") or [],
            },
            "safety": {
                "paper_only": bool(plan.get("paper_only")),
                "shadow_only": bool(plan.get("shadow_only")),
                "can_place_orders": bool(plan.get("can_place_orders")),
                "score_wired": bool(plan.get("score_wired")),
            },
        }
        if args.run:
            payload["run"] = runner.run_once(max_cases=max(1, min(MAX_CASES_PER_RUN, int(args.max_cases))))

        print("=== DEX BACKFILL BUILD 46 RUNTIME ===")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        safe = bool(
            payload["safety"]["paper_only"]
            and payload["safety"]["shadow_only"]
            and not payload["safety"]["can_place_orders"]
            and not payload["safety"]["score_wired"]
            and payload["plan"]["max_cases_per_run"] == MAX_CASES_PER_RUN
        )
        if not safe:
            raise SystemExit("DEX_BACKFILL_BUILD46_RUNTIME=FAIL")
        print("DEX_BACKFILL_BUILD46_RUNTIME=PASS")
    finally:
        runner.close()


if __name__ == "__main__":
    main()
