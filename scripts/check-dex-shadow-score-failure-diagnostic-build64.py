from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"b3_trader"/"dex_shadow_score_failure_diagnostic.py"
VERIFY=ROOT/"scripts"/"verify-dex-shadow-score-failure-diagnostic-build64.py"
def main()->None:
    source=SOURCE.read_text(encoding="utf-8"); verify=VERIFY.read_text(encoding="utf-8")
    checks={
      "build64_build62_and_build63_frozen_inputs":"audit_dex_shadow_scores" in source and "audit_dex_shadow_score_validation" in source and '"score_formula_changed":False' in source and '"score_weights_changed":False' in source and '"component_signs_changed":False' in source,
      "build64_component_decomposition":'"component_event":event_components' in source and '"component_asset_dedup":asset_components' in source and '"component_direction_summary":component_summary' in source,
      "build64_late_half_sensitivity":'"component_late_event":late_event_components' in source and '"component_late_asset_dedup":late_asset_components' in source and "_chronological_late" in source,
      "build64_leave_one_out_attribution_only":'"leave_one_component_out_event":leave_one_out' in source and '"leave_one_out_is_attribution_only":True' in source,
      "build64_no_retrospective_reweight":'"retrospective_reweighting_allowed":False' in source and '"mechanical_score_inversion_allowed":False' in source and '"v1_sign_flip_is_not_validated_v2":True' in source,
      "build64_forward_v2_required":'"forward_validation_required_for_any_v2":True' in source and '"v2_must_be_declared_before_forward_data":True' in source and '"v2_must_not_claim_retrospective_validation":True' in source,
      "build64_paper_shadow_only":'"paper_only":True' in source and '"shadow_only":True' in source,
      "build64_no_orders":'"can_place_orders":False' in source and ".place_order(" not in source and " place_order(" not in source and ".submit_order(" not in source and " submit_order(" not in source,
      "build64_not_wired":'"paper_ab_wired":False' in source,
      "build64_read_only":'"read_only":True' in source and '"database_mutation":False' in source and "INSERT INTO" not in source and "UPDATE dex_" not in source and "DELETE FROM" not in source,
      "build64_no_network":'"network_fetches":False' in source,"build64_no_cloudflare":'"cloudflare_publishing":False' in source,
      "build64_no_strategy_mutation":'"strategy_signal_mutation":False' in source,"build64_no_position_sizing_mutation":'"position_sizing_mutation":False' in source,
      "build64_no_fitting":'"training_or_fitting":False' in source,"build64_no_trade_threshold":'"trade_threshold":None' in source,
      "build64_fixed_direction_protocol":'MIN_DIRECTIONAL_RHO = 0.10' in source and 'STRONG_DIRECTIONAL_RHO = 0.20' in source and 'MIN_DIRECTIONAL_CORE_WINDOWS = 2' in source,
      "build64_no_check_same_thread_override":"check_same_thread" not in source,
      "build64_runtime_verifier":"DEX_SHADOW_SCORE_FAILURE_DIAGNOSTIC_BUILD64_RUNTIME=PASS" in verify,
      "build64_direct_import_bootstrap":"DEX_SHADOW_SCORE_FAILURE_DIAGNOSTIC_BUILD64_IMPORT=PASS" in verify,
    }
    print("=== DEX SHADOW SCORE FAILURE DIAGNOSTIC BUILD 64 CONTRACT ==="); print(json.dumps(checks,ensure_ascii=False,indent=2))
    if not all(checks.values()): raise SystemExit("DEX_SHADOW_SCORE_FAILURE_DIAGNOSTIC_BUILD64=FAIL")
    print("DEX_SHADOW_SCORE_FAILURE_DIAGNOSTIC_BUILD64=PASS")
if __name__=="__main__": main()
