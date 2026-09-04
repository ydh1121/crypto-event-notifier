from __future__ import annotations

import argparse
import json
from typing import Any

import requests

from .config import Settings

COMPONENT_NAME = "phase5-intelligence-ingest"
EXPECTED_SOURCE_IDS = {
    "us_bls_release_calendar",
    "us_bea_release_schedule",
    "us_fed_fomc_calendar",
    "us_sec_press_releases",
    "us_cftc_press_releases",
}


def evaluate_phase5_runtime(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the read-only Phase 5 supervisor snapshot fail-closed.

    A pass means the current supervisor is alive and the Phase 5 worker has
    completed at least one full network-enabled official-source cycle without a
    source failure. Event count is intentionally not a pass condition because a
    healthy cycle may legitimately discover no new evidence.
    """

    reasons: list[str] = []
    if snapshot.get("paper_only") is not True:
        reasons.append("paper_only_not_asserted")

    safety = snapshot.get("safety") if isinstance(snapshot.get("safety"), dict) else {}
    if safety.get("can_place_orders") is not False:
        reasons.append("order_safety_not_asserted")
    if snapshot.get("supervisor_running") is not True:
        reasons.append("supervisor_not_running")

    component: dict[str, Any] | None = None
    rows = snapshot.get("components") if isinstance(snapshot.get("components"), list) else []
    for row in rows:
        if isinstance(row, dict) and str(row.get("name") or "") == COMPONENT_NAME:
            component = row
            break

    if component is None:
        reasons.append("component_missing")
        return {
            "ok": False,
            "component": COMPONENT_NAME,
            "reasons": reasons,
            "status": "missing",
            "runs": 0,
            "last_success_at": 0.0,
            "last_result_status": "",
            "source_failures": None,
        }

    if component.get("enabled") is not True:
        reasons.append("component_disabled")
    status = str(component.get("status") or "").strip().lower()
    if status != "healthy":
        reasons.append("component_not_healthy")

    try:
        runs = int(component.get("runs") or 0)
    except (TypeError, ValueError):
        runs = 0
    if runs < 1:
        reasons.append("no_completed_cycle")

    try:
        last_success_at = float(component.get("last_success_at") or 0.0)
    except (TypeError, ValueError):
        last_success_at = 0.0
    if last_success_at <= 0:
        reasons.append("no_success_timestamp")

    last_result = component.get("last_result") if isinstance(component.get("last_result"), dict) else {}
    if last_result.get("paper_only") is not True:
        reasons.append("component_paper_only_not_asserted")
    if last_result.get("can_place_orders") is not False:
        reasons.append("component_order_safety_not_asserted")
    if last_result.get("score_mutation") is not False:
        reasons.append("score_mutation_safety_not_asserted")
    if last_result.get("network_enabled") is not True:
        reasons.append("network_cycle_not_verified")

    last_result_status = str(last_result.get("status") or "").strip().lower()
    if last_result_status != "ok":
        reasons.append("last_cycle_not_ok")

    try:
        source_failures = int(last_result.get("source_failures"))
    except (TypeError, ValueError):
        source_failures = -1
    if source_failures != 0:
        reasons.append("source_failures_present")

    requested = {
        str(value or "").strip().lower()
        for value in (last_result.get("requested_sources") if isinstance(last_result.get("requested_sources"), list) else [])
        if str(value or "").strip()
    }
    missing_sources = sorted(EXPECTED_SOURCE_IDS - requested)
    if missing_sources:
        reasons.append("official_sources_incomplete")

    return {
        "ok": not reasons,
        "component": COMPONENT_NAME,
        "reasons": reasons,
        "status": status or "unknown",
        "runs": runs,
        "last_success_at": last_success_at,
        "last_result_status": last_result_status,
        "source_failures": source_failures,
        "missing_sources": missing_sources,
        "events_received": int(last_result.get("events_received") or 0),
        "events_inserted": int(last_result.get("events_inserted") or 0),
        "events_updated": int(last_result.get("events_updated") or 0),
    }


def fetch_runtime_snapshot(*, port: int, timeout_seconds: float = 2.5) -> dict[str, Any]:
    response = requests.get(
        f"http://127.0.0.1:{int(port)}/api/research/components",
        timeout=max(0.2, float(timeout_seconds)),
        headers={"User-Agent": "phase5-intelligence-runtime-check/1.0"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("runtime snapshot is not a JSON object")
    return payload


def main() -> int:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Read-only Phase 5 intelligence runtime smoke check")
    parser.add_argument("--port", type=int, default=int(settings.service_port))
    parser.add_argument("--timeout", type=float, default=2.5)
    args = parser.parse_args()

    try:
        snapshot = fetch_runtime_snapshot(port=args.port, timeout_seconds=args.timeout)
    except (requests.RequestException, ValueError) as exc:
        result = {
            "ok": False,
            "component": COMPONENT_NAME,
            "reasons": ["runtime_unavailable_or_invalid"],
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    result = evaluate_phase5_runtime(snapshot)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
