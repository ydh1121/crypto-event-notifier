from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_shadow_score_v2_forward_validation import (
    audit_dex_shadow_score_v2_forward_validation,
)


def _compact(payload: dict) -> dict:
    return {
        "ok": bool(payload.get("ok")),
        "status": payload.get("status"),
        "build71_version": payload.get("build71_version"),
        "build71_name": payload.get("build71_name"),
        "score_version": payload.get("score_version"),
        "score_name": payload.get("score_name"),
        "paper_only": payload.get("paper_only"),
        "shadow_only": payload.get("shadow_only"),
        "can_place_orders": payload.get("can_place_orders"),
        "score_wired": payload.get("score_wired"),
        "paper_ab_wired": payload.get("paper_ab_wired"),
        "live_promotion_allowed": payload.get("live_promotion_allowed"),
        "read_only": payload.get("read_only"),
        "network_fetches": payload.get("network_fetches"),
        "database_mutation": payload.get("database_mutation"),
        "training_or_fitting": payload.get("training_or_fitting"),
        "trade_threshold": payload.get("trade_threshold"),
        "validation_statistics_calculated": payload.get("validation_statistics_calculated"),
        "forward_only": payload.get("forward_only"),
        "forward_boundary": payload.get("forward_boundary"),
        "isolation": payload.get("isolation"),
        "sample_ledger": payload.get("sample_ledger"),
        "sample_integrity": payload.get("sample_integrity"),
        "validation_protocol": payload.get("validation_protocol"),
        "validation_gate": payload.get("validation_gate"),
        "statistics": payload.get("statistics"),
        "review": payload.get("review"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()
    if args.import_check:
        print("DEX_SHADOW_SCORE_V2_FORWARD_VALIDATION_BUILD71_IMPORT=PASS")
        return

    payload = audit_dex_shadow_score_v2_forward_validation()
    print("=== DEX SHADOW SCORE V2 FORWARD VALIDATION BUILD 71 RUNTIME ===")
    print(json.dumps(_compact(payload), ensure_ascii=False, indent=2))

    allowed_statuses = {
        "waiting_for_forward_sample",
        "forward_validation_passed",
        "forward_validation_failed",
    }
    if not payload.get("ok") or payload.get("status") not in allowed_statuses:
        raise SystemExit("DEX_SHADOW_SCORE_V2_FORWARD_VALIDATION_BUILD71_RUNTIME=FAIL")
    if payload.get("paper_ab_wired") or payload.get("can_place_orders") or payload.get("live_promotion_allowed"):
        raise SystemExit("DEX_SHADOW_SCORE_V2_FORWARD_VALIDATION_BUILD71_RUNTIME=FAIL")
    if payload.get("status") == "waiting_for_forward_sample":
        if payload.get("validation_statistics_calculated") or payload.get("statistics") is not None:
            raise SystemExit("DEX_SHADOW_SCORE_V2_FORWARD_VALIDATION_BUILD71_RUNTIME=FAIL")
        if (payload.get("validation_gate") or {}).get("build72_parallel_paper_ab_allowed"):
            raise SystemExit("DEX_SHADOW_SCORE_V2_FORWARD_VALIDATION_BUILD71_RUNTIME=FAIL")
    else:
        if payload.get("validation_statistics_calculated") is not True:
            raise SystemExit("DEX_SHADOW_SCORE_V2_FORWARD_VALIDATION_BUILD71_RUNTIME=FAIL")
        passed = payload.get("status") == "forward_validation_passed"
        if bool((payload.get("validation_gate") or {}).get("build72_parallel_paper_ab_allowed")) != passed:
            raise SystemExit("DEX_SHADOW_SCORE_V2_FORWARD_VALIDATION_BUILD71_RUNTIME=FAIL")
    print("DEX_SHADOW_SCORE_V2_FORWARD_VALIDATION_BUILD71_RUNTIME=PASS")


if __name__ == "__main__":
    main()
