from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_stream import DEFAULT_MARKETS, ENDPOINTS, STATUS_PATH
from b3_trader.market_flow_stream_store import MarketFlowStreamStore


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only runtime verification for the public WebSocket flow sidecar.")
    parser.add_argument("--require-running", action="store_true")
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-5m-continuity", action="store_true")
    args = parser.parse_args()

    now = time.time()
    status = _read_json(STATUS_PATH)
    store = MarketFlowStreamStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    updated_at = float(status.get("updated_at") or 0.0)
    age = max(0.0, now - updated_at) if updated_at > 0 else None
    exchanges = status.get("exchanges") if isinstance(status.get("exchanges"), dict) else {}
    markets = [str(value) for value in status.get("markets") or []]
    expected_pairs = {(exchange, market) for exchange in ENDPOINTS for market in DEFAULT_MARKETS}
    sessions = audit.get("sessions") if isinstance(audit.get("sessions"), list) else []
    session_pairs = {
        (str(row.get("exchange") or ""), str(row.get("market") or ""))
        for row in sessions
        if isinstance(row, dict)
    }
    latest_windows = audit.get("latest_windows") if isinstance(audit.get("latest_windows"), list) else []
    complete_5m = {
        (str(row.get("exchange") or ""), str(row.get("market") or ""))
        for row in latest_windows
        if isinstance(row, dict)
        and str(row.get("window_label") or "") == "5m"
        and bool(row.get("continuity_complete"))
    }

    checks = {
        "process_running": bool(status.get("running")),
        "status_fresh": bool(status.get("running") and age is not None and age <= 15.0),
        "process_lock_acquired": status.get("process_lock_acquired") is True,
        "public_network_only": status.get("network_public_only") is True,
        "authentication_unused": status.get("authentication_used") is False,
        "paper_only": status.get("paper_only") is True,
        "cannot_place_orders": status.get("can_place_orders") is False,
        "cannot_modify_strategy": status.get("can_modify_strategy") is False,
        "score_unwired": status.get("score_wired") is False,
        "raw_cloud_projection_disabled": status.get("raw_cloud_projection") is False,
        "benchmarks_configured": all(market in markets for market in DEFAULT_MARKETS),
        "exchange_states_present": all(exchange in exchanges for exchange in ENDPOINTS),
        "exchange_connections_live": all(bool((exchanges.get(exchange) or {}).get("connected")) for exchange in ENDPOINTS),
        "stream_tables_ready": bool(audit.get("tables_ready")),
        "benchmark_sessions_ready": expected_pairs.issubset(session_pairs),
        "minute_data_ready": int(audit.get("minute_rows") or 0) > 0,
        "window_data_ready": int(audit.get("window_rows") or 0) > 0,
        "exchange_side_only": int(audit.get("invalid_side_rows") or 0) == 0 and int(audit.get("non_exchange_side_rows") or 0) == 0,
        "five_minute_continuity_ready": expected_pairs.issubset(complete_5m),
    }

    required = [
        "process_lock_acquired",
        "public_network_only",
        "authentication_unused",
        "paper_only",
        "cannot_place_orders",
        "cannot_modify_strategy",
        "score_unwired",
        "raw_cloud_projection_disabled",
        "benchmarks_configured",
        "exchange_states_present",
        "stream_tables_ready",
        "exchange_side_only",
    ]
    if args.require_running:
        required += ["process_running", "status_fresh", "exchange_connections_live"]
    if args.require_data:
        required += ["benchmark_sessions_ready", "minute_data_ready", "window_data_ready"]
    if args.require_5m_continuity:
        required += ["five_minute_continuity_ready"]

    passed = all(bool(checks[name]) for name in required)
    output = {
        "status": "runtime_verified" if passed else "runtime_verification_failed",
        "checks": checks,
        "process": {
            "pid": int(status.get("pid") or 0),
            "started_at": float(status.get("started_at") or 0.0),
            "updated_at": updated_at,
            "status_age_seconds": age,
            "markets": markets,
            "exchanges": exchanges,
            "window_features_written": int(status.get("window_features_written") or 0),
            "last_feature_at": float(status.get("last_feature_at") or 0.0),
            "last_feature_error": str(status.get("last_feature_error") or ""),
        },
        "audit": audit,
        "read_only": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not passed:
        failed = [name for name in required if not checks.get(name)]
        raise SystemExit(f"MARKET_FLOW_STREAM_RUNTIME=FAIL: {', '.join(failed)}")
    print("MARKET_FLOW_STREAM_RUNTIME=PASS")


if __name__ == "__main__":
    main()
