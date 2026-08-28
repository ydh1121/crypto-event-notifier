from __future__ import annotations

import json

from b3_trader.cloudflare_snapshot_budget import MAX_BODY_BYTES, TARGET_BODY_BYTES, snapshot_bytes
from b3_trader.cloudflare_snapshot_lifecycle import CloudflareSnapshotPublisher


FORBIDDEN_RAW_KEYS = {
    "candles",
    "candle_ts",
    "interval_seconds",
    "open",
    "high",
    "low",
    "close",
    "volume_usd",
}


def _raw_key_hits(value, path="public.dex_launch") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_RAW_KEYS:
                hits.append(child_path)
            hits.extend(_raw_key_hits(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(_raw_key_hits(child, f"{path}[{index}]"))
    return hits


def main() -> None:
    snapshot = CloudflareSnapshotPublisher().build_snapshot()
    public = snapshot.get("public") if isinstance(snapshot.get("public"), dict) else {}
    dex = public.get("dex_launch") if isinstance(public.get("dex_launch"), dict) else {}
    budget = public.get("snapshot_budget") if isinstance(public.get("snapshot_budget"), dict) else {}
    cases = dex.get("cases") if isinstance(dex.get("cases"), list) else []
    raw_hits = _raw_key_hits(dex)
    body_bytes = snapshot_bytes(snapshot)
    projection_bytes = len(json.dumps(dex, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    asset_counts = [len(row.get("assets") or []) for row in cases if isinstance(row, dict)]

    payload = {
        "ok": bool(dex),
        "projection": {
            "version": int(dex.get("version") or 0),
            "paper_only": bool(dex.get("paper_only")),
            "shadow_only": bool(dex.get("shadow_only")),
            "raw_candles_included": bool(dex.get("raw_candles_included")),
            "case_count": int(dex.get("case_count") or 0),
            "projected_cases": len(cases),
            "max_assets_per_projected_case": max(asset_counts, default=0),
            "asset_count": int(dex.get("asset_count") or 0),
            "pool_count": int(dex.get("pool_count") or 0),
            "accepted_pool_count": int(dex.get("accepted_pool_count") or 0),
            "primary_pool_count": int(dex.get("primary_pool_count") or 0),
            "feature_count": int(dex.get("feature_count") or 0),
            "status_counts": dex.get("status_counts") if isinstance(dex.get("status_counts"), dict) else {},
            "projection_bytes": projection_bytes,
            "raw_key_hits": raw_hits,
        },
        "snapshot_budget": {
            "body_bytes": body_bytes,
            "target_body_bytes": int(budget.get("target_body_bytes") or TARGET_BODY_BYTES),
            "max_body_bytes": int(budget.get("max_body_bytes") or MAX_BODY_BYTES),
            "headroom_bytes": int(budget.get("headroom_bytes") or max(0, MAX_BODY_BYTES - body_bytes)),
            "within_target": bool(budget.get("within_target", body_bytes <= TARGET_BODY_BYTES)),
            "within_hard_limit": bool(budget.get("within_hard_limit", body_bytes <= MAX_BODY_BYTES)),
            "compact_level": str(budget.get("compact_level") or ""),
            "raw_rows_added": bool(budget.get("raw_rows_added")),
        },
        "safety": {
            "paper_only": bool(public.get("paper_only")),
            "can_place_orders": False,
            "raw_dex_rows_projected": bool(raw_hits),
        },
    }

    print("=== DEX CLOUD PROJECTION BUILD 44 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    safe = bool(
        payload["ok"]
        and payload["projection"]["version"] == 1
        and payload["projection"]["paper_only"]
        and payload["projection"]["shadow_only"]
        and not payload["projection"]["raw_candles_included"]
        and payload["projection"]["projected_cases"] <= 16
        and payload["projection"]["max_assets_per_projected_case"] <= 2
        and not raw_hits
        and payload["snapshot_budget"]["within_target"]
        and payload["snapshot_budget"]["within_hard_limit"]
        and not payload["snapshot_budget"]["raw_rows_added"]
        and payload["safety"]["paper_only"]
        and not payload["safety"]["can_place_orders"]
    )
    if not safe:
        raise SystemExit("DEX_CLOUD_PROJECTION_BUILD44_RUNTIME=FAIL")
    print("DEX_CLOUD_PROJECTION_BUILD44_RUNTIME=PASS")


if __name__ == "__main__":
    main()
