from __future__ import annotations

import sqlite3

from b3_trader.intelligence_ingest_cycle import IntelligenceIngestCycle


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class _Capture:
    def __init__(self, status: str):
        self.status = status
        self.calls: list[tuple[float, bool]] = []

    def run_once(self, *, now: float, network_enabled: bool):
        self.calls.append((now, network_enabled))
        return {
            "status": self.status,
            "paper_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "credential_exposed": False,
        }


def test_ingest_cycle_calls_bea_actual_only_when_bea_schedule_is_requested() -> None:
    capture = _Capture("ok")
    cycle = IntelligenceIngestCycle(
        conn=_conn(),
        fetchers={"us_bea_release_schedule": lambda _now: []},
        bea_actual_capture=capture,
    )
    result = cycle.run_once(
        network_enabled=True,
        source_ids=["us_bea_release_schedule"],
        now=2000,
    )
    assert result["status"] == "ok"
    assert result["source_failures"] == 0
    assert result["bea_actual_capture"]["status"] == "ok"
    assert capture.calls == [(2000.0, True)]


def test_missing_bea_credentials_do_not_break_official_schedule_ingest() -> None:
    capture = _Capture("credentials_missing")
    cycle = IntelligenceIngestCycle(
        conn=_conn(),
        fetchers={"us_bea_release_schedule": lambda _now: []},
        bea_actual_capture=capture,
    )
    result = cycle.run_once(
        network_enabled=True,
        source_ids=["us_bea_release_schedule"],
        now=3000,
    )
    assert result["status"] == "ok"
    assert result["source_failures"] == 0
    assert result["bea_actual_capture"]["status"] == "credentials_missing"


def test_bea_capture_partial_marks_cycle_partial_without_order_authority() -> None:
    capture = _Capture("partial")
    cycle = IntelligenceIngestCycle(
        conn=_conn(),
        fetchers={"us_bea_release_schedule": lambda _now: []},
        bea_actual_capture=capture,
    )
    result = cycle.run_once(
        network_enabled=True,
        source_ids=["us_bea_release_schedule"],
        now=4000,
    )
    assert result["status"] == "partial"
    assert result["source_failures"] == 1
    assert result["paper_only"] is True
    assert result["can_place_orders"] is False
    assert result["score_mutation"] is False
