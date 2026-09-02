from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.market_fee_schedule import MarketFeeScheduleStore
from b3_trader.research_work_lock import ResearchWorkLock


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exchange", choices=("bithumb", "upbit"), required=True)
    parser.add_argument("--market-prefix", default="KRW")
    parser.add_argument("--profile", required=True)
    parser.add_argument(
        "--confirm-account-profile",
        action="store_true",
        help="Acknowledge that this profile matches the actual account state from this moment forward.",
    )
    args = parser.parse_args()

    if not args.confirm_account_profile:
        print(json.dumps({
            "ok": False,
            "status": "explicit_account_profile_confirmation_required",
            "exchange": args.exchange,
            "market_prefix": args.market_prefix.upper(),
            "profile": args.profile,
            "network_fetches": False,
            "paper_only": True,
            "shadow_only": True,
        }, ensure_ascii=False, indent=2))
        print("MARKET_FEE_PROFILE_SELECTION=FAIL")
        raise SystemExit(2)

    stamp = time.time()
    with ResearchWorkLock() as work_lock:
        if not work_lock.acquired:
            print(json.dumps({
                "ok": True,
                "status": "deferred_research_work_lock_busy",
                "shared_research_work_lock": True,
                "network_fetches": False,
                "database_mutation": False,
                "paper_only": True,
                "shadow_only": True,
            }, ensure_ascii=False, indent=2))
            print("MARKET_FEE_PROFILE_SELECTION=DEFERRED")
            raise SystemExit(75)

        store = MarketFeeScheduleStore()
        try:
            store.ensure_current_catalog(now=stamp)
            before = store.audit()
            store.set_active_profile(
                args.exchange,
                args.market_prefix,
                args.profile,
                source="manual_local_account_confirmation",
                now=stamp,
            )
            after = store.audit()
            resolved = store.resolve_taker_fee(
                args.exchange,
                f"{args.market_prefix.upper()}-BTC",
                stamp,
            )
        finally:
            store.close()

    payload = {
        "ok": bool(after.get("ok")) and resolved is not None,
        "status": "fee_profile_selected_forward_only",
        "exchange": args.exchange,
        "market_prefix": args.market_prefix.upper(),
        "profile": args.profile,
        "effective_from": stamp,
        "resolved_taker_fee_bps": None if resolved is None else resolved.get("taker_fee_bps"),
        "before_profile": before.get(f"{args.exchange}_krw_profile"),
        "after_profile": after.get(f"{args.exchange}_krw_profile"),
        "profile_selection_retroactive": False,
        "historical_fee_backfill": False,
        "network_fetches": False,
        "database_mutation": True,
        "paper_only": True,
        "shadow_only": True,
        "score_wired": False,
        "can_place_orders": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"MARKET_FEE_PROFILE_SELECTION={'PASS' if payload['ok'] else 'FAIL'}")
    raise SystemExit(0 if payload["ok"] else 1)


if __name__ == "__main__":
    main()
