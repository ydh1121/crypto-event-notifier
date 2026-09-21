from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


STATUS_PATH = Path("b3_trader/data/research-platform/status.json")


def _read_status(attempts: int = 8, delay_seconds: float = 0.05) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except (OSError, json.JSONDecodeError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(delay_seconds)
    if last_error is not None:
        raise RuntimeError(f"cannot read stable supervisor status: {last_error}") from last_error
    raise RuntimeError("cannot read stable supervisor status")


def _component(status: dict[str, Any], name: str) -> dict[str, Any]:
    components = status.get("components") if isinstance(status.get("components"), dict) else {}
    value = components.get(name)
    return value if isinstance(value, dict) else {}


def _compact_component(value: dict[str, Any]) -> dict[str, Any]:
    result = value.get("last_result") if isinstance(value.get("last_result"), dict) else {}
    return {
        "exists": bool(value),
        "enabled": bool(value.get("enabled")),
        "status": str(value.get("status") or "missing"),
        "interval_seconds": float(value.get("interval_seconds") or 0.0),
        "runs": int(value.get("runs") or 0),
        "last_success_at": float(value.get("last_success_at") or 0.0),
        "last_error": str(value.get("last_error") or ""),
        "last_result": result,
    }


def main() -> None:
    status = _read_status()
    snapshot = _compact_component(_component(status, "cloudflare-snapshot-publish"))
    pages = _compact_component(_component(status, "cloudflare-pages-deploy"))
    safety = status.get("safety") if isinstance(status.get("safety"), dict) else {}
    payload = {
        "ok": True,
        "supervisor": {
            "pid": int(status.get("pid") or 0),
            "running": bool(status.get("running")),
            "paper_only": bool(status.get("paper_only")),
        },
        "cloudflare_snapshot_publish": snapshot,
        "cloudflare_pages_deploy": pages,
        "safety": {
            "can_place_orders": bool(safety.get("can_place_orders")),
            "cloudflare_viewer_read_only": bool(safety.get("cloudflare_viewer_read_only")),
            "dex_launch_public_sources_only": bool(safety.get("dex_launch_public_sources_only")),
            "dex_launch_shadow_only": bool(safety.get("dex_launch_shadow_only")),
        },
    }
    print("=== CLOUDFLARE BUILD 44 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    snapshot_result = snapshot.get("last_result") if isinstance(snapshot.get("last_result"), dict) else {}
    pages_result = pages.get("last_result") if isinstance(pages.get("last_result"), dict) else {}
    remote = snapshot_result.get("remote") if isinstance(snapshot_result.get("remote"), dict) else {}
    snapshot_ok = bool(
        snapshot["exists"]
        and snapshot["enabled"]
        and snapshot["status"] in {"healthy", "running"}
        and not snapshot["last_error"]
        and (
            snapshot_result.get("status") == "published" and bool(remote.get("ok"))
            or snapshot["status"] == "running"
        )
    )
    pages_ok = bool(
        pages["exists"]
        and pages["enabled"]
        and pages["status"] in {"healthy", "running"}
        and not pages["last_error"]
        and str(pages_result.get("status") or "") in {"deployed", "up_to_date", "no_viewer_changes", ""}
    )
    safe = bool(
        payload["supervisor"]["running"]
        and payload["supervisor"]["paper_only"]
        and snapshot_ok
        and pages_ok
        and not payload["safety"]["can_place_orders"]
        and payload["safety"]["cloudflare_viewer_read_only"]
        and payload["safety"]["dex_launch_public_sources_only"]
        and payload["safety"]["dex_launch_shadow_only"]
    )
    if not safe:
        raise SystemExit("CLOUDFLARE_BUILD44_RUNTIME=FAIL")
    print("CLOUDFLARE_BUILD44_RUNTIME=PASS")


if __name__ == "__main__":
    main()
