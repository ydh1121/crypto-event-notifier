from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_shadow_score_v2_forward import audit_dex_shadow_score_v2_forward


def _compact(payload: dict) -> dict:
    return {
        "ok": bool(payload.get("ok")),
        "status": payload.get("status"),
        "forward_scorer_version": payload.get("forward_scorer_version"),
        "forward_scorer_name": payload.get("forward_scorer_name"),
        "score_version": payload.get("score_version"),
        "score_name": payload.get("score_name"),
        "paper_only": payload.get("paper_only"),
        "shadow_only": payload.get("shadow_only"),
        "can_place_orders": payload.get("can_place_orders"),
        "paper_ab_wired": payload.get("paper_ab_wired"),
        "score_wired": payload.get("score_wired"),
        "read_only": payload.get("read_only"),
        "network_fetches": payload.get("network_fetches"),
        "training_or_fitting": payload.get("training_or_fitting"),
        "trade_threshold": payload.get("trade_threshold"),
        "retrospective_validation_claimed": payload.get("retrospective_validation_claimed"),
        "forward_only": payload.get("forward_only"),
        "preregistration_ready": payload.get("preregistration_ready"),
        "forward_boundary": payload.get("forward_boundary"),
        "usable_case_count_total": payload.get("usable_case_count_total"),
        "usable_case_rows_found": payload.get("usable_case_rows_found"),
        "pre_cutoff_design_only_case_count": payload.get("pre_cutoff_design_only_case_count"),
        "forward_eligible_case_count": payload.get("forward_eligible_case_count"),
        "case_score_count": payload.get("case_score_count"),
        "all_forward_eligible_cases_scored": payload.get("all_forward_eligible_cases_scored"),
        "historical_rows_scored_as_v2": payload.get("historical_rows_scored_as_v2"),
        "historical_rows_eligible_for_v2_validation": payload.get("historical_rows_eligible_for_v2_validation"),
        "component_weights": payload.get("component_weights"),
        "excluded_components": payload.get("excluded_components"),
        "distribution": payload.get("distribution"),
        "confidence_distribution": payload.get("confidence_distribution"),
        "component_available_case_counts": payload.get("component_available_case_counts"),
        "missing_component_case_counts": payload.get("missing_component_case_counts"),
        "evaluation_label_available_case_counts": payload.get("evaluation_label_available_case_counts"),
        "preview": [
            {
                "case_key": row.get("case_key"),
                "domestic_open_at": row.get("domestic_open_at"),
                "shadow_score": row.get("shadow_score"),
                "confidence": row.get("confidence"),
                "missing_feature_flags": row.get("missing_feature_flags"),
            }
            for row in (payload.get("case_scores") or [])[:5]
            if isinstance(row, dict)
        ],
        "review": payload.get("review"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()
    if args.import_check:
        print("DEX_SHADOW_SCORE_V2_FORWARD_BUILD66_IMPORT=PASS")
        return

    payload = audit_dex_shadow_score_v2_forward()
    print("=== DEX SHADOW SCORE V2 FORWARD BUILD 66 RUNTIME ===")
    print(json.dumps(_compact(payload), ensure_ascii=False, indent=2))
    if not payload.get("ok"):
        raise SystemExit("DEX_SHADOW_SCORE_V2_FORWARD_BUILD66_RUNTIME=FAIL")
    if payload.get("status") not in {"forward_waiting_no_eligible_cases", "scored_forward_only"}:
        raise SystemExit("DEX_SHADOW_SCORE_V2_FORWARD_BUILD66_RUNTIME=FAIL")
    if payload.get("historical_rows_scored_as_v2") or payload.get("historical_rows_eligible_for_v2_validation"):
        raise SystemExit("DEX_SHADOW_SCORE_V2_FORWARD_BUILD66_RUNTIME=FAIL")
    if payload.get("can_place_orders") or payload.get("paper_ab_wired") or payload.get("score_wired"):
        raise SystemExit("DEX_SHADOW_SCORE_V2_FORWARD_BUILD66_RUNTIME=FAIL")
    if int(payload.get("case_score_count") or 0) != int(payload.get("forward_eligible_case_count") or 0):
        raise SystemExit("DEX_SHADOW_SCORE_V2_FORWARD_BUILD66_RUNTIME=FAIL")
    print("DEX_SHADOW_SCORE_V2_FORWARD_BUILD66_RUNTIME=PASS")


if __name__ == "__main__":
    main()
