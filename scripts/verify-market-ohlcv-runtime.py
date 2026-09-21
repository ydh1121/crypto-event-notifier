from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_ohlcv_audit import audit_market_ohlcv
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
    parser = argparse.ArgumentParser(description="Read-only runtime verification for bounded KRW OHLCV history.")
    parser.add_argument("--require-running", action="store_true")
    parser.add_argument("--require-data", action="store_true")
    args = parser.parse_args()

    now = time.time()
    status = _read_json(STATUS_PATH)
    components = status.get("components") if isinstance(status.get("components"), dict) else {}
    component = components.get("market-ohlcv-history") if isinstance(components.get("market-ohlcv-history"), dict) else {}
    last_result = component.get("last_result") if isinstance(component.get("last_result"), dict) else {}
    audit = audit_market_ohlcv(now=now)

    supervisor_running = bool(status.get("running"))
    status_age = max(0.0, now - float(status.get("updated_at") or 0.0)) if status.get("updated_at") else None
    status_fresh = bool(supervisor_running and status_age is not None and status_age <= 30.0)
    component_enabled = bool(component.get("enabled"))
    component_status = str(component.get("status") or "offline")
    component_seen = bool(component)
    paper_only = bool(last_result.get("paper_only", status.get("paper_only", True)))
    cannot_place_orders = last_result.get("can_place_orders") is False
    database_scope_ok = str(last_result.get("database_scope") or "") in {
        "research_market_ohlcv_mx_only",
        "market_history_research_tables_only",
        "",
    }
    expected_timeframes = {"1m", "5m", "15m", "1h", "4h", "1d"}
    configured_timeframes = set(str(value) for value in last_result.get("timeframes", []) if value)
    timeframes_configured = not configured_timeframes or configured_timeframes == expected_timeframes
    audit_timeframes = set((audit.get("timeframes") or {}).keys())
    data_ready = bool(audit.get("row_count") and expected_timeframes.issubset(audit_timeframes))
    retention_ok = int(audit.get("retention_overflow_groups") or 0) == 0

    checks = {
        "supervisor_running": supervisor_running,
        "supervisor_status_fresh": status_fresh,
        "component_registered": component_seen,
        "component_enabled": component_enabled,
        "component_not_degraded": component_status not in {"degraded"},
        "paper_only": paper_only,
        "cannot_place_orders": cannot_place_orders,
        "database_scope_ok": database_scope_ok,
        "timeframes_configured": timeframes_configured,
        "retention_ok": retention_ok,
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False if audit.get("table_exists") else True,
        "data_ready": data_ready,
    }

    required = [
        "component_registered",
        "paper_only",
        "cannot_place_orders",
        "database_scope_ok",
        "timeframes_configured",
        "retention_ok",
        "raw_cloud_projection_disabled",
    ]
    if args.require_running:
        required += ["supervisor_running", "supervisor_status_fresh", "component_enabled", "component_not_degraded"]
    if args.require_data:
        required += ["data_ready"]

    passed = all(bool(checks[name]) for name in required)
    output = {
        "status": "runtime_verified" if passed and (not args.require_data or data_ready) else (
            "runtime_running_data_accumulating" if passed else "runtime_verification_failed"
        ),
        "checks": checks,
        "component": {
            "status": component_status,
            "interval_seconds": float(component.get("interval_seconds") or 0.0),
            "runs": int(component.get("runs") or 0),
            "last_started_at": float(component.get("last_started_at") or 0.0),
            "last_finished_at": float(component.get("last_finished_at") or 0.0),
            "last_result": last_result,
        },
        "audit": audit,
        "read_only": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not passed:
        failed = [name for name in required if not checks.get(name)]
        raise SystemExit(f"MARKET_OHLCV_RUNTIME=FAIL: {', '.join(failed)}")
    print("MARKET_OHLCV_RUNTIME=PASS")


if __name__ == "__main__":
    main()
