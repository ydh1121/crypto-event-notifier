from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_domestic_premium_audit import audit_market_domestic_premium
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
    parser = argparse.ArgumentParser(description="Read-only runtime verification for verified domestic premium/discount research.")
    parser.add_argument("--require-running", action="store_true")
    parser.add_argument("--require-data", action="store_true")
    args = parser.parse_args()

    now = time.time()
    status = _read_json(STATUS_PATH)
    components = status.get("components") if isinstance(status.get("components"), dict) else {}
    component = components.get("market-ohlcv-history") if isinstance(components.get("market-ohlcv-history"), dict) else {}
    last_result = component.get("last_result") if isinstance(component.get("last_result"), dict) else {}
    premium_result = last_result.get("domestic_premium") if isinstance(last_result.get("domestic_premium"), dict) else {}
    audit = audit_market_domestic_premium(now=now)

    supervisor_running = bool(status.get("running"))
    status_age = max(0.0, now - float(status.get("updated_at") or 0.0)) if status.get("updated_at") else None
    checks = {
        "supervisor_running": supervisor_running,
        "supervisor_status_fresh": bool(supervisor_running and status_age is not None and status_age <= 30.0),
        "component_registered": bool(component),
        "component_enabled": bool(component.get("enabled")),
        "component_not_degraded": str(component.get("status") or "") != "degraded",
        "paper_only": bool(premium_result.get("paper_only", audit.get("paper_only", True))),
        "cannot_place_orders": premium_result.get("can_place_orders", audit.get("can_place_orders")) is False,
        "score_unwired": premium_result.get("score_wired", audit.get("score_wired")) is False,
        "identity_gate_clean": int(audit.get("identity_gate_violations") or 0) == 0,
        "reference_values_complete": int(audit.get("reference_null_violations") or 0) == 0,
        "premium_values_complete": int(audit.get("premium_null_violations") or 0) == 0,
        "feature_table_ready": bool(audit.get("table_exists")),
        "computed_data_ready": int(audit.get("computed_rows") or 0) > 0,
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False if audit.get("table_exists") else True,
    }
    required = [
        "component_registered",
        "paper_only",
        "cannot_place_orders",
        "score_unwired",
        "identity_gate_clean",
        "reference_values_complete",
        "premium_values_complete",
        "raw_cloud_projection_disabled",
    ]
    if args.require_running:
        required += ["supervisor_running", "supervisor_status_fresh", "component_enabled", "component_not_degraded"]
    if args.require_data:
        required += ["feature_table_ready", "computed_data_ready"]

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
            "domestic_premium": premium_result,
        },
        "audit": audit,
        "read_only": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not passed:
        failed = [name for name in required if not checks.get(name)]
        raise SystemExit(f"MARKET_DOMESTIC_PREMIUM_RUNTIME=FAIL: {', '.join(failed)}")
    print("MARKET_DOMESTIC_PREMIUM_RUNTIME=PASS")


if __name__ == "__main__":
    main()
