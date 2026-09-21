from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.forward_pipeline_scheduler import (
    HEARTBEAT_SECONDS,
    MIN_INTERVAL_SECONDS,
    RESEARCH_STATUS_FRESH_SECONDS,
    STATUS_PATH,
    _read_json,
    _safety_violations,
)
from b3_trader.research_control import STATUS_PATH as RESEARCH_STATUS_PATH


def _offline_payload(path: Path) -> dict:
    return {
        "ok": True,
        "status": "server_offline_runtime_pending",
        "runtime_active": False,
        "status_path": str(path),
        "network_fetches": False,
        "database_mutation": False,
        "source_contract_ready": True,
        "runtime_verification_pending": True,
        "review": {
            "next_action": "start_normal_server_once_then_rerun_with_require_running",
        },
    }


def _runtime_payload(path: Path, research_path: Path) -> dict:
    now = time.time()
    status = _read_json(path)
    updated_at = float(status.get("updated_at") or 0.0)
    fresh = bool(status.get("running")) and updated_at > 0 and (
        now - updated_at <= max(20.0, HEARTBEAT_SECONDS * 4)
    )
    if not fresh:
        return _offline_payload(path)

    research = _read_json(research_path)
    research_updated_at = float(research.get("updated_at") or 0.0)
    research_fresh = bool(research.get("running")) and research_updated_at > 0 and (
        now - research_updated_at <= RESEARCH_STATUS_FRESH_SECONDS
    )
    components = (
        research.get("components")
        if isinstance(research.get("components"), dict)
        else {}
    )
    generic = {}
    for name in ("listing-history-research", "dex-launch-research"):
        row = components.get(name) if isinstance(components.get(name), dict) else {}
        generic[name] = {
            "enabled": bool(row.get("enabled")),
            "status": str(row.get("status") or "unknown"),
            "last_result_status": str((row.get("last_result") or {}).get("status") or ""),
        }

    last_result = (
        status.get("last_result") if isinstance(status.get("last_result"), dict) else {}
    )
    last_status = str(last_result.get("status") or "waiting_first_run")
    if last_result and not last_status.startswith("deferred_") and last_status not in {
        "retryable_scheduler_error",
        "safety_contract_blocked",
    }:
        violations = _safety_violations(last_result)
    else:
        violations = []
    checks = {
        "scheduler_running": True,
        "scheduler_status_fresh": fresh,
        "scheduler_process_lock_acquired": bool(status.get("process_lock_acquired")),
        "scheduler_paper_only": status.get("paper_only") is True,
        "scheduler_shadow_only": status.get("shadow_only") is True,
        "scheduler_cannot_place_orders": status.get("can_place_orders") is False,
        "scheduler_paper_ab_unwired": status.get("paper_ab_wired") is False,
        "scheduler_live_unwired": status.get("live_promotion_allowed") is False,
        "scheduler_interval_bounded": float(status.get("interval_seconds") or 0.0)
        >= MIN_INTERVAL_SECONDS,
        "scheduler_pages_bounded": 1 <= int(status.get("pages_per_exchange") or 0) <= 2,
        "scheduler_last_result_safe": not violations,
        "research_supervisor_running": research_fresh,
        "generic_listing_history_disabled": not generic["listing-history-research"][
            "enabled"
        ],
        "generic_dex_launch_disabled": not generic["dex-launch-research"]["enabled"],
        "research_forward_dedicated_mode": bool(
            (research.get("safety") or {}).get("forward_pipeline_dedicated_mode")
        ),
    }
    return {
        "ok": all(checks.values()),
        "status": "runtime_verified" if all(checks.values()) else "runtime_contract_failed",
        "runtime_active": True,
        "status_path": str(path),
        "checks": checks,
        "scheduler": {
            "pid": int(status.get("pid") or 0),
            "updated_at": updated_at,
            "interval_seconds": float(status.get("interval_seconds") or 0.0),
            "pages_per_exchange": int(status.get("pages_per_exchange") or 0),
            "attempts": int(status.get("attempts") or 0),
            "successes": int(status.get("successes") or 0),
            "deferred": int(status.get("deferred") or 0),
            "failures": int(status.get("failures") or 0),
            "last_error": str(status.get("last_error") or ""),
            "last_result_status": last_status,
            "last_result_summary": last_result.get("summary") or {},
        },
        "generic_research": generic,
        "last_result_safety_violations": violations,
        "network_fetches": False,
        "database_mutation": False,
        "review": {
            "next_action": (
                "continue_automatic_build69_forward_accumulation"
                if all(checks.values())
                else "repair_failed_runtime_contract_before_leaving_server_on"
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status-path", type=Path, default=STATUS_PATH)
    parser.add_argument("--research-status-path", type=Path, default=RESEARCH_STATUS_PATH)
    parser.add_argument("--require-running", action="store_true")
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("DEX_FORWARD_PIPELINE_SCHEDULER_BUILD69_IMPORT=PASS")
        return

    payload = _runtime_payload(args.status_path, args.research_status_path)
    print("=== DEX FORWARD PIPELINE SCHEDULER BUILD 69 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload.get("runtime_active"):
        if args.require_running:
            raise SystemExit("DEX_FORWARD_PIPELINE_SCHEDULER_BUILD69_RUNTIME=FAIL")
        print("DEX_FORWARD_PIPELINE_SCHEDULER_BUILD69_SERVER_OFFLINE=PASS")
        return
    if not payload.get("ok"):
        raise SystemExit("DEX_FORWARD_PIPELINE_SCHEDULER_BUILD69_RUNTIME=FAIL")
    print("DEX_FORWARD_PIPELINE_SCHEDULER_BUILD69_RUNTIME=PASS")


if __name__ == "__main__":
    main()
