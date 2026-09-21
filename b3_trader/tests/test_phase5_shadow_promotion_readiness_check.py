from __future__ import annotations

import json
from pathlib import Path

from b3_trader.intelligence_shadow_promotion_readiness import (
    MIN_DISTINCT_EVENTS_PER_CELL,
    MIN_SAMPLES_PER_CELL,
    REQUIRED_CELLS_PER_CANDIDATE,
    REQUIRED_HORIZONS,
    REQUIRED_REFERENCE_SOURCES,
    STATUS_INSUFFICIENT,
    STATUS_READY,
    STATUS_WAITING,
)
from b3_trader.phase5_shadow_promotion_readiness_check import run_check


def _payload(status: str, *, ready: bool = False, promotion_eligible: bool = False) -> dict:
    readiness = {
        "ok": True,
        "status": status,
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_mutation": False,
        "score_authority": False,
        "promotion_eligible": promotion_eligible,
        "automatic_promotion": False,
        "manual_review_ready": ready,
        "missing_values_coerced_to_zero": False,
        "network_requests": 0,
        "minimum_samples_per_cell": MIN_SAMPLES_PER_CELL,
        "minimum_distinct_events_per_cell": MIN_DISTINCT_EVENTS_PER_CELL,
        "required_horizons": list(REQUIRED_HORIZONS),
        "required_reference_sources": list(REQUIRED_REFERENCE_SOURCES),
        "required_cells_per_candidate": REQUIRED_CELLS_PER_CANDIDATE,
        "candidates_considered": 1 if status != STATUS_WAITING else 0,
        "candidates_ready": 1 if ready else 0,
        "blockers": [] if ready else ["no_sensitivity_samples"],
    }
    return {
        "components": {
            "phase5-intelligence-ingest": {
                "last_result": {"shadow_promotion_readiness": readiness}
            }
        }
    }


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "status.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_waiting_state_is_a_valid_safe_runtime_state(tmp_path: Path) -> None:
    result, code = run_check(path=_write(tmp_path, _payload(STATUS_WAITING)))
    assert code == 0
    assert result["ok"] is True
    assert result["status"] == STATUS_WAITING
    assert result["manual_review_ready"] is False


def test_insufficient_state_is_a_valid_safe_runtime_state(tmp_path: Path) -> None:
    result, code = run_check(path=_write(tmp_path, _payload(STATUS_INSUFFICIENT)))
    assert code == 0
    assert result["ok"] is True
    assert result["status"] == STATUS_INSUFFICIENT
    assert result["promotion_eligible"] is False


def test_ready_state_still_has_no_automatic_promotion_authority(tmp_path: Path) -> None:
    result, code = run_check(path=_write(tmp_path, _payload(STATUS_READY, ready=True)))
    assert code == 0
    assert result["ok"] is True
    assert result["manual_review_ready"] is True
    assert result["promotion_eligible"] is False
    assert result["can_place_orders"] is False


def test_any_promotion_authority_is_rejected(tmp_path: Path) -> None:
    result, code = run_check(
        path=_write(tmp_path, _payload(STATUS_READY, ready=True, promotion_eligible=True))
    )
    assert code == 1
    assert result["ok"] is False
    assert result["status"] == "contract_violation"
    assert "promotion_eligible_not_false" in result["reasons"]
