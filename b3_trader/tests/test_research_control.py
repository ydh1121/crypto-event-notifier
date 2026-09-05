from __future__ import annotations

import json
import time

from b3_trader.research_control import load_control, patch_component, platform_snapshot


def test_component_control_is_persistent_and_bounded(tmp_path):
    control_path = tmp_path / "components.json"
    control = load_control(control_path)
    assert control["components"]["warehouse-export"]["enabled"] is True
    phase5 = control["components"]["phase5-intelligence-ingest"]
    assert phase5["enabled"] is True
    assert phase5["interval_seconds"] == 900.0

    updated = patch_component(
        "warehouse-export",
        enabled=False,
        interval_seconds=1,
        run_now=True,
        path=control_path,
    )
    row = updated["components"]["warehouse-export"]
    assert row["enabled"] is False
    assert row["interval_seconds"] == 60.0
    assert row["run_nonce"] == 1
    assert updated["revision"] > control["revision"]

    phase5_updated = patch_component(
        "phase5-intelligence-ingest",
        interval_seconds=1,
        path=control_path,
    )
    assert phase5_updated["components"]["phase5-intelligence-ingest"]["interval_seconds"] == 300.0

    reloaded = load_control(control_path)
    assert reloaded["components"]["warehouse-export"] == row
    assert reloaded["components"]["phase5-intelligence-ingest"]["interval_seconds"] == 300.0


def test_platform_snapshot_summarizes_runtime_and_reference_updates(tmp_path):
    control_path = tmp_path / "components.json"
    status_path = tmp_path / "status.json"
    reference_path = tmp_path / "references.json"
    load_control(control_path)
    now = time.time()
    status_path.write_text(
        json.dumps(
            {
                "running": True,
                "pid": 123,
                "started_at": now - 60,
                "updated_at": now,
                "components": {
                    "warehouse-export": {
                        "status": "healthy",
                        "last_success_at": now - 2,
                        "runs": 3,
                        "last_result": {"status": "ok", "exported_rows": 42},
                    },
                    "reference-version-watch": {
                        "status": "healthy",
                        "last_success_at": now - 3,
                        "runs": 2,
                        "last_result": {},
                    },
                    "phase5-intelligence-ingest": {
                        "status": "healthy",
                        "last_success_at": now - 4,
                        "runs": 1,
                        "last_result": {
                            "status": "ok",
                            "paper_only": True,
                            "can_place_orders": False,
                            "score_mutation": False,
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    reference_path.write_text(
        json.dumps(
            {
                "checked_at": now,
                "components": [
                    {"id": "a", "status": "update_available"},
                    {"id": "b", "status": "current_seen"},
                    {"id": "c", "status": "check_failed"},
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = platform_snapshot(
        control_path=control_path,
        status_path=status_path,
        reference_state_path=reference_path,
    )
    assert snapshot["supervisor_running"] is True
    assert snapshot["references"]["total"] == 3
    assert snapshot["references"]["updates"] == 1
    assert snapshot["references"]["failed"] == 1
    warehouse = next(row for row in snapshot["components"] if row["name"] == "warehouse-export")
    assert warehouse["last_result"]["exported_rows"] == 42
    phase5 = next(row for row in snapshot["components"] if row["name"] == "phase5-intelligence-ingest")
    assert phase5["status"] == "healthy"
    assert phase5["last_result"]["can_place_orders"] is False
    assert snapshot["safety"]["can_place_orders"] is False
