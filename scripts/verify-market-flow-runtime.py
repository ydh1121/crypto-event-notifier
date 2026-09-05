from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_audit import audit_market_flow
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
    parser = argparse.ArgumentParser(description="Read-only runtime verification for public trade/orderbook flow observation.")
    parser.add_argument("--require-running", action="store_true")
    parser.add_argument("--require-data", action="store_true")
    args = parser.parse_args()

    now = time.time()
    status = _read_json(STATUS_PATH)
    components = status.get("components") if isinstance(status.get("components"), dict) else {}
    component = components.get("market-ohlcv-history") if isinstance(components.get("market-ohlcv-history"), dict) else {}
    last_result = component.get("last_result") if isinstance(component.get("last_result"), dict) else {}
    flow_result = last_result.get("market_flow") if isinstance(last_result.get("market_flow"), dict) else {}
    audit = audit_market_flow(now=now)

    supervisor_running = bool(status.get("running"))
    status_age = max(0.0, now - float(status.get("updated_at") or 0.0)) if status.get("updated_at") else None
    checks = {
        "supervisor_running": supervisor_running,
        "supervisor_status_fresh": bool(supervisor_running and status_age is not None and status_age <= 30.0),
        "component_registered": bool(component),
        "component_enabled": bool(component.get("enabled")),
        "component_not_degraded": str(component.get("status") or "") != "degraded",
        "paper_only": flow_result.get("paper_only", audit.get("paper_only", True)) is True,
        "cannot_place_orders": flow_result.get("can_place_orders", audit.get("can_place_orders")) is False,
        "score_unwired": flow_result.get("score_wired", audit.get("score_wired")) is False,
        "tables_ready": bool(audit.get("tables_ready")),
        "trade_data_ready": int(audit.get("trade_rows") or 0) > 0,
        "orderbook_data_ready": int(audit.get("orderbook_rows") or 0) > 0,
        "feature_data_ready": int(audit.get("feature_rows") or 0) > 0,
        "exchange_side_only": int(audit.get("invalid_side_rows") or 0) == 0 and int(audit.get("non_exchange_side_rows") or 0) == 0,
        "continuity_gate_clean": int(audit.get("complete_side_violations") or 0) == 0 and int(audit.get("complete_anchor_violations") or 0) == 0,
        "orderbook_gate_clean": int(audit.get("crossed_book_rows") or 0) == 0,
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False if audit.get("tables_ready") else True,
    }
    required = [
        "component_registered",
        "paper_only",
        "cannot_place_orders",
        "score_unwired",
        "exchange_side_only",
        "continuity_gate_clean",
        "orderbook_gate_clean",
        "raw_cloud_projection_disabled",
    ]
    if args.require_running:
        required += ["supervisor_running", "supervisor_status_fresh", "component_enabled", "component_not_degraded"]
    if args.require_data:
        required += ["tables_ready", "trade_data_ready", "orderbook_data_ready", "feature_data_ready"]

    passed = all(bool(checks[name]) for name in required)
    output = {
        "status": "runtime_verified" if passed else "runtime_verification_failed",
        "checks": checks,
        "component": {
            "status": str(component.get("status") or "offline"),
            "runs": int(component.get("runs") or 0),
            "interval_seconds": float(component.get("interval_seconds") or 0.0),
            "last_started_at": float(component.get("last_started_at") or 0.0),
            "last_finished_at": float(component.get("last_finished_at") or 0.0),
            "market_flow": flow_result,
        },
        "audit": audit,
        "read_only": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not passed:
        failed = [name for name in required if not checks.get(name)]
        raise SystemExit(f"MARKET_FLOW_RUNTIME=FAIL: {', '.join(failed)}")
    print("MARKET_FLOW_RUNTIME=PASS")


if __name__ == "__main__":
    main()
