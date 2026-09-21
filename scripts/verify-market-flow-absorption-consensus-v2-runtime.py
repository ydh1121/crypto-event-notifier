from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_absorption_consensus_v2 import (
    CONSENSUS_WINDOW_LABEL,
    IDENTITY_BASIS,
    MarketFlowAbsorptionConsensusV2Store,
)
from b3_trader.market_flow_reliability import MarketFlowReliabilityStore
from b3_trader.market_price_flow_divergence import (
    MAX_ADVERSE_RETURN_BPS,
    MIN_REPLENISHMENT_PAIRS,
    MIN_REPLENISHMENT_RATIO,
    STRONG_DELTA_PCT,
)

EXPECTED_V1_THRESHOLDS = {
    "strong_delta_pct": 20.0,
    "max_adverse_return_bps": 20.0,
    "min_replenishment_ratio": 1.0,
    "min_replenishment_pairs": 5,
}


def verify(*, require_activation: bool, require_consensus: bool) -> tuple[bool, dict]:
    store = MarketFlowAbsorptionConsensusV2Store()
    try:
        audit = store.audit()
    finally:
        store.close()

    source = inspect.getsource(MarketFlowReliabilityStore.compute)
    due_pos = source.find("reaction_due_result = self._compute_reaction_due_stage")
    consensus_pos = source.find(
        "absorption_consensus_v2_result = self._compute_absorption_consensus_v2_stage"
    )
    base_pos = source.find("base_result = super().compute")
    automatic_code_contract = bool(
        due_pos >= 0
        and consensus_pos > due_pos
        and base_pos > consensus_pos
        and 'result["absorption_consensus_v2"] = absorption_consensus_v2_result' in source
    )
    actual_v1 = {
        "strong_delta_pct": float(STRONG_DELTA_PCT),
        "max_adverse_return_bps": float(MAX_ADVERSE_RETURN_BPS),
        "min_replenishment_ratio": float(MIN_REPLENISHMENT_RATIO),
        "min_replenishment_pairs": int(MIN_REPLENISHMENT_PAIRS),
    }
    checks = {
        "audit_ok": bool(audit.get("ok")),
        "automatic_cycle_code_contract": automatic_code_contract,
        "v1_thresholds_unchanged": actual_v1 == EXPECTED_V1_THRESHOLDS,
        "exact_5m_contract": audit.get("window_label") == CONSENSUS_WINDOW_LABEL,
        "identity_contract": audit.get("identity_basis") == IDENTITY_BASIS,
        "pre_activation_clean": int(audit.get("pre_activation_rows") or 0) == 0,
        "non_5m_clean": int(audit.get("non_5m_rows") or 0) == 0,
        "label_direction_clean": int(audit.get("invalid_label_or_direction_rows") or 0) == 0,
        "identity_rows_clean": int(audit.get("identity_violation_rows") or 0) == 0,
        "activation_consistent": int(audit.get("activation_mismatch_rows") or 0) == 0,
        "historical_v1_backfill_disabled": audit.get("historical_v1_backfill") is False,
        "v1_threshold_retuning_disabled": audit.get("v1_threshold_retuning") is False,
        "network_fetches_disabled": audit.get("network_fetches") is False,
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
        "paper_only": audit.get("paper_only") is True,
        "shadow_only": audit.get("shadow_only") is True,
        "score_unwired": audit.get("score_wired") is False,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "cannot_modify_strategy": audit.get("can_modify_strategy") is False,
    }
    if require_activation:
        checks["activation_present"] = audit.get("activation_present") is True
    if require_consensus:
        checks["consensus_present"] = int(audit.get("row_count") or 0) > 0

    ok = all(bool(value) for value in checks.values())
    payload = {
        "status": "runtime_verified" if ok else "runtime_failed",
        "checks": checks,
        "v1_thresholds": actual_v1,
        "activation_ts": audit.get("activation_ts"),
        "last_checked_at": audit.get("last_checked_at"),
        "consensus_rows": int(audit.get("row_count") or 0),
        "audit": audit,
        "historical_v1_backfill": False,
        "v1_threshold_retuning": False,
        "paper_only": True,
        "shadow_only": True,
        "score_wired": False,
        "can_place_orders": False,
    }
    return ok, payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-activation", action="store_true")
    parser.add_argument("--require-consensus", action="store_true")
    args = parser.parse_args()
    ok, payload = verify(
        require_activation=bool(args.require_activation),
        require_consensus=bool(args.require_consensus),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not ok:
        print("MARKET_FLOW_ABSORPTION_CONSENSUS_V2_RUNTIME=FAIL")
        raise SystemExit(1)
    print("MARKET_FLOW_ABSORPTION_CONSENSUS_V2_RUNTIME=PASS")


if __name__ == "__main__":
    main()
