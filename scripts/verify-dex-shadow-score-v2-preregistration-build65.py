from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_shadow_score_v2_preregistration import declare_dex_shadow_score_v2_preregistration


def _compact(payload: dict) -> dict:
    return {
        "ok": bool(payload.get("ok")),
        "status": payload.get("status"),
        "preregistration_version": payload.get("preregistration_version"),
        "preregistration_name": payload.get("preregistration_name"),
        "paper_only": payload.get("paper_only"),
        "shadow_only": payload.get("shadow_only"),
        "can_place_orders": payload.get("can_place_orders"),
        "paper_ab_wired": payload.get("paper_ab_wired"),
        "read_only": payload.get("read_only"),
        "v2_score_wired": payload.get("v2_score_wired"),
        "forward_scorer_implemented": payload.get("forward_scorer_implemented"),
        "historical_rows_scored_as_v2": payload.get("historical_rows_scored_as_v2"),
        "historical_rows_eligible_for_v2_validation": payload.get("historical_rows_eligible_for_v2_validation"),
        "retrospective_validation_claimed": payload.get("retrospective_validation_claimed"),
        "mechanical_whole_score_inversion": payload.get("mechanical_whole_score_inversion"),
        "v1": payload.get("v1"),
        "v2": payload.get("v2"),
        "forward_boundary": payload.get("forward_boundary"),
        "forward_validation_protocol": payload.get("forward_validation_protocol"),
        "build64_design_motivation": payload.get("build64_design_motivation"),
        "review": payload.get("review"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()
    if args.import_check:
        print("DEX_SHADOW_SCORE_V2_PREREGISTRATION_BUILD65_IMPORT=PASS")
        return

    payload = declare_dex_shadow_score_v2_preregistration()
    print("=== DEX SHADOW SCORE V2 PREREGISTRATION BUILD 65 RUNTIME ===")
    print(json.dumps(_compact(payload), ensure_ascii=False, indent=2))
    if not payload.get("ok") or payload.get("status") != "v2_preregistered_forward_only":
        raise SystemExit("DEX_SHADOW_SCORE_V2_PREREGISTRATION_BUILD65_RUNTIME=FAIL")
    if not (payload.get("v1") or {}).get("retired"):
        raise SystemExit("DEX_SHADOW_SCORE_V2_PREREGISTRATION_BUILD65_RUNTIME=FAIL")
    if payload.get("historical_rows_scored_as_v2") or payload.get("paper_ab_wired") or payload.get("can_place_orders"):
        raise SystemExit("DEX_SHADOW_SCORE_V2_PREREGISTRATION_BUILD65_RUNTIME=FAIL")
    print("DEX_SHADOW_SCORE_V2_PREREGISTRATION_BUILD65_RUNTIME=PASS")


if __name__ == "__main__":
    main()
