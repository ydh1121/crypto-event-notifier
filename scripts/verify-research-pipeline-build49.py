from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.research_pipeline_accelerator import (  # noqa: E402
    DEFAULT_DEX_CASES,
    DEFAULT_LISTING_CYCLES,
    MAX_DEX_CASES,
    MAX_LISTING_CYCLES,
    ResearchPipelineAccelerator,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--listing-cycles", type=int, default=DEFAULT_LISTING_CYCLES)
    parser.add_argument("--dex-cases", type=int, default=DEFAULT_DEX_CASES)
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("RESEARCH_PIPELINE_BUILD49_IMPORT=PASS")
        return

    runner = ResearchPipelineAccelerator()
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
            payload["run"] = runner.run_once(
                listing_cycles=args.listing_cycles,
                dex_cases=args.dex_cases,
            )
    finally:
        runner.close()

    print("=== RESEARCH PIPELINE BUILD 49 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    safe = bool(
        payload["safety"]["paper_only"]
        and payload["safety"]["shadow_only"]
        and not payload["safety"]["can_place_orders"]
        and not payload["safety"]["score_wired"]
        and int(plan.get("listing", {}).get("max_cycles") or 0) == MAX_LISTING_CYCLES
        and int(plan.get("dex", {}).get("max_cases") or 0) == MAX_DEX_CASES
    )
    if args.run:
        result = payload.get("run") if isinstance(payload.get("run"), dict) else {}
        safe = bool(
            safe
            and result.get("paper_only")
            and result.get("shadow_only")
            and not result.get("can_place_orders")
            and not result.get("score_wired")
            and int(result.get("listing_cycles_budget") or DEFAULT_LISTING_CYCLES) <= MAX_LISTING_CYCLES
            and int(result.get("dex_cases_budget") or DEFAULT_DEX_CASES) <= MAX_DEX_CASES
        )
    if not safe:
        raise SystemExit("RESEARCH_PIPELINE_BUILD49_RUNTIME=FAIL")
    print("RESEARCH_PIPELINE_BUILD49_RUNTIME=PASS")


if __name__ == "__main__":
    main()
