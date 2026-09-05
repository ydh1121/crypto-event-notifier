from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.historical_listing_backfill import (  # noqa: E402
    DEFAULT_PAGES_PER_EXCHANGE,
    MAX_PAGES_PER_EXCHANGE,
    HistoricalListingBackfill,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--pages", type=int, default=DEFAULT_PAGES_PER_EXCHANGE)
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("HISTORICAL_LISTING_BUILD47_IMPORT=PASS")
        return

    runner = HistoricalListingBackfill(pages_per_exchange=args.pages)
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
            "official_sources_only": bool(plan.get("official_sources_only")),
        },
    }
    if args.run:
        payload["run"] = runner.run_once()

    print("=== HISTORICAL LISTING BUILD 47 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    safe = bool(
        payload["safety"]["paper_only"]
        and payload["safety"]["shadow_only"]
        and not payload["safety"]["can_place_orders"]
        and not payload["safety"]["score_wired"]
        and payload["safety"]["official_sources_only"]
        and 1 <= int(plan.get("pages_per_exchange") or 0) <= MAX_PAGES_PER_EXCHANGE
        and int(plan.get("max_pages_per_exchange") or 0) == MAX_PAGES_PER_EXCHANGE
    )
    if args.run:
        result = payload.get("run") if isinstance(payload.get("run"), dict) else {}
        safe = bool(
            safe
            and result.get("paper_only")
            and result.get("shadow_only")
            and not result.get("can_place_orders")
            and not result.get("score_wired")
            and result.get("official_sources_only")
        )
    if not safe:
        raise SystemExit("HISTORICAL_LISTING_BUILD47_RUNTIME=FAIL")
    print("HISTORICAL_LISTING_BUILD47_RUNTIME=PASS")


if __name__ == "__main__":
    main()
