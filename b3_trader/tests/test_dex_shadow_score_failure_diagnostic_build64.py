from pathlib import Path
from b3_trader.dex_shadow_score_failure_diagnostic import audit_dex_shadow_score_failure_diagnostic

def _row(case_key,asset,open_at,score,short,outcome):
    return {"case_key":case_key,"coingecko_id":asset,"domestic_open_at":open_at,"shadow_score":score,
            "components":{"pre_short_momentum":{"available":True,"signal":short,"points":short*22.5},"pre_medium_momentum":{"available":True,"signal":short*0.5,"points":short*5.0},"pre_acceleration":{"available":True,"signal":short*0.25,"points":short*1.875},"launch_continuity":{"available":False,"signal":None,"points":0.0}},
            "evaluation_only_outcomes":{"post_listing_returns_pct":{"p5m":outcome,"p1h":outcome,"p6h":outcome*2,"p24h":outcome*3,"p3d":outcome*4,"p7d":outcome*5}}}
def _score_payload():
    rows=[_row("a","asset-a",1,80,.8,-10),_row("b","asset-b",2,70,.6,-5),_row("c","asset-c",3,40,-.3,5),_row("d","asset-d",4,30,-.6,10)]
    return {"ok":True,"status":"scored_read_only","all_usable_cases_scored":True,"score_version":1,"score_name":"dex_prelisting_shadow_hypothesis_v1","case_scores":rows}
def _validation_payload():
    windows={w:{"labeled_count":4,"spearman":-.9,"quartiles":{"top_minus_bottom_mean_return_pct":-10.0}} for w in ("p1h","p6h","p24h")}
    return {"ok":True,"status":"validated_read_only","score_audit_ready":True,"event_level":{"windows":windows},"asset_level_dedup":{"windows":windows},"validation_protocol":{"all_criteria_pass":False,"criteria":{"event_positive_rank_signal":False,"asset_positive_rank_signal":False},"observed":{"strong_negative_core_windows":[{"level":"event","window":"p6h","spearman":-.9}]}}}
def test_diagnostic():
    result=audit_dex_shadow_score_failure_diagnostic(Path("unused"),score_audit_fn=lambda _: _score_payload(),validation_fn=lambda _: _validation_payload())
    assert result["ok"] is True and result["review"]["v1_reject_advisory"] is True
    assert result["component_direction_summary"]["pre_short_momentum"]["retrospective_contrarian_evidence"] is True
    assert result["score_formula_changed"] is False and result["mechanical_score_inversion_allowed"] is False
def test_fail_closed():
    result=audit_dex_shadow_score_failure_diagnostic(Path("unused"),score_audit_fn=lambda _: {"ok":False},validation_fn=lambda _: {"ok":False})
    assert result["ok"] is False and result["status"]=="upstream_blocked" and result["review"]["v2_design_allowed"] is False
