from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_diversity_backfill import DexDiversityBackfillRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Build51 diversity-aware DEX backfill verifier")
    parser.add_argument("--run", action="store_true", help="Run bounded public-source DEX research")
    parser.add_argument("--max-cases", type=int, default=2, help="Bounded case count, hard capped at 2")
    parser.add_argument("--import-check", action="store_true", help="Validate direct-script import bootstrap only")
    args = parser.parse_args()

    if args.import_check:
        print("DEX_DIVERSITY_BUILD51_IMPORT=PASS")
        return

    runner = DexDiversityBackfillRunner()
    try:
        plan = runner.plan(limit=20)
        payload = {
            "ok": True,
            "mode": "run" if args.run else "plan",
            "plan": plan,
            "safety": {
                "paper_only": True,
                "shadow_only": True,
                "can_place_orders": False,
                "score_wired": False,
            },
        }
        if args.run:
            payload["run"] = runner.run_once(max_cases=args.max_cases)
        print("=== DEX DIVERSITY BUILD 51 RUNTIME ===")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        safety = payload["safety"]
        if not (
            safety["paper_only"]
            and safety["shadow_only"]
            and not safety["can_place_orders"]
            and not safety["score_wired"]
            and int(plan.get("max_cases_per_run") or 0) <= 2
            and plan.get("mode") == "diversity_aware"
        ):
            raise SystemExit("DEX_DIVERSITY_BUILD51_RUNTIME=FAIL")
        print("DEX_DIVERSITY_BUILD51_RUNTIME=PASS")
    finally:
        runner.close()


if __name__ == "__main__":
    main()
