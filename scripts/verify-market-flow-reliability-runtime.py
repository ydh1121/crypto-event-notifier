from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_flow_reliability import MarketFlowReliabilityStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-observation-ready", action="store_true")
    args = parser.parse_args()

    store = MarketFlowReliabilityStore()
    try:
        audit = store.audit()
    finally:
        store.close()

    checks = {
        "table_ready": bool(audit.get("table_exists")),
        "audit_ok": bool(audit.get("ok")),
        "paper_only": audit.get("paper_only") is True,
        "cannot_place_orders": audit.get("can_place_orders") is False,
        "score_unwired": audit.get("score_wired") is False and not audit.get("score_wiring_columns"),
        "raw_cloud_projection_disabled": audit.get("raw_cloud_projection") is False,
        "promotion_contract_clean": int(audit.get("promotion_contract_violations") or 0) == 0,
        "data_present": int(audit.get("row_count") or 0) > 0,
        "observation_ready_present": int(audit.get("observation_ready_rows") or 0) > 0,
    }
    required = [
        "table_ready","audit_ok","paper_only","cannot_place_orders","score_unwired",
        "raw_cloud_projection_disabled","promotion_contract_clean",
    ]
    if args.require_data:
        required.append("data_present")
    if args.require_observation_ready:
        required.append("observation_ready_present")

    ok = all(bool(checks[name]) for name in required)
    payload = {
        "status": "runtime_verified" if ok else "runtime_verification_failed",
        "checks": checks,
        "audit": audit,
        "read_only": True,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"MARKET_FLOW_RELIABILITY_RUNTIME={'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
