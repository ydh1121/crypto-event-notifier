from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.cloudflare_snapshot_lifecycle import CloudflareSnapshotPublisher


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify compact listing-history Viewer projection")
    parser.add_argument("--publish", action="store_true", help="publish one authenticated Viewer snapshot")
    args = parser.parse_args()

    publisher = CloudflareSnapshotPublisher()
    snapshot = publisher.build_snapshot()
    public = snapshot.get("public") if isinstance(snapshot.get("public"), dict) else {}
    listing = public.get("listing_history") if isinstance(public.get("listing_history"), dict) else {}
    encoded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    result = {
        "ok": bool(listing) and listing.get("raw_candles_included") is False,
        "paper_only": bool(listing.get("paper_only", True)),
        "shadow_only": bool(listing.get("shadow_only", True)),
        "raw_candles_included": listing.get("raw_candles_included"),
        "case_count": int(listing.get("case_count") or 0),
        "source_count": int(listing.get("source_count") or 0),
        "feature_count": int(listing.get("feature_count") or 0),
        "projected_cases": len(listing.get("cases") or []),
        "snapshot_bytes": len(encoded),
        "under_snapshot_budget": len(encoded) < 1_800_000,
    }
    if args.publish:
        result["publish"] = publisher.publish_once()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"] or not result["under_snapshot_budget"]:
        raise SystemExit(1)
    if args.publish:
        published = result.get("publish") if isinstance(result.get("publish"), dict) else {}
        if str(published.get("status") or "") not in {"published", "not_configured"}:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
