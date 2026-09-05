from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_absorption_consensus_v2_oos_comparator import (
    COMPARISON_POLICY,
    CONFIRMATION_MIN_EVENTS_PER_SIDE,
    OBSERVATION_MIN_EVENTS_PER_SIDE,
    REFERENCE_NOTIONAL_KRW,
    MarketFlowAbsorptionConsensusV2OosComparatorStore,
)


def source_contract() -> dict:
    reliability = (ROOT / "b3_trader" / "market_flow_reliability.py").read_text(encoding="utf-8")
    comparator = (ROOT / "b3_trader" / "market_flow_absorption_consensus_v2_oos_comparator.py").read_text(encoding="utf-8")
    return {
        "automatic_cycle_code_contract": (
            "MarketFlowAbsorptionConsensusV2OosComparatorStore" in reliability
            and "market_flow_absorption_consensus_v2_oos_comparator" in reliability
        ),
        "separate_comparator_activation_contract": (
            "research_market_flow_absorption_consensus_v2_oos_comparator_control_mx" in comparator
            and "v2_forward_activation_ts" in comparator
        ),
        "v1_750k_exact_contract": "REFERENCE_NOTIONAL_KRW = 750_000.0" in comparator,
        "v1_outcome_blind_cluster_contract": "fixed_anchor_reaction_overlap+earliest_per_exchange+750k+outcome_blind" in comparator,
        "cross_exchange_only_contract": "cross_exchange_only+750k_full_cost" in comparator,
        "historical_backfill_disabled_contract": '"historical_comparison_backfill": False' in comparator,
        "winner_selection_disabled_contract": '"winner_selection_enabled": False' in comparator,
        "score_unwired_contract": '"score_wired": False' in comparator,
        "can_place_orders_false_contract": '"can_place_orders": False' in comparator,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-activation", action="store_true")
    args = parser.parse_args()

    contract = source_contract()
    store = MarketFlowAbsorptionConsensusV2OosComparatorStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    required = all(contract.values()) and bool(audit.get("ok"))
    if args.require_activation:
        required = required and bool(audit.get("activation_present"))

    payload = {
        "ok": required,
        "contract": contract,
        "reference_notional_krw": REFERENCE_NOTIONAL_KRW,
        "comparison_policy": COMPARISON_POLICY,
        "observation_min_events_per_side": OBSERVATION_MIN_EVENTS_PER_SIDE,
        "confirmation_min_events_per_side": CONFIRMATION_MIN_EVENTS_PER_SIDE,
        "audit": audit,
        "paper_only": True,
        "shadow_only": True,
        "score_wired": False,
        "can_place_orders": False,
    }
    print("=== MARKET FLOW V1 VS V2 OOS COMPARATOR RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if required:
        print("MARKET_FLOW_V1_VS_V2_OOS_COMPARATOR_RUNTIME=PASS")
        return
    print("MARKET_FLOW_V1_VS_V2_OOS_COMPARATOR_RUNTIME=FAIL")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
