from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.cloudflare_snapshot_budget import MAX_BODY_BYTES, TARGET_BODY_BYTES, snapshot_bytes
from b3_trader.cloudflare_snapshot_lifecycle import CloudflareSnapshotPublisher


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    publisher = CloudflareSnapshotPublisher()
    snapshot = publisher.build_snapshot()
    public = snapshot.get("public") if isinstance(snapshot.get("public"), dict) else {}
    budget = public.get("snapshot_budget") if isinstance(public.get("snapshot_budget"), dict) else {}
    listing = public.get("listing_history") if isinstance(public.get("listing_history"), dict) else {}
    exchanges = public.get("exchanges") if isinstance(public.get("exchanges"), dict) else {}
    bithumb = exchanges.get("bithumb") if isinstance(exchanges.get("bithumb"), dict) else {}
    body_bytes = snapshot_bytes(snapshot)

    result = {
        "ok": bool(budget),
        "body_bytes": body_bytes,
        "target_body_bytes": TARGET_BODY_BYTES,
        "max_body_bytes": MAX_BODY_BYTES,
        "headroom_bytes": max(0, MAX_BODY_BYTES - body_bytes),
        "within_target": body_bytes <= TARGET_BODY_BYTES,
        "within_hard_limit": body_bytes <= MAX_BODY_BYTES,
        "compact_level": budget.get("compact_level"),
        "bytes_before": budget.get("bytes_before"),
        "bytes_after": budget.get("bytes_after"),
        "bithumb_root_markets": len(public.get("leaderboard") or []),
        "bithumb_exchange_duplicate_removed": (
            bool(bithumb.get("projection_inherits_root")) and "leaderboard" not in bithumb
        ),
        "upbit_markets": len(((exchanges.get("upbit") or {}).get("leaderboard") or [])),
        "bithumb_records_duplicate_removed": "bithumb" not in (public.get("exchange_records") or {}),
        "listing_cases": len(listing.get("cases") or []),
        "listing_case_count": int(listing.get("case_count") or 0),
        "listing_raw_candles_included": bool(listing.get("raw_candles_included", True)),
        "paper_only": bool(listing.get("paper_only", True)),
        "shadow_only": bool(listing.get("shadow_only", True)),
    }

    if args.publish:
        result["publish"] = publisher.publish_once()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    accepted = (
        result["ok"]
        and result["within_hard_limit"]
        and result["bithumb_exchange_duplicate_removed"]
        and result["bithumb_records_duplicate_removed"]
        and not result["listing_raw_candles_included"]
        and result["paper_only"]
        and result["shadow_only"]
    )
    if args.publish:
        accepted = accepted and (result.get("publish") or {}).get("status") == "published"
    if not accepted:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
