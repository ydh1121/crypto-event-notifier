from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_temporal_diversity_backfill import (  # noqa: E402
    DEFAULT_MAX_CASES_PER_RUN,
    MAX_CASES_PER_RUN,
    DexTemporalDiversityBackfillRunner,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--max-cases", type=int, default=DEFAULT_MAX_CASES_PER_RUN)
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("DEX_TEMPORAL_DIVERSITY_BUILD57_IMPORT=PASS")
        return

    runner = DexTemporalDiversityBackfillRunner()
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
            payload["run"] = runner.run_once(max_cases=args.max_cases)
    finally:
        runner.close()

    print("=== DEX TEMPORAL DIVERSITY BUILD 57 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    safe = bool(
        payload["safety"]["paper_only"]
        and payload["safety"]["shadow_only"]
        and not payload["safety"]["can_place_orders"]
        and not payload["safety"]["score_wired"]
        and int(plan.get("max_cases_per_run") or 0) == MAX_CASES_PER_RUN
        and bool(plan.get("policy", {}).get("verified_coingecko_identity_only"))
        and bool(plan.get("policy", {}).get("new_unique_asset_only"))
        and not bool(plan.get("policy", {}).get("july_fallback_execution_enabled"))
    )
    if args.run:
        result = payload.get("run") if isinstance(payload.get("run"), dict) else {}
        safe = bool(
            safe
            and result.get("paper_only")
            and result.get("shadow_only")
            and not result.get("can_place_orders")
            and not result.get("score_wired")
            and 0 <= int(result.get("processed") or 0) <= MAX_CASES_PER_RUN
        )
    if not safe:
        raise SystemExit("DEX_TEMPORAL_DIVERSITY_BUILD57_RUNTIME=FAIL")
    print("DEX_TEMPORAL_DIVERSITY_BUILD57_RUNTIME=PASS")


if __name__ == "__main__":
    main()
