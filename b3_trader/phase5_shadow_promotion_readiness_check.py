from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .intelligence_shadow_promotion_readiness import (
    MIN_DISTINCT_EVENTS_PER_CELL,
    MIN_SAMPLES_PER_CELL,
    REQUIRED_CELLS_PER_CANDIDATE,
    REQUIRED_HORIZONS,
    REQUIRED_REFERENCE_SOURCES,
    STATUS_INSUFFICIENT,
    STATUS_READY,
    STATUS_WAITING,
)

STATUS_PATH = Path("b3_trader/data/research-platform/status.json")
_VALID_STATUSES = {STATUS_WAITING, STATUS_INSUFFICIENT, STATUS_READY}


def run_check(*, path: Path | str = STATUS_PATH) -> tuple[dict[str, Any], int]:
    status_path = Path(path)
    result: dict[str, Any] = {
        "ok": False,
        "status": "not_checked",
        "reasons": [],
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_mutation": False,
        "score_authority": False,
        "promotion_eligible": False,
        "automatic_promotion": False,
        "manual_review_ready": False,
        "missing_values_coerced_to_zero": False,
        "network_requests": 0,
        "minimum_samples_per_cell": MIN_SAMPLES_PER_CELL,
        "minimum_distinct_events_per_cell": MIN_DISTINCT_EVENTS_PER_CELL,
        "required_horizons": list(REQUIRED_HORIZONS),
        "required_reference_sources": list(REQUIRED_REFERENCE_SOURCES),
        "required_cells_per_candidate": REQUIRED_CELLS_PER_CANDIDATE,
        "candidates_considered": 0,
        "candidates_ready": 0,
        "blockers": [],
    }
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        result["status"] = "status_unavailable"
        result["reasons"] = [f"{type(exc).__name__}: {exc}"[:300]]
        return result, 2

    components = payload.get("components") if isinstance(payload, dict) else None
    phase5 = components.get("phase5-intelligence-ingest") if isinstance(components, dict) else None
    last_result = phase5.get("last_result") if isinstance(phase5, dict) else None
    readiness = last_result.get("shadow_promotion_readiness") if isinstance(last_result, dict) else None
    if not isinstance(readiness, dict):
        result["status"] = "readiness_result_missing"
        result["reasons"] = ["phase5 last_result has no shadow_promotion_readiness result"]
        return result, 1

    for key in (
        "status",
        "paper_only",
        "shadow_only",
        "can_place_orders",
        "score_mutation",
        "score_authority",
        "promotion_eligible",
        "automatic_promotion",
        "manual_review_ready",
        "missing_values_coerced_to_zero",
        "network_requests",
        "minimum_samples_per_cell",
        "minimum_distinct_events_per_cell",
        "required_horizons",
        "required_reference_sources",
        "required_cells_per_candidate",
        "candidates_considered",
        "candidates_ready",
        "blockers",
    ):
        if key in readiness:
            result[key] = readiness[key]

    reasons: list[str] = []
    status = str(readiness.get("status") or "")
    if status not in _VALID_STATUSES:
        reasons.append(f"invalid_status:{status or 'missing'}")
    if readiness.get("paper_only") is not True:
        reasons.append("paper_only_not_true")
    if readiness.get("shadow_only") is not True:
        reasons.append("shadow_only_not_true")
    for key in (
        "can_place_orders",
        "score_mutation",
        "score_authority",
        "promotion_eligible",
        "automatic_promotion",
        "missing_values_coerced_to_zero",
    ):
        if readiness.get(key) is not False:
            reasons.append(f"{key}_not_false")
    if int(readiness.get("network_requests") or 0) != 0:
        reasons.append("network_requests_not_zero")
    if int(readiness.get("minimum_samples_per_cell") or 0) != MIN_SAMPLES_PER_CELL:
        reasons.append("minimum_samples_contract_mismatch")
    if int(readiness.get("minimum_distinct_events_per_cell") or 0) != MIN_DISTINCT_EVENTS_PER_CELL:
        reasons.append("minimum_distinct_events_contract_mismatch")
    if list(readiness.get("required_horizons") or []) != list(REQUIRED_HORIZONS):
        reasons.append("required_horizons_contract_mismatch")
    if list(readiness.get("required_reference_sources") or []) != list(REQUIRED_REFERENCE_SOURCES):
        reasons.append("required_reference_sources_contract_mismatch")
    if int(readiness.get("required_cells_per_candidate") or 0) != REQUIRED_CELLS_PER_CANDIDATE:
        reasons.append("required_cells_contract_mismatch")

    ready = readiness.get("manual_review_ready") is True
    if status == STATUS_READY and not ready:
        reasons.append("ready_status_without_manual_review_ready")
    if status != STATUS_READY and ready:
        reasons.append("manual_review_ready_without_ready_status")
    if ready and int(readiness.get("candidates_ready") or 0) < 1:
        reasons.append("manual_review_ready_without_ready_candidate")

    result["reasons"] = reasons
    if reasons:
        result["status"] = "contract_violation"
        return result, 1
    result["ok"] = True
    result["status"] = status
    return result, 0


def main() -> None:
    result, code = run_check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
