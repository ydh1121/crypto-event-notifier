from __future__ import annotations

from b3_trader.phase5_runtime_check import EXPECTED_SOURCE_IDS, evaluate_phase5_runtime


def _healthy_snapshot() -> dict[str, object]:
    return {
        "paper_only": True,
        "supervisor_running": True,
        "safety": {"can_place_orders": False},
        "components": [
            {
                "name": "phase5-intelligence-ingest",
                "enabled": True,
                "status": "healthy",
                "runs": 2,
                "last_success_at": 1_000.0,
                "last_result": {
                    "paper_only": True,
                    "can_place_orders": False,
                    "score_mutation": False,
                    "network_enabled": True,
                    "status": "ok",
                    "source_failures": 0,
                    "requested_sources": sorted(EXPECTED_SOURCE_IDS),
                    "events_received": 0,
                    "events_inserted": 0,
                    "events_updated": 0,
                },
            }
        ],
    }


def test_runtime_check_accepts_healthy_zero_event_cycle():
    result = evaluate_phase5_runtime(_healthy_snapshot())
    assert result["ok"] is True
    assert result["reasons"] == []
    assert result["events_received"] == 0
    assert result["source_failures"] == 0


def test_runtime_check_fails_closed_on_missing_safety_and_component():
    result = evaluate_phase5_runtime({"paper_only": True, "supervisor_running": True, "components": []})
    assert result["ok"] is False
    assert "order_safety_not_asserted" in result["reasons"]
    assert "component_missing" in result["reasons"]


def test_runtime_check_rejects_partial_or_non_network_cycle():
    snapshot = _healthy_snapshot()
    component = snapshot["components"][0]
    component["last_result"]["network_enabled"] = False
    component["last_result"]["status"] = "partial"
    component["last_result"]["source_failures"] = 1

    result = evaluate_phase5_runtime(snapshot)
    assert result["ok"] is False
    assert "network_cycle_not_verified" in result["reasons"]
    assert "last_cycle_not_ok" in result["reasons"]
    assert "source_failures_present" in result["reasons"]


def test_runtime_check_requires_all_official_sources_and_order_safety():
    snapshot = _healthy_snapshot()
    component = snapshot["components"][0]
    component["last_result"]["requested_sources"] = ["us_bls_release_calendar"]
    component["last_result"]["can_place_orders"] = True

    result = evaluate_phase5_runtime(snapshot)
    assert result["ok"] is False
    assert "official_sources_incomplete" in result["reasons"]
    assert "component_order_safety_not_asserted" in result["reasons"]
    assert result["missing_sources"]
