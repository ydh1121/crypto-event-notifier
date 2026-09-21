from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.forward_pipeline_orchestrator import ForwardPipelineOrchestrator
from b3_trader.forward_sample_intake import DEFAULT_PAGES_PER_EXCHANGE


def _compact(payload: dict) -> dict:
    keys = (
        "ok", "status", "build69_version", "build69_name", "paper_only", "shadow_only",
        "can_place_orders", "score_wired", "paper_ab_wired", "live_promotion_allowed",
        "forward_only", "read_only_plan", "network_fetches", "database_mutation",
        "forward_boundary", "bounds", "isolation", "safety", "steps", "summary",
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
        print("DEX_FORWARD_PIPELINE_ORCHESTRATOR_BUILD69_IMPORT=PASS")
        return

    orchestrator = ForwardPipelineOrchestrator(pages_per_exchange=args.pages)
    payload = orchestrator.run_once() if args.run else orchestrator.plan()
    print("=== DEX FORWARD PIPELINE ORCHESTRATOR BUILD 69 RUNTIME ===")
    print(json.dumps(_compact(payload), ensure_ascii=False, indent=2))

    expected = (
        {
            "waiting_no_forward_cases",
            "processed_forward_case",
            "candidate_not_processed",
            "intake_only_waiting_enrichment_candidate",
        }
        if args.run
        else {"planned"}
    )
    if not payload.get("ok") or payload.get("status") not in expected:
        raise SystemExit("DEX_FORWARD_PIPELINE_ORCHESTRATOR_BUILD69_RUNTIME=FAIL")
    if payload.get("can_place_orders") or payload.get("score_wired") or payload.get("paper_ab_wired"):
        raise SystemExit("DEX_FORWARD_PIPELINE_ORCHESTRATOR_BUILD69_RUNTIME=FAIL")
    if (payload.get("forward_boundary") or {}).get("pre_cutoff_cases_selectable"):
        raise SystemExit("DEX_FORWARD_PIPELINE_ORCHESTRATOR_BUILD69_RUNTIME=FAIL")
    print("DEX_FORWARD_PIPELINE_ORCHESTRATOR_BUILD69_RUNTIME=PASS")


if __name__ == "__main__":
    main()
