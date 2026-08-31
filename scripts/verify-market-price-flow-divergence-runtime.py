from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_price_flow_divergence import MarketPriceFlowDivergenceStore
from b3_trader.research_control import STATUS_PATH

EXPECTED_EXCHANGES = {"bithumb", "upbit"}
EXPECTED_MARKETS = {"KRW-BTC", "KRW-ETH"}
EXPECTED_PAIRS = {(exchange, market) for exchange in EXPECTED_EXCHANGES for market in EXPECTED_MARKETS}


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
        description="Read-only runtime verification for aligned price-flow divergence/absorption evidence."
    )
    parser.add_argument("--require-running", action="store_true")
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-5m-data", action="store_true")
    args = parser.parse_args()

    now = time.time()
    status = _read_json(STATUS_PATH)
    components = status.get("components") if isinstance(status.get("components"), dict) else {}
    component = components.get("market-ohlcv-history") if isinstance(components.get("market-ohlcv-history"), dict) else {}
    last_result = component.get("last_result") if isinstance(component.get("last_result"), dict) else {}

    store = MarketPriceFlowDivergenceStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    supervisor_running = bool(status.get("running"))
    status_age = max(0.0, now - float(status.get("updated_at") or 0.0)) if status.get("updated_at") else None
    status_fresh = bool(supervisor_running and status_age is not None and status_age <= 30.0)
    component_status = str(component.get("status") or "offline")
    latest_ready = audit.get("latest_ready") if isinstance(audit.get("latest_ready"), list) else []
    ready_5m_pairs = {
        (str(row.get("exchange") or ""), str(row.get("market") or ""))
        for row in latest_ready
        if isinstance(row, dict)
        and str(row.get("window_label") or "") == "5m"
        and bool(row.get("data_ready"))
    }
    candidate_rows = [
        row
        for row in latest_ready
        if isinstance(row, dict)
        and (
            bool(row.get("passive_buy_absorption_candidate"))
            or bool(row.get("passive_sell_absorption_candidate"))
        )
    ]

    price_flow_result = last_result.get("price_flow_divergence") if isinstance(last_result.get("price_flow_divergence"), dict) else {}
    checks = {
        "supervisor_running": supervisor_running,
        "supervisor_status_fresh": status_fresh,
        "component_registered": bool(component),
        "component_enabled": bool(component.get("enabled")),
        "component_not_degraded": component_status != "degraded",
        "cycle_price_flow_present": bool(price_flow_result),
        "cycle_price_flow_error_free": not bool(price_flow_result) or price_flow_result.get("ok") is True,
        "table_ready": audit.get("table_exists") is True,
        "data_ready": int(audit.get("ready_rows") or 0) > 0,
        "five_minute_benchmarks_ready": EXPECTED_PAIRS.issubset(ready_5m_pairs),
        "exact_price_alignment": int(audit.get("alignment_violations") or 0) == 0,
        "continuous_sources_only": int(audit.get("continuity_violations") or 0) == 0,
        "join_contract_declared": str(audit.get("join_contract") or "").startswith("exact_aligned_closed_ohlcv+continuous_ws_trade+continuous_ws_orderbook"),
        "paper_only": audit.get("paper_only") is True,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "score_unwired": audit.get("score_wired") is False,
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
    }

    required = [
        "exact_price_alignment",
        "continuous_sources_only",
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
            "cycle_price_flow_present",
            "cycle_price_flow_error_free",
        ]
    if args.require_data:
        required += ["table_ready", "data_ready"]
    if args.require_5m_data:
        required += ["five_minute_benchmarks_ready"]

    passed = all(bool(checks[name]) for name in required)
    output = {
        "status": "runtime_verified" if passed else "runtime_verification_failed",
        "checks": checks,
        "ready_5m_pairs": sorted([f"{exchange}:{market}" for exchange, market in ready_5m_pairs]),
        "latest_absorption_candidates": candidate_rows,
        "component": {
            "status": component_status,
            "interval_seconds": float(component.get("interval_seconds") or 0.0),
            "runs": int(component.get("runs") or 0),
            "last_started_at": float(component.get("last_started_at") or 0.0),
            "last_finished_at": float(component.get("last_finished_at") or 0.0),
            "last_result_price_flow_divergence": price_flow_result,
        },
        "audit": audit,
        "read_only": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not passed:
        failed = [name for name in required if not checks.get(name)]
        raise SystemExit(f"MARKET_PRICE_FLOW_DIVERGENCE_RUNTIME=FAIL: {', '.join(failed)}")
    print("MARKET_PRICE_FLOW_DIVERGENCE_RUNTIME=PASS")


if __name__ == "__main__":
    main()
