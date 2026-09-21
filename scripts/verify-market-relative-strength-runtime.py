from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_relative_strength import BENCHMARK_MARKETS, HORIZON_DAYS
from b3_trader.market_relative_strength_audit import audit_market_relative_strength
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
    parser = argparse.ArgumentParser(description="Read-only runtime verification for BTC/ETH/breadth relative strength.")
    parser.add_argument("--require-running", action="store_true")
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-breadth-ready", action="store_true")
    args = parser.parse_args()

    now = time.time()
    status = _read_json(STATUS_PATH)
    components = status.get("components") if isinstance(status.get("components"), dict) else {}
    component = components.get("market-ohlcv-history") if isinstance(components.get("market-ohlcv-history"), dict) else {}
    last_result = component.get("last_result") if isinstance(component.get("last_result"), dict) else {}
    audit = audit_market_relative_strength(now=now)

    supervisor_running = bool(status.get("running"))
    status_age = max(0.0, now - float(status.get("updated_at") or 0.0)) if status.get("updated_at") else None
    status_fresh = bool(supervisor_running and status_age is not None and status_age <= 30.0)
    component_enabled = bool(component.get("enabled"))
    component_status = str(component.get("status") or "offline")
    exchanges = audit.get("exchanges") if isinstance(audit.get("exchanges"), dict) else {}

    benchmark_ready_by_exchange: dict[str, bool] = {}
    horizon_ready_by_exchange: dict[str, bool] = {}
    breadth_ready_by_exchange: dict[str, bool] = {}
    for exchange, item in exchanges.items():
        row = item if isinstance(item, dict) else {}
        benchmarks = row.get("benchmarks") if isinstance(row.get("benchmarks"), dict) else {}
        benchmark_ready_by_exchange[str(exchange)] = all(
            int((benchmarks.get(market) or {}).get("horizons") or 0) == len(HORIZON_DAYS)
            for market in BENCHMARK_MARKETS
        )
        horizon_ready_by_exchange[str(exchange)] = int(row.get("horizons") or 0) == len(HORIZON_DAYS)
        breadth_ready_by_exchange[str(exchange)] = int(row.get("breadth_ready_rows") or 0) > 0

    expected_exchanges = {"bithumb", "upbit"}
    data_ready = bool(
        audit.get("row_count")
        and expected_exchanges.issubset(set(exchanges.keys()))
        and all(benchmark_ready_by_exchange.get(exchange, False) for exchange in expected_exchanges)
        and all(horizon_ready_by_exchange.get(exchange, False) for exchange in expected_exchanges)
    )
    breadth_ready = bool(
        expected_exchanges.issubset(set(exchanges.keys()))
        and all(breadth_ready_by_exchange.get(exchange, False) for exchange in expected_exchanges)
    )

    checks = {
        "supervisor_running": supervisor_running,
        "supervisor_status_fresh": status_fresh,
        "component_registered": bool(component),
        "component_enabled": component_enabled,
        "component_not_degraded": component_status != "degraded",
        "paper_only": audit.get("paper_only") is True,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "feature_table_ready": audit.get("table_exists") is True,
        "benchmarks_ready": data_ready,
        "breadth_fail_closed": int(audit.get("breadth_null_violations") or 0) == 0,
        "score_unwired": not bool(audit.get("score_wiring_columns")),
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False if audit.get("table_exists") else True,
        "breadth_ready": breadth_ready,
    }

    required = [
        "paper_only",
        "cannot_place_orders",
        "breadth_fail_closed",
        "score_unwired",
        "raw_cloud_projection_disabled",
    ]
    if args.require_running:
        required += ["supervisor_running", "supervisor_status_fresh", "component_registered", "component_enabled", "component_not_degraded"]
    if args.require_data:
        required += ["feature_table_ready", "benchmarks_ready"]
    if args.require_breadth_ready:
        required += ["breadth_ready"]

    passed = all(bool(checks[name]) for name in required)
    output = {
        "status": "runtime_verified" if passed else "runtime_verification_failed",
        "checks": checks,
        "benchmark_ready_by_exchange": benchmark_ready_by_exchange,
        "breadth_ready_by_exchange": breadth_ready_by_exchange,
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
        raise SystemExit(f"MARKET_RELATIVE_STRENGTH_RUNTIME=FAIL: {', '.join(failed)}")
    print("MARKET_RELATIVE_STRENGTH_RUNTIME=PASS")


if __name__ == "__main__":
    main()
