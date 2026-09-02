from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_full_cost_notional_sensitivity import (
    REFERENCE_NOTIONALS_KRW,
    MarketFlowFullCostNotionalSensitivityStore,
)


def verify(*, require_data: bool, require_paper_base: bool) -> tuple[bool, dict]:
    store = MarketFlowFullCostNotionalSensitivityStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    stats = list(audit.get("stats") or [])
    paper_base_ready = sum(
        int(row.get("ready_count") or 0)
        for row in stats
        if abs(float(row.get("reference_notional_krw") or 0.0) - 750_000.0) < 0.001
    )
    checks = {
        "audit_ok": bool(audit.get("ok")),
        "notional_contract_exact": audit.get("reference_notionals_krw") in (
            [], list(REFERENCE_NOTIONALS_KRW)
        ),
        "canonical_50k_baseline_exact": int(audit.get("baseline_50k_mismatch_count") or 0) == 0,
        "cost_monotonicity_clean": int(audit.get("cost_monotonicity_violations") or 0) == 0,
        "depth_monotonicity_clean": int(audit.get("depth_monotonicity_violations") or 0) == 0,
        "historical_ladder_backfill_disabled": audit.get("historical_ladder_backfill") is False,
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
        "paper_only": audit.get("paper_only") is True,
        "shadow_only": audit.get("shadow_only") is True,
        "score_unwired": audit.get("score_wired") is False,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "cannot_modify_strategy": audit.get("can_modify_strategy") is False,
    }
    if require_data:
        checks["sensitivity_data_present"] = int(audit.get("row_count") or 0) > 0
    if require_paper_base:
        checks["paper_base_750k_ready_present"] = paper_base_ready > 0

    ok = all(bool(value) for value in checks.values())
    payload = {
        "status": "runtime_verified" if ok else "runtime_failed",
        "checks": checks,
        "paper_base_750k_ready_count": paper_base_ready,
        "audit": audit,
        "paper_only": True,
        "shadow_only": True,
        "score_wired": False,
        "can_place_orders": False,
    }
    return ok, payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-paper-base", action="store_true")
    args = parser.parse_args()
    ok, payload = verify(
        require_data=bool(args.require_data),
        require_paper_base=bool(args.require_paper_base),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not ok:
        print("MARKET_FLOW_FULL_COST_NOTIONAL_SENSITIVITY_RUNTIME=FAIL")
        raise SystemExit(1)
    print("MARKET_FLOW_FULL_COST_NOTIONAL_SENSITIVITY_RUNTIME=PASS")


if __name__ == "__main__":
    main()
