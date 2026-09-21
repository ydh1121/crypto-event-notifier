from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_orderbook_stream_store import MarketFlowOrderbookStreamStore
from b3_trader.market_flow_stream import DEFAULT_MARKETS, ENDPOINTS, STATUS_PATH


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only runtime verification for WebSocket orderbook replenishment features.")
    parser.add_argument("--require-running", action="store_true")
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-5m-continuity", action="store_true")
    args = parser.parse_args()

    now = time.time()
    status = _read_json(STATUS_PATH)
    store = MarketFlowOrderbookStreamStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    updated_at = float(status.get("updated_at") or 0.0)
    age = max(0.0, now - updated_at) if updated_at > 0 else None
    exchanges = status.get("exchanges") if isinstance(status.get("exchanges"), dict) else {}
    expected_pairs = {(exchange, market) for exchange in ENDPOINTS for market in DEFAULT_MARKETS}
    state_rows = audit.get("state_rows") if isinstance(audit.get("state_rows"), list) else []
    state_pairs = {
        (str(row.get("exchange") or ""), str(row.get("market") or ""))
        for row in state_rows
        if isinstance(row, dict)
    }
    latest_windows = audit.get("latest_windows") if isinstance(audit.get("latest_windows"), list) else []
    one_minute_pairs = {
        (str(row.get("exchange") or ""), str(row.get("market") or ""))
        for row in latest_windows
        if isinstance(row, dict)
        and str(row.get("window_label") or "") == "1m"
        and int(row.get("snapshot_count") or 0) > 0
    }
    complete_5m = {
        (str(row.get("exchange") or ""), str(row.get("market") or ""))
        for row in latest_windows
        if isinstance(row, dict)
        and str(row.get("window_label") or "") == "5m"
        and bool(row.get("continuity_complete"))
    }
    replenishment_pairs = {
        (str(row.get("exchange") or ""), str(row.get("market") or ""))
        for row in latest_windows
        if isinstance(row, dict)
        and str(row.get("window_label") or "") == "1m"
        and (
            int(row.get("bid_same_best_pairs") or 0) > 0
            or int(row.get("ask_same_best_pairs") or 0) > 0
        )
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
        "orderbook_scope_declared": str(status.get("orderbook_scope") or "") == "sampled_top5_same_best_price_replenishment_proxy",
        "exchange_connections_live": all(bool((exchanges.get(exchange) or {}).get("connected")) for exchange in ENDPOINTS),
        "orderbook_messages_live": all(int((exchanges.get(exchange) or {}).get("orderbook_messages") or 0) > 0 for exchange in ENDPOINTS),
        "orderbook_samples_live": all(int((exchanges.get(exchange) or {}).get("orderbook_samples") or 0) > 0 for exchange in ENDPOINTS),
        "orderbook_feature_error_free": not bool(status.get("last_orderbook_feature_error")),
        "orderbook_tables_ready": bool(audit.get("tables_ready")),
        "benchmark_orderbooks_ready": expected_pairs.issubset(state_pairs),
        "minute_data_ready": int(audit.get("minute_rows") or 0) > 0,
        "window_data_ready": int(audit.get("window_rows") or 0) > 0,
        "one_minute_features_ready": expected_pairs.issubset(one_minute_pairs),
        "replenishment_pairs_observed": expected_pairs.issubset(replenishment_pairs),
        "five_minute_continuity_ready": expected_pairs.issubset(complete_5m),
        "raw_orderbook_cloud_projection_disabled": audit.get("raw_orderbook_cloud_projection") is False,
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
        "orderbook_scope_declared",
        "orderbook_feature_error_free",
        "raw_orderbook_cloud_projection_disabled",
    ]
    if args.require_running:
        required += [
            "process_running",
            "status_fresh",
            "exchange_connections_live",
            "orderbook_messages_live",
            "orderbook_samples_live",
        ]
    if args.require_data:
        required += [
            "orderbook_tables_ready",
            "benchmark_orderbooks_ready",
            "minute_data_ready",
            "window_data_ready",
            "one_minute_features_ready",
            "replenishment_pairs_observed",
        ]
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
            "markets": [str(value) for value in status.get("markets") or []],
            "exchanges": exchanges,
            "orderbook_window_features_written": int(status.get("orderbook_window_features_written") or 0),
            "last_orderbook_feature_error": str(status.get("last_orderbook_feature_error") or ""),
            "orderbook_scope": str(status.get("orderbook_scope") or ""),
        },
        "audit": audit,
        "read_only": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not passed:
        failed = [name for name in required if not checks.get(name)]
        raise SystemExit(f"MARKET_FLOW_ORDERBOOK_RUNTIME=FAIL: {', '.join(failed)}")
    print("MARKET_FLOW_ORDERBOOK_RUNTIME=PASS")


if __name__ == "__main__":
    main()
