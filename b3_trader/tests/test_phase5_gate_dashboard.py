from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.phase5_gate_dashboard import build_phase5_gate_dashboard_snapshot


def _runtime_snapshot() -> dict:
    return {
        "paper_only": True,
        "supervisor_running": True,
        "safety": {"can_place_orders": False},
        "components": [
            {
                "name": "phase5-intelligence-ingest",
                "enabled": True,
                "status": "healthy",
                "runs": 1,
                "last_success_at": 1_700_000_000.0,
                "last_result": {
                    "paper_only": True,
                    "can_place_orders": False,
                    "score_mutation": False,
                    "network_enabled": True,
                    "status": "ok",
                    "source_failures": 0,
                    "requested_sources": [
                        "us_bls_release_calendar",
                        "us_bea_release_schedule",
                        "us_fed_fomc_calendar",
                        "us_sec_press_releases",
                        "us_cftc_press_releases",
                    ],
                    "events_received": 0,
                    "events_inserted": 0,
                    "events_updated": 0,
                    "consensus_capture": {"status": "credential_missing"},
                    "us_market_reference_capture": {"status": "credential_missing"},
                    "event_response_capture": {"status": "waiting_for_observable_event"},
                    "event_response_us_sensitivity": {"status": "waiting_for_samples"},
                    "shadow_promotion_readiness": {"status": "waiting_for_samples"},
                },
            }
        ],
    }


def test_dashboard_snapshot_is_read_only_and_does_not_expose_credentials(tmp_path: Path) -> None:
    db = tmp_path / "phase5.sqlite3"
    sqlite3.connect(db).close()

    result = build_phase5_gate_dashboard_snapshot(
        path=db,
        runtime_snapshot=_runtime_snapshot(),
        env={
            "TRADING_ECONOMICS_API_KEY": "secret-te-value",
            "TWELVE_DATA_API_KEY": "secret-twelve-value",
        },
    )

    rendered = repr(result)
    assert result["read_only"] is True
    assert result["external_network_requests"] == 0
    assert result["credential_values_exposed"] is False
    assert "secret-te-value" not in rendered
    assert "secret-twelve-value" not in rendered
    assert result["summary"]["FAILED"] == 0


def test_dashboard_snapshot_preserves_expected_waiting_blocked_states(tmp_path: Path) -> None:
    db = tmp_path / "phase5.sqlite3"
    sqlite3.connect(db).close()

    result = build_phase5_gate_dashboard_snapshot(
        path=db,
        runtime_snapshot=_runtime_snapshot(),
        env={},
    )
    gates = {row["id"]: row for row in result["gates"]}

    assert gates["phase5_runtime"]["status"] == "PASS"
    assert gates["consensus_provider"]["status"] == "BLOCKED"
    assert gates["us_index_reference"]["status"] == "BLOCKED"
    assert gates["event_response_samples"]["status"] == "WAITING"
    assert gates["shadow_promotion_readiness"]["status"] == "WAITING"
