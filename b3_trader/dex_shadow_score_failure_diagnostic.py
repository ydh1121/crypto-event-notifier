from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from .auto_demo_v2 import DB_PATH
from .dex_shadow_score import COMPONENT_WEIGHTS, OUTCOME_WINDOWS, audit_dex_shadow_scores
from .dex_shadow_score_validation import CORE_WINDOWS, audit_dex_shadow_score_validation

DIAGNOSTIC_VERSION = 1
DIAGNOSTIC_NAME = "dex_shadow_score_failure_diagnostic_v1"
MIN_DIRECTIONAL_RHO = 0.10
STRONG_DIRECTIONAL_RHO = 0.20
MIN_DIRECTIONAL_CORE_WINDOWS = 2

ScoreAuditFn = Callable[[Path | str], dict[str, Any]]
ValidationFn = Callable[[Path | str], dict[str, Any]]

def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None

def _rounded(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)

def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx, my = mean(xs), mean(ys)
    dx, dy = [x-mx for x in xs], [y-my for y in ys]
    denom = math.sqrt(sum(v*v for v in dx) * sum(v*v for v in dy))
    if denom <= 0.0:
        return None
    return sum(a*b for a,b in zip(dx,dy)) / denom

def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda idx: (values[idx], idx))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + 1 + end) / 2.0
        for pos in range(start, end):
            ranks[order[pos]] = rank
        start = end
    return ranks

def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    return _pearson(_ranks(xs), _ranks(ys))

def _outcome(row: dict[str, Any], window: str) -> float | None:
    outcomes = row.get("evaluation_only_outcomes")
    if isinstance(outcomes, dict):
        post = outcomes.get("post_listing_returns_pct")
        if isinstance(post, dict):
            value = _finite(post.get(window))
            if value is not None:
                return value
    post = row.get("post_listing_returns_pct")
    if isinstance(post, dict):
        return _finite(post.get(window))
    return None

def _component_signal(row: dict[str, Any], component: str) -> float | None:
    components = row.get("components")
    if not isinstance(components, dict):
        return None
    item = components.get(component)
    if not isinstance(item, dict) or not item.get("available"):
        return None
    return _finite(item.get("signal"))

def _leave_one_out_score(row: dict[str, Any], excluded: str) -> float | None:
    components = row.get("components")
    if not isinstance(components, dict):
        return None
    points, saw = 0.0, False
    for name, item in components.items():
        if name == excluded or not isinstance(item, dict) or not item.get("available"):
            continue
        value = _finite(item.get("points"))
        if value is not None:
            points += value
            saw = True
    return min(100.0, max(0.0, 50.0 + points)) if saw else None

def _quartile_stats(pairs: list[tuple[float,float]]) -> dict[str, Any]:
    if not pairs:
        return {"labeled_count":0,"quartile_size":0,"top_mean_return_pct":None,"bottom_mean_return_pct":None,"top_minus_bottom_mean_return_pct":None}
    ordered = sorted(pairs, key=lambda item:(item[0], item[1]))
    size = max(1, int(math.ceil(len(ordered)*0.25)))
    bottom, top = ordered[:size], ordered[-size:]
    top_mean, bottom_mean = mean(v for _,v in top), mean(v for _,v in bottom)
    return {"labeled_count":len(ordered),"quartile_size":size,"top_mean_return_pct":round(top_mean,6),"bottom_mean_return_pct":round(bottom_mean,6),"top_minus_bottom_mean_return_pct":round(top_mean-bottom_mean,6)}

def _signal_window_stats(rows: list[dict[str, Any]], window: str, signal_fn: Callable[[dict[str, Any]], float | None]) -> dict[str, Any]:
    pairs=[]
    for row in rows:
        signal, outcome = signal_fn(row), _outcome(row, window)
        if signal is not None and outcome is not None:
            pairs.append((signal,outcome))
    xs=[x for x,_ in pairs]; ys=[y for _,y in pairs]
    return {"labeled_count":len(pairs),"pearson":_rounded(_pearson(xs,ys)),"spearman":_rounded(_spearman(xs,ys)),"quartiles":_quartile_stats(pairs)}

def _component_metrics(rows: list[dict[str, Any]], component: str) -> dict[str, Any]:
    return {"row_count":len(rows),"available_count":sum(_component_signal(r,component) is not None for r in rows),"windows":{w:_signal_window_stats(rows,w,lambda r,n=component:_component_signal(r,n)) for w in OUTCOME_WINDOWS}}

def _leave_one_out_metrics(rows: list[dict[str, Any]], component: str) -> dict[str, Any]:
    return {"row_count":len(rows),"windows":{w:_signal_window_stats(rows,w,lambda r,n=component:_leave_one_out_score(r,n)) for w in OUTCOME_WINDOWS}}

