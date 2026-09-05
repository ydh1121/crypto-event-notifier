from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.forward_sample_enrichment import ForwardSampleEnrichment


def _compact(payload: dict) -> dict:
    keys = (
        "ok", "status", "build68_version", "build68_name", "paper_only", "shadow_only",
        "can_place_orders", "score_wired", "network_fetches", "database_mutation",
        "forward_only", "forward_boundary", "bounds", "candidate_count", "preview",
        "processed", "usable_gain", "results", "isolation", "run_scope", "scope",
        "elapsed_seconds", "review",
    )
    return {key: payload.get(key) for key in keys if key in payload}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()
    if args.import_check:
        print("DEX_FORWARD_SAMPLE_ENRICHMENT_BUILD68_IMPORT=PASS")
        return

    runner = ForwardSampleEnrichment()
    payload = runner.run_once() if args.run else runner.plan()
    print("=== DEX FORWARD SAMPLE ENRICHMENT BUILD 68 RUNTIME ===")
    print(json.dumps(_compact(payload), ensure_ascii=False, indent=2))
    expected = {"enriched", "waiting_no_forward_cases"} if args.run else {"planned"}
    if not payload.get("ok") or payload.get("status") not in expected:
        raise SystemExit("DEX_FORWARD_SAMPLE_ENRICHMENT_BUILD68_RUNTIME=FAIL")
    if payload.get("can_place_orders") or payload.get("score_wired"):
        raise SystemExit("DEX_FORWARD_SAMPLE_ENRICHMENT_BUILD68_RUNTIME=FAIL")
    isolation = payload.get("isolation") or {}
    if isolation.get("generic_listing_history_run_once_called") or isolation.get("generic_dex_launch_run_once_called"):
        raise SystemExit("DEX_FORWARD_SAMPLE_ENRICHMENT_BUILD68_RUNTIME=FAIL")
    boundary = payload.get("forward_boundary") or {}
    if int(boundary.get("pre_cutoff_cases_processed") or 0) != 0:
        raise SystemExit("DEX_FORWARD_SAMPLE_ENRICHMENT_BUILD68_RUNTIME=FAIL")
    print("DEX_FORWARD_SAMPLE_ENRICHMENT_BUILD68_RUNTIME=PASS")


if __name__ == "__main__":
    main()
