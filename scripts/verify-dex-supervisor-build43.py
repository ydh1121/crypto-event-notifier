from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_launch_audit import audit_dex_launch
from b3_trader.research_control import COMPONENT_DEFINITIONS, STATUS_PATH


def _read_status() -> dict:
    if not STATUS_PATH.exists():
        return {}
    try:
        payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def main() -> None:
    status = _read_status()
    components = status.get("components") if isinstance(status.get("components"), dict) else {}
    component = components.get("dex-launch-research") if isinstance(components.get("dex-launch-research"), dict) else {}
    result = component.get("last_result") if isinstance(component.get("last_result"), dict) else {}
    safety = status.get("safety") if isinstance(status.get("safety"), dict) else {}
    definition = COMPONENT_DEFINITIONS.get("dex-launch-research") or {}
    audit = audit_dex_launch()

    payload = {
        "ok": bool(status and component and audit.get("ok")),
        "component": {
            "exists": bool(component),
            "enabled": bool(component.get("enabled")),
            "status": str(component.get("status") or "missing"),
            "interval_seconds": float(component.get("interval_seconds") or 0.0),
            "runs": int(component.get("runs") or 0),
            "last_success_at": float(component.get("last_success_at") or 0.0),
            "last_error": str(component.get("last_error") or ""),
            "result_status": str(result.get("status") or ""),
            "pending_cases": int(result.get("pending_cases") or 0),
            "processed": int(result.get("processed") or 0),
            "complete": int(result.get("complete") or 0),
            "identity_waiting": int(result.get("identity_waiting") or 0),
            "pool_quality_waiting": int(result.get("pool_quality_waiting") or 0),
            "source_waiting": int(result.get("source_waiting") or 0),
        },
        "definition": {
            "default_enabled": bool(definition.get("default_enabled")),
            "default_interval_seconds": float(definition.get("default_interval_seconds") or 0.0),
            "min_interval_seconds": float(definition.get("min_interval_seconds") or 0.0),
        },
        "audit": {
            "case_count": int(audit.get("case_count") or 0),
            "case_status_counts": audit.get("case_status_counts") if isinstance(audit.get("case_status_counts"), dict) else {},
            "asset_count": int(audit.get("asset_count") or 0),
            "pool_count": int(audit.get("pool_count") or 0),
            "accepted_pool_count": int(audit.get("accepted_pool_count") or 0),
            "primary_pool_count": int(audit.get("primary_pool_count") or 0),
            "candle_count": int(audit.get("candle_count") or 0),
            "feature_count": int(audit.get("feature_count") or 0),
            "raw_candles_cloud_projected": bool(audit.get("raw_candles_cloud_projected")),
        },
        "safety": {
            "paper_only": bool(status.get("paper_only")),
            "can_place_orders": bool(safety.get("can_place_orders")),
            "dex_launch_public_sources_only": bool(safety.get("dex_launch_public_sources_only")),
            "dex_launch_shadow_only": bool(safety.get("dex_launch_shadow_only")),
        },
    }

    print("=== DEX SUPERVISOR BUILD 43 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    acceptable_status = payload["component"]["status"] in {"starting", "running", "healthy"}
    safe = bool(
        payload["ok"]
        and payload["component"]["enabled"]
        and payload["component"]["interval_seconds"] >= 1800.0
        and acceptable_status
        and "SQLite objects created in a thread" not in payload["component"]["last_error"]
        and payload["safety"]["paper_only"]
        and not payload["safety"]["can_place_orders"]
        and payload["safety"]["dex_launch_public_sources_only"]
        and payload["safety"]["dex_launch_shadow_only"]
        and not payload["audit"]["raw_candles_cloud_projected"]
    )
    if not safe:
        raise SystemExit("DEX_SUPERVISOR_BUILD43_RUNTIME=FAIL")
    print("DEX_SUPERVISOR_BUILD43_RUNTIME=PASS")


if __name__ == "__main__":
    main()
