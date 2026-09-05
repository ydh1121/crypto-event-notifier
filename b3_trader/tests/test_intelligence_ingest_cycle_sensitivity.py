from __future__ import annotations

import sqlite3

from b3_trader.intelligence_ingest_cycle import IntelligenceIngestCycle


class _ResponseCapture:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def run_once(self, *, now: float):
        self.calls.append("response")
        return {
            "ok": True,
            "status": "ok",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "network_requests": 0,
        }


class _Sensitivity:
    def __init__(self, calls: list[str], *, ok: bool = True) -> None:
        self.calls = calls
        self.ok = ok

    def run_once(self, *, now: float):
        self.calls.append("sensitivity")
        return {
            "ok": self.ok,
            "status": "waiting_for_event_response_samples" if self.ok else "invalid_event_response_rows",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "network_requests": 0,
        }


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_ingest_runs_sensitivity_after_event_response_without_promoting_waiting_state() -> None:
    calls: list[str] = []
    cycle = IntelligenceIngestCycle(
        conn=_conn(),
        fetchers={"us_sec_press_releases": lambda now: []},
        event_response_capture=_ResponseCapture(calls),
        us_market_sensitivity=_Sensitivity(calls),
    )
    result = cycle.run_once(
        network_enabled=True,
        source_ids=["us_sec_press_releases"],
        now=1000,
    )
    assert calls == ["response", "sensitivity"]
    assert result["status"] == "ok"
    assert result["event_response_failures"] == 0
    assert result["us_market_sensitivity_failures"] == 0
    assert result["us_market_sensitivity"]["status"] == "waiting_for_event_response_samples"


def test_invalid_sensitivity_state_marks_cycle_partial_fail_closed() -> None:
    calls: list[str] = []
    cycle = IntelligenceIngestCycle(
        conn=_conn(),
        fetchers={"us_sec_press_releases": lambda now: []},
        event_response_capture=_ResponseCapture(calls),
        us_market_sensitivity=_Sensitivity(calls, ok=False),
    )
    result = cycle.run_once(
        network_enabled=True,
        source_ids=["us_sec_press_releases"],
        now=1000,
    )
    assert result["status"] == "partial"
    assert result["us_market_sensitivity_failures"] == 1
    assert result["us_market_sensitivity"]["status"] == "invalid_event_response_rows"
