from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_absorption_consensus_v2_forward import (
    ENTRY_BOUNDARY_SECONDS,
    REFERENCE_NOTIONAL_KRW,
    MarketFlowAbsorptionConsensusV2ForwardStore,
)
from b3_trader.market_flow_reliability import MarketFlowReliabilityStore


def verify(*, require_activation: bool, require_forward_data: bool) -> tuple[bool, dict]:
    store = MarketFlowAbsorptionConsensusV2ForwardStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    source = inspect.getsource(MarketFlowReliabilityStore.compute)
    consensus_pos = source.find(
        "absorption_consensus_v2_result = self._compute_absorption_consensus_v2_stage"
    )
    forward_pos = source.find(
        "absorption_consensus_v2_forward_result = self._compute_absorption_consensus_v2_forward_stage"
    )
    base_pos = source.find("base_result = super().compute")
    automatic_code_contract = bool(
        consensus_pos >= 0
        and forward_pos > consensus_pos
        and base_pos > forward_pos
        and 'result["absorption_consensus_v2_forward"] = absorption_consensus_v2_forward_result' in source
    )

    checks = {
        "audit_ok": bool(audit.get("ok")),
        "automatic_cycle_code_contract": automatic_code_contract,
        "historical_consensus_backfill_disabled": audit.get("historical_consensus_backfill") is False,
        "causal_entry_contract": audit.get("entry_policy")
            == "strict_next_5m_boundary_after_consensus_recorded",
        "entry_boundary_exact": int(ENTRY_BOUNDARY_SECONDS) == 300,
        "reference_notional_750k_exact":
            abs(float(audit.get("reference_notional_krw") or 0.0) - REFERENCE_NOTIONAL_KRW) <= 0.000001,
        "pre_activation_clean": int(audit.get("pre_forward_activation_reaction_rows") or 0) == 0,
        "causal_entry_clean": int(audit.get("causal_entry_boundary_violations") or 0) == 0,
        "horizon_contract_clean": int(audit.get("horizon_contract_violations") or 0) == 0,
        "notional_contract_clean": int(audit.get("reference_notional_violations") or 0) == 0,
        "prior_only_ladder_clean": int(audit.get("prior_only_ladder_violations") or 0) == 0,
        "full_cost_formula_clean": int(audit.get("full_cost_formula_violations") or 0) == 0,
        "promotion_contract_clean": int(audit.get("promotion_contract_violations") or 0) == 0,
        "wiring_columns_clean": not audit.get("suspicious_wiring_columns"),
        "network_fetches_disabled": audit.get("network_fetches") is False,
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
        "paper_only": audit.get("paper_only") is True,
        "shadow_only": audit.get("shadow_only") is True,
        "probability_interpretation_disabled": audit.get("probability_interpretation") is False,
        "score_unwired": audit.get("score_wired") is False,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "cannot_modify_strategy": audit.get("can_modify_strategy") is False,
    }
    if require_activation:
        checks["activation_present"] = audit.get("activation_present") is True
    if require_forward_data:
        checks["forward_reaction_present"] = int(audit.get("reaction_rows") or 0) > 0

    ok = all(bool(value) for value in checks.values())
    payload = {
        "status": "runtime_verified" if ok else "runtime_failed",
        "checks": checks,
        "activation_ts": audit.get("activation_ts"),
        "consensus_source_rows_before_forward_activation":
            int(audit.get("consensus_source_rows_before_forward_activation") or 0),
        "consensus_source_rows_after_forward_activation":
            int(audit.get("consensus_source_rows_after_forward_activation") or 0),
        "reaction_rows": int(audit.get("reaction_rows") or 0),
        "reaction_ready_rows": int(audit.get("reaction_ready_rows") or 0),
        "full_cost_rows": int(audit.get("full_cost_rows") or 0),
        "full_cost_ready_rows": int(audit.get("full_cost_ready_rows") or 0),
        "event_rows": int(audit.get("event_rows") or 0),
        "ready_nonoverlap_event_rows": int(audit.get("ready_nonoverlap_event_rows") or 0),
        "reliability_rows": int(audit.get("reliability_rows") or 0),
        "promotion_ready_rows": int(audit.get("promotion_ready_rows") or 0),
        "audit": audit,
        "paper_only": True,
        "shadow_only": True,
        "score_wired": False,
        "can_place_orders": False,
    }
    return ok, payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-activation", action="store_true")
    parser.add_argument("--require-forward-data", action="store_true")
    args = parser.parse_args()
    ok, payload = verify(
        require_activation=bool(args.require_activation),
        require_forward_data=bool(args.require_forward_data),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not ok:
        print("MARKET_FLOW_ABSORPTION_CONSENSUS_V2_FORWARD_RUNTIME=FAIL")
        raise SystemExit(1)
    print("MARKET_FLOW_ABSORPTION_CONSENSUS_V2_FORWARD_RUNTIME=PASS")


if __name__ == "__main__":
    main()
