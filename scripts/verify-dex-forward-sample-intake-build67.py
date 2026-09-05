from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.forward_sample_intake import DEFAULT_PAGES_PER_EXCHANGE, ForwardSampleIntake


def _compact(payload: dict) -> dict:
    keys = (
        "ok", "status", "build67_version", "build67_name", "paper_only", "shadow_only",
        "can_place_orders", "score_wired", "read_only_plan", "network_fetches",
        "official_sources_only", "latest_pages_start_at", "pages_per_exchange",
        "hard_max_pages_per_exchange", "forward_boundary", "existing_forward_counts",
        "isolation", "run_scope", "scope", "source_results", "unique_forward_notices",
        "market_notices_inserted", "seed", "forward_counts_before", "forward_counts_after",
        "elapsed_seconds", "review",
    )
    return {key: payload.get(key) for key in keys if key in payload}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--pages", type=int, default=DEFAULT_PAGES_PER_EXCHANGE)
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()
    if args.import_check:
        print("DEX_FORWARD_SAMPLE_INTAKE_BUILD67_IMPORT=PASS")
        return

    intake = ForwardSampleIntake(pages_per_exchange=args.pages)
    payload = intake.run_once() if args.run else intake.plan()
    print("=== DEX FORWARD SAMPLE INTAKE BUILD 67 RUNTIME ===")
    print(json.dumps(_compact(payload), ensure_ascii=False, indent=2))
    expected = {"intake_complete", "intake_partial"} if args.run else {"planned"}
    if not payload.get("ok") or payload.get("status") not in expected:
        raise SystemExit("DEX_FORWARD_SAMPLE_INTAKE_BUILD67_RUNTIME=FAIL")
    isolation = payload.get("isolation") or {}
    if isolation.get("build47_historical_cursor_read") or isolation.get("build47_historical_cursor_mutation"):
        raise SystemExit("DEX_FORWARD_SAMPLE_INTAKE_BUILD67_RUNTIME=FAIL")
    if payload.get("can_place_orders") or payload.get("score_wired"):
        raise SystemExit("DEX_FORWARD_SAMPLE_INTAKE_BUILD67_RUNTIME=FAIL")
    print("DEX_FORWARD_SAMPLE_INTAKE_BUILD67_RUNTIME=PASS")


if __name__ == "__main__":
    main()
