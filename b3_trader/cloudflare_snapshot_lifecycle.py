from __future__ import annotations

from typing import Any

from .cloudflare_snapshot_budget import apply_snapshot_budget
from .cloudflare_snapshot_publisher import (
    DEMO_DB_PATH,
    DEMO_STATUS_PATH,
    UPBIT_STATUS_PATH,
    CloudflareSnapshotPublisher as BaseCloudflareSnapshotPublisher,
    _read_json,
)
from .listing_history_snapshot import build_listing_history_snapshot


def _lifecycle_map(demo: dict[str, Any]) -> dict[str, str]:
    source = demo.get("leaderboard") if isinstance(demo.get("leaderboard"), list) else []
    return {
        str(row.get("market") or ""): str(row.get("lifecycle_state") or "NORMAL")
        for row in source
        if isinstance(row, dict) and row.get("market")
    }


def apply_lifecycle_projection(payload: dict[str, Any], demo: dict[str, Any]) -> None:
    states = _lifecycle_map(demo)
    for row in payload.get("leaderboard") or []:
        if not isinstance(row, dict):
            continue
        market = str(row.get("market") or "")
        if market:
            row["lifecycle_state"] = states.get(market, "NORMAL")
    best = payload.get("best_market") if isinstance(payload.get("best_market"), dict) else None
    if best is not None:
        market = str(best.get("market") or "")
        if market:
            best["lifecycle_state"] = states.get(market, "NORMAL")
    lifecycle = demo.get("market_lifecycle") if isinstance(demo.get("market_lifecycle"), dict) else {}
    payload["market_lifecycle"] = {
        "market_count": int(lifecycle.get("market_count") or 0),
        "counts": lifecycle.get("counts") if isinstance(lifecycle.get("counts"), dict) else {},
        "attention": lifecycle.get("attention") if isinstance(lifecycle.get("attention"), list) else [],
        "notice_only": lifecycle.get("notice_only") if isinstance(lifecycle.get("notice_only"), list) else [],
        "notice_state_count": int(lifecycle.get("notice_state_count") or 0),
        "notice_overlay": bool(lifecycle.get("notice_overlay")),
        "transitions": lifecycle.get("transitions") if isinstance(lifecycle.get("transitions"), list) else [],
        "shadow_only": True,
    }


class CloudflareSnapshotPublisher(BaseCloudflareSnapshotPublisher):
    """Viewer projection for lifecycle state and bounded compact research data."""

    def build_snapshot(self) -> dict[str, Any]:
        snapshot = super().build_snapshot()
        public = snapshot.get("public") if isinstance(snapshot.get("public"), dict) else {}
        exchanges = public.get("exchanges") if isinstance(public.get("exchanges"), dict) else {}
        bithumb_demo = _read_json(DEMO_STATUS_PATH)
        upbit_demo = _read_json(UPBIT_STATUS_PATH)

        bithumb_payload = exchanges.get("bithumb") if isinstance(exchanges.get("bithumb"), dict) else None
        upbit_payload = exchanges.get("upbit") if isinstance(exchanges.get("upbit"), dict) else None
        if bithumb_payload is not None:
            apply_lifecycle_projection(bithumb_payload, bithumb_demo)
        if upbit_payload is not None:
            apply_lifecycle_projection(upbit_payload, upbit_demo)

        # Preserve the backward-compatible Bithumb root projection as well.
        apply_lifecycle_projection(public, bithumb_demo)
        # Listing-history candles remain local. Only the read-only compact
        # case/source/feature projection is added to the existing snapshot row.
        public["listing_history"] = build_listing_history_snapshot(DEMO_DB_PATH)
        # Build 41 removes duplicate Bithumb projection blocks and reserves
        # payload headroom before future compact DEX research is introduced.
        return apply_snapshot_budget(snapshot)
