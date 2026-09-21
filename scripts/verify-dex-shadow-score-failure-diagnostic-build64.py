from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from b3_trader.auto_demo_v2 import DB_PATH
from b3_trader.dex_shadow_score_failure_diagnostic import DIAGNOSTIC_NAME,DIAGNOSTIC_VERSION,MIN_DIRECTIONAL_CORE_WINDOWS,MIN_DIRECTIONAL_RHO,STRONG_DIRECTIONAL_RHO,audit_dex_shadow_score_failure_diagnostic

def _summary(payload: dict) -> dict:
    protocol=payload.get("diagnostic_protocol") if isinstance(payload.get("diagnostic_protocol"),dict) else {}
    review=payload.get("review") if isinstance(payload.get("review"),dict) else {}
    items=payload.get("component_direction_summary") if isinstance(payload.get("component_direction_summary"),dict) else {}
    components={}
    for name,item in items.items():
        if not isinstance(item,dict): continue
        components[name]={
            "weight_frozen_v1":item.get("weight_frozen_v1"),
            "event_classification":(item.get("event") or {}).get("classification"),
            "asset_classification":(item.get("asset_dedup") or {}).get("classification"),
            "late_event_classification":(item.get("late_event") or {}).get("classification"),
            "retrospective_contrarian_evidence":item.get("retrospective_contrarian_evidence"),
            "retrospective_continuation_evidence":item.get("retrospective_continuation_evidence"),
        }
    return {"ok":payload.get("ok"),"status":payload.get("status"),"diagnostic_version":payload.get("diagnostic_version"),"diagnostic_name":payload.get("diagnostic_name"),
            "score_version":payload.get("score_version"),"score_name":payload.get("score_name"),"paper_only":payload.get("paper_only"),"shadow_only":payload.get("shadow_only"),
            "can_place_orders":payload.get("can_place_orders"),"paper_ab_wired":payload.get("paper_ab_wired"),"read_only":payload.get("read_only"),
            "score_formula_changed":payload.get("score_formula_changed"),"score_weights_changed":payload.get("score_weights_changed"),"component_signs_changed":payload.get("component_signs_changed"),
            "training_or_fitting":payload.get("training_or_fitting"),"trade_threshold":payload.get("trade_threshold"),"event_case_count":payload.get("event_case_count"),"asset_count_dedup":payload.get("asset_count_dedup"),
            "whole_score_core":payload.get("whole_score_core"),"component_direction_summary":components,"diagnostic_protocol":protocol,"review":review}

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--db",default=str(DB_PATH)); parser.add_argument("--full",action="store_true"); parser.add_argument("--import-check",action="store_true"); args=parser.parse_args()
    if args.import_check:
        print("DEX_SHADOW_SCORE_FAILURE_DIAGNOSTIC_BUILD64_IMPORT=PASS"); return
    payload=audit_dex_shadow_score_failure_diagnostic(Path(args.db))
    print("=== DEX SHADOW SCORE FAILURE DIAGNOSTIC BUILD 64 RUNTIME ===")
    print(json.dumps(payload if args.full else _summary(payload),ensure_ascii=False,indent=2))
    protocol=payload.get("diagnostic_protocol") if isinstance(payload.get("diagnostic_protocol"),dict) else {}
    thresholds=protocol.get("thresholds") if isinstance(protocol.get("thresholds"),dict) else {}
    review=payload.get("review") if isinstance(payload.get("review"),dict) else {}
    safe=bool(payload.get("ok") and payload.get("status")=="diagnosed_read_only" and int(payload.get("diagnostic_version") or 0)==DIAGNOSTIC_VERSION and payload.get("diagnostic_name")==DIAGNOSTIC_NAME
              and payload.get("paper_only") and payload.get("shadow_only") and not payload.get("can_place_orders") and not payload.get("paper_ab_wired") and payload.get("read_only")
              and not payload.get("network_fetches") and not payload.get("database_mutation") and not payload.get("cloudflare_publishing") and not payload.get("strategy_signal_mutation")
              and not payload.get("position_sizing_mutation") and not payload.get("score_formula_changed") and not payload.get("score_weights_changed") and not payload.get("component_signs_changed")
              and not payload.get("training_or_fitting") and payload.get("trade_threshold") is None and not payload.get("retrospective_reweighting_allowed") and not payload.get("mechanical_score_inversion_allowed")
              and payload.get("forward_validation_required_for_any_v2") and not payload.get("live_promotion_allowed")
              and thresholds.get("min_directional_spearman_rho")==MIN_DIRECTIONAL_RHO and thresholds.get("strong_directional_spearman_rho")==STRONG_DIRECTIONAL_RHO
              and thresholds.get("min_directional_core_windows")==MIN_DIRECTIONAL_CORE_WINDOWS and isinstance(protocol.get("v1_reject_advisory"),bool)
              and protocol.get("v1_sign_flip_is_not_validated_v2") is True and protocol.get("leave_one_out_is_attribution_only") is True
              and review.get("paper_ab_wired") is False and review.get("orders_changed") is False and review.get("existing_strategy_signal_changed") is False and review.get("position_sizing_changed") is False)
    if not safe: raise SystemExit("DEX_SHADOW_SCORE_FAILURE_DIAGNOSTIC_BUILD64_RUNTIME=FAIL")
    print("DEX_SHADOW_SCORE_FAILURE_DIAGNOSTIC_BUILD64_RUNTIME=PASS")
if __name__=="__main__": main()
