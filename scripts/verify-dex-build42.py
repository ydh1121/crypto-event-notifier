from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_launch_audit import audit_dex_launch
from b3_trader.dex_launch_research_cycle import DexLaunchResearchCycle
from b3_trader.dex_launch_store import DexLaunchStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify local-only Build 42 DEX launch research")
    parser.add_argument("--collect", action="store_true", help="run one bounded public-source collection cycle")
    args = parser.parse_args()

    # The verifier owns only additive DEX research tables. On a fresh CI root,
    # initialize those tables before auditing; existing listing/PAPER rows are
    # never deleted or rewritten.
    schema = DexLaunchStore()
    schema.close()

    cycle_result = None
    if args.collect:
        cycle = DexLaunchResearchCycle()
        try:
            cycle_result = cycle.run_once()
        finally:
            cycle.close()

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
    )
    if not safe:
        raise SystemExit("DEX_BUILD42_RUNTIME=FAIL")
    print("DEX_BUILD42_RUNTIME=PASS")


if __name__ == "__main__":
    main()
