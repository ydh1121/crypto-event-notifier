from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_launch_audit import audit_dex_launch
from b3_trader.dex_launch_research_cycle import DexLaunchResearchCycle
from b3_trader.dex_launch_store import DexLaunchStore


def _target_listing_case(store: DexLaunchStore, case_key: str) -> dict[str, Any] | None:
    key = str(case_key or "").strip()
    if not key:
        return None
    tables = {
        str(row["name"])
        for row in store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "listing_history_cases" not in tables:
        return None
    row = store.conn.execute(
        """
        SELECT case_key,domestic_exchange,domestic_market,symbol,domestic_open_at,
               identity_json,identity_verified,status AS listing_status
        FROM listing_history_cases
        WHERE case_key=?
          AND identity_verified=1
          AND status NOT IN ('rejected_identity','rejected_notice')
        LIMIT 1
        """,
        (key,),
    ).fetchone()
    if row is None:
        return None
    item = dict(row)
    try:
        item["identity"] = json.loads(str(item.pop("identity_json") or "{}"))
    except json.JSONDecodeError:
        item["identity"] = {}
    return item


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify local-only Build 42 DEX launch research")
    parser.add_argument("--collect", action="store_true", help="run one bounded public-source collection cycle")
    parser.add_argument(
        "--case-key",
        default="",
        help="QA only: run one exact listing case even when its normal retry cooldown has not expired",
    )
    args = parser.parse_args()

    # The verifier owns only additive DEX research tables. On a fresh CI root,
    # initialize those tables before auditing; existing listing/PAPER rows are
    # never deleted or rewritten.
    schema = DexLaunchStore()

    cycle_result = None
    try:
        if args.collect:
            cycle = DexLaunchResearchCycle(store=schema)
            try:
                if args.case_key:
                    target = _target_listing_case(schema, args.case_key)
                    if target is None:
                        cycle_result = {
                            "status": "target_case_missing",
                            "case_key": str(args.case_key),
                            "paper_only": True,
                            "shadow_only": True,
                            "can_place_orders": False,
                        }
                    else:
                        result = cycle._research_case(target, time.time())
                        cycle_result = {
                            "status": "targeted_research",
                            "paper_only": True,
                            "shadow_only": True,
                            "can_place_orders": False,
                            "case_key": str(args.case_key),
                            "processed": 1,
                            "results": [result],
                        }
                else:
                    cycle_result = cycle.run_once()
            finally:
                cycle.close()
    finally:
        schema.close()

    audit = audit_dex_launch()
    payload = {
        "ok": bool(audit.get("ok")),
        "paper_only": bool(audit.get("paper_only", True)),
        "can_place_orders": bool(audit.get("can_place_orders", False)),
        "raw_dex_candles_cloud_projected": bool(audit.get("raw_candles_cloud_projected", False)),
        "cycle": cycle_result,
        "audit": audit,
    }
    print("=== DEX BUILD 42 LOCAL VERIFY ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    safe = bool(
        payload["ok"]
        and payload["paper_only"]
        and not payload["can_place_orders"]
        and not payload["raw_dex_candles_cloud_projected"]
        and (not args.case_key or (cycle_result or {}).get("status") != "target_case_missing")
    )
    if not safe:
        raise SystemExit("DEX_BUILD42_RUNTIME=FAIL")
    print("DEX_BUILD42_RUNTIME=PASS")


if __name__ == "__main__":
    main()