def _chronological_late(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered=sorted(rows,key=lambda r:(float(_finite(r.get("domestic_open_at")) or 0.0),str(r.get("case_key") or r.get("asset_key") or "")))
    if not ordered: return []
    return ordered[max(1,len(ordered)//2):]

def _aggregate_assets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped=defaultdict(list)
    for row in rows:
        key=str(row.get("coingecko_id") or "").strip() or f"case:{row.get('case_key') or ''}"
        grouped[key].append(row)
    assets=[]
    for key in sorted(grouped):
        members=grouped[key]
        opens=[v for v in (_finite(r.get("domestic_open_at")) for r in members) if v is not None]
        components={}
        for component in COMPONENT_WEIGHTS:
            values=[v for v in (_component_signal(r,component) for r in members) if v is not None]
            components[component]={"available":bool(values),"signal":mean(values) if values else None}
        outcomes={}
        for window in OUTCOME_WINDOWS:
            values=[v for v in (_outcome(r,window) for r in members) if v is not None]
            outcomes[window]=mean(values) if values else None
        assets.append({"asset_key":key,"member_event_count":len(members),"domestic_open_at":min(opens) if opens else 0.0,"components":components,"post_listing_returns_pct":outcomes})
    return assets

def _direction_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    windows=metrics.get("windows") if isinstance(metrics.get("windows"),dict) else {}
    positive=[]; negative=[]; strong_negative=[]
    for window in CORE_WINDOWS:
        rho=_finite((windows.get(window) or {}).get("spearman"))
        if rho is None: continue
        if rho >= MIN_DIRECTIONAL_RHO: positive.append({"window":window,"spearman":round(rho,6)})
        if rho <= -MIN_DIRECTIONAL_RHO: negative.append({"window":window,"spearman":round(rho,6)})
        if rho <= -STRONG_DIRECTIONAL_RHO: strong_negative.append({"window":window,"spearman":round(rho,6)})
    classification="mixed_or_weak"
    if len(positive) >= MIN_DIRECTIONAL_CORE_WINDOWS:
        classification="continuation_supported_retrospectively"
    elif len(negative) >= MIN_DIRECTIONAL_CORE_WINDOWS:
        classification="contrarian_or_exhaustion_supported_retrospectively"
    return {"classification":classification,"positive_core_windows":positive,"negative_core_windows":negative,"strong_negative_core_windows":strong_negative}

def _whole_score_core(validation: dict[str, Any], key: str) -> dict[str, Any]:
    block=validation.get(key) if isinstance(validation.get(key),dict) else {}
    windows=block.get("windows") if isinstance(block.get("windows"),dict) else {}
    return {w:{"labeled_count":int((windows.get(w) or {}).get("labeled_count") or 0),"spearman":_finite((windows.get(w) or {}).get("spearman")),"spread_pct":_finite(((windows.get(w) or {}).get("quartiles") or {}).get("top_minus_bottom_mean_return_pct"))} for w in CORE_WINDOWS}

def audit_dex_shadow_score_failure_diagnostic(path: Path | str = DB_PATH, *, score_audit_fn: ScoreAuditFn = audit_dex_shadow_scores, validation_fn: ValidationFn = audit_dex_shadow_score_validation) -> dict[str, Any]:
    """Build64 read-only failure decomposition. Retrospective diagnostics may not be used as validation for a revised score."""
    db_path=Path(path)
    score_payload=score_audit_fn(db_path)
    validation=validation_fn(db_path)
    base={
        "ok":False,"diagnostic_version":DIAGNOSTIC_VERSION,"diagnostic_name":DIAGNOSTIC_NAME,
        "paper_only":True,"shadow_only":True,"can_place_orders":False,"paper_ab_wired":False,
        "read_only":True,"network_fetches":False,"database_mutation":False,"cloudflare_publishing":False,
        "strategy_signal_mutation":False,"position_sizing_mutation":False,
        "score_formula_changed":False,"score_weights_changed":False,"component_signs_changed":False,
        "training_or_fitting":False,"trade_threshold":None,
        "post_listing_outcomes_used_for_diagnostic_only":True,
        "retrospective_reweighting_allowed":False,"mechanical_score_inversion_allowed":False,
        "forward_validation_required_for_any_v2":True,"live_promotion_allowed":False,
    }
    score_ready=bool(score_payload.get("ok") and score_payload.get("status")=="scored_read_only" and score_payload.get("all_usable_cases_scored"))
    validation_ready=bool(validation.get("ok") and validation.get("status")=="validated_read_only" and validation.get("score_audit_ready"))
    if not score_ready or not validation_ready:
        return {**base,"status":"upstream_blocked","score_audit_ready":score_ready,"validation_ready":validation_ready,"review":{"next_action":"repair_build62_or_build63_before_failure_diagnostic","v1_reject_advisory":False,"v2_design_allowed":False}}
    rows=[r for r in score_payload.get("case_scores") or [] if isinstance(r,dict)]
    asset_rows=_aggregate_assets(rows)
    event_late=_chronological_late(rows); asset_late=_chronological_late(asset_rows)
    event_components={c:_component_metrics(rows,c) for c in COMPONENT_WEIGHTS}
    asset_components={c:_component_metrics(asset_rows,c) for c in COMPONENT_WEIGHTS}
    late_event_components={c:_component_metrics(event_late,c) for c in COMPONENT_WEIGHTS}
    late_asset_components={c:_component_metrics(asset_late,c) for c in COMPONENT_WEIGHTS}
    leave_one_out={c:_leave_one_out_metrics(rows,c) for c in COMPONENT_WEIGHTS}
    component_summary={}
    for c in COMPONENT_WEIGHTS:
        e=_direction_summary(event_components[c]); a=_direction_summary(asset_components[c]); le=_direction_summary(late_event_components[c]); la=_direction_summary(late_asset_components[c])
        component_summary[c]={
            "weight_frozen_v1":float(COMPONENT_WEIGHTS[c]),
            "event":e,"asset_dedup":a,"late_event":le,"late_asset_dedup":la,
            "retrospective_contrarian_evidence":e["classification"]=="contrarian_or_exhaustion_supported_retrospectively" and a["classification"]=="contrarian_or_exhaustion_supported_retrospectively",
            "retrospective_continuation_evidence":e["classification"]=="continuation_supported_retrospectively" and a["classification"]=="continuation_supported_retrospectively",
            "interpretation_is_diagnostic_only":True,
        }
    protocol=validation.get("validation_protocol") if isinstance(validation.get("validation_protocol"),dict) else {}
    criteria=protocol.get("criteria") if isinstance(protocol.get("criteria"),dict) else {}
    observed=protocol.get("observed") if isinstance(protocol.get("observed"),dict) else {}
    whole_score_failed=not bool(protocol.get("all_criteria_pass"))
    strong_negative=observed.get("strong_negative_core_windows")
    strong_negative_count=len(strong_negative) if isinstance(strong_negative,list) else 0
    contrarian_components=sorted(c for c,s in component_summary.items() if s.get("retrospective_contrarian_evidence"))
    continuation_components=sorted(c for c,s in component_summary.items() if s.get("retrospective_continuation_evidence"))
    v1_reject=bool(whole_score_failed and not criteria.get("event_positive_rank_signal") and not criteria.get("asset_positive_rank_signal") and strong_negative_count>0)
    return {
        **base,"ok":True,"status":"diagnosed_read_only","score_version":int(score_payload.get("score_version") or 0),"score_name":str(score_payload.get("score_name") or ""),
        "event_case_count":len(rows),"asset_count_dedup":len(asset_rows),
        "whole_score_core":{"event":_whole_score_core(validation,"event_level"),"asset_dedup":_whole_score_core(validation,"asset_level_dedup")},
        "component_event":event_components,"component_asset_dedup":asset_components,
        "component_late_event":late_event_components,"component_late_asset_dedup":late_asset_components,
        "leave_one_component_out_event":leave_one_out,"component_direction_summary":component_summary,
        "diagnostic_protocol":{
            "thresholds":{"core_windows":list(CORE_WINDOWS),"min_directional_spearman_rho":MIN_DIRECTIONAL_RHO,"strong_directional_spearman_rho":STRONG_DIRECTIONAL_RHO,"min_directional_core_windows":MIN_DIRECTIONAL_CORE_WINDOWS},
            "whole_score_validation_failed":whole_score_failed,"whole_score_strong_negative_core_count":strong_negative_count,
            "retrospective_contrarian_components":contrarian_components,"retrospective_continuation_components":continuation_components,
            "v1_reject_advisory":v1_reject,"v1_sign_flip_is_not_validated_v2":True,"leave_one_out_is_attribution_only":True,
        },
        "review":{"paper_ab_wired":False,"orders_changed":False,"existing_strategy_signal_changed":False,"position_sizing_changed":False,
                  "v1_reject_advisory":v1_reject,"v2_design_allowed":v1_reject,
                  "v2_must_be_declared_before_forward_data":True,"v2_must_not_claim_retrospective_validation":True,
                  "next_action":"retire_v1_then_design_preregistered_v2_for_forward_shadow_validation" if v1_reject else "inspect_component_failure_before_v1_disposition"},
    }
