from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_reaction import HORIZONS, MarketFlowReactionStore
from b3_trader.market_ohlcv_research_cycle import STATE_PATH
from b3_trader.research_control import STATUS_PATH


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only runtime verification for forward price-flow reaction evidence."
    )
    parser.add_argument("--require-running", action="store_true")
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()

    now = time.time()
    status = _read_json(STATUS_PATH)
    cycle_state = _read_json(STATE_PATH)
    components = status.get("components") if isinstance(status.get("components"), dict) else {}
    component = components.get("market-ohlcv-history") if isinstance(components.get("market-ohlcv-history"), dict) else {}
    last_result = component.get("last_result") if isinstance(component.get("last_result"), dict) else {}
    reaction_result = last_result.get("flow_reaction") if isinstance(last_result.get("flow_reaction"), dict) else {}
    cycle_contract = cycle_state.get("flow_reaction") if isinstance(cycle_state.get("flow_reaction"), dict) else {}

    store = MarketFlowReactionStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    supervisor_running = bool(status.get("running"))
    status_age = max(0.0, now - float(status.get("updated_at") or 0.0)) if status.get("updated_at") else None
    status_fresh = bool(supervisor_running and status_age is not None and status_age <= 30.0)
    component_status = str(component.get("status") or "offline")
    audit_horizons = set(str(value) for value in audit.get("horizons") or [])

    checks = {
        "supervisor_running": supervisor_running,
        "supervisor_status_fresh": status_fresh,
        "component_registered": bool(component),
        "component_enabled": bool(component.get("enabled")),
        "component_not_degraded": component_status != "degraded",
        "cycle_contract_registered": int(cycle_state.get("version") or 0) >= 7 and bool(cycle_contract),
        "cycle_contract_score_unwired": not bool(cycle_contract) or cycle_contract.get("score_wired") is False,
        "last_cycle_reaction_error_free": not bool(reaction_result) or reaction_result.get("ok") is True,
        "table_ready": audit.get("table_exists") is True,
        "data_present": int(audit.get("row_count") or 0) > 0,
        "ready_reactions_present": int(audit.get("ready_rows") or 0) > 0,
        "reaction_time_exact": int(audit.get("reaction_time_violations") or 0) == 0,
        "reaction_source_exact": int(audit.get("reaction_source_violations") or 0) == 0,
        "hypothesis_direction_exact": int(audit.get("hypothesis_direction_violations") or 0) == 0,
        "all_horizons_declared": set(HORIZONS).issubset(audit_horizons),
        "join_contract_declared": str(audit.get("join_contract") or "") == "forward_only_exact_contiguous_closed_ohlcv_after_signal_window",
        "paper_only": audit.get("paper_only") is True,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "score_unwired": audit.get("score_wired") is False,
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
    }

    required = [
        "reaction_time_exact",
        "reaction_source_exact",
        "hypothesis_direction_exact",
        "all_horizons_declared",
        "join_contract_declared",
        "paper_only",
        "cannot_place_orders",
        "score_unwired",
        "raw_cloud_projection_disabled",
    ]
    if args.require_running:
        required += [
            "supervisor_running",
            "supervisor_status_fresh",
            "component_registered",
            "component_enabled",
            "component_not_degraded",
            "cycle_contract_registered",
            "cycle_contract_score_unwired",
            "last_cycle_reaction_error_free",
        ]
    if args.require_data:
        required += ["table_ready", "data_present"]
    if args.require_ready:
        required += ["ready_reactions_present"]

    passed = all(bool(checks[name]) for name in required)
    output = {
        "status": "runtime_verified" if passed else "runtime_verification_failed",
        "checks": checks,
        "cycle_state": {
            "version": int(cycle_state.get("version") or 0),
            "updated_at": float(cycle_state.get("updated_at") or 0.0),
            "flow_reaction": cycle_contract,
        },
        "component": {
            "status": component_status,
            "interval_seconds": float(component.get("interval_seconds") or 0.0),
            "runs": int(component.get("runs") or 0),
            "last_started_at": float(component.get("last_started_at") or 0.0),
            "last_finished_at": float(component.get("last_finished_at") or 0.0),
            "last_result_flow_reaction": reaction_result,
        },
        "audit": audit,
        "read_only": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not passed:
        failed = [name for name in required if not checks.get(name)]
        raise SystemExit(f"MARKET_FLOW_REACTION_RUNTIME=FAIL: {', '.join(failed)}")
    print("MARKET_FLOW_REACTION_RUNTIME=PASS")


if __name__ == "__main__":
    main()
