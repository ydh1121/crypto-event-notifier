from __future__ import annotations

import sqlite3

from b3_trader.intelligence_event import normalize_intelligence_event
from b3_trader.intelligence_ingest_cycle import IntelligenceIngestCycle
from b3_trader.intelligence_source_registry import MACRO_CALENDAR


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _event(now: float):
    return normalize_intelligence_event(
        source_id="us_bls_release_calendar",
        source_family=MACRO_CALENDAR,
        event_type="US_CPI",
        title="Consumer Price Index for August 2026",
        source_url="https://www.bls.gov/schedule/",
        external_id="cpi-consensus-wiring",
        scheduled_at=now + 1800,
        received_at=now,
        entities=("US",),
    )


class _ActualCapture:
    def run_once(self, **kwargs):
        return {"status": "ok", "paper_only": True, "can_place_orders": False, "score_mutation": False}


class _ConsensusCapture:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run_once(self, **kwargs):
        self.calls.append(kwargs)
        return dict(self.result)


def test_missing_consensus_credential_does_not_break_official_ingest() -> None:
    consensus = _ConsensusCapture(
        {
            "status": "credential_missing",
            "paper_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "credential_exposed": False,
        }
    )
    cycle = IntelligenceIngestCycle(
        conn=_conn(),
        fetchers={"us_bls_release_calendar": lambda now: [_event(now)]},
        bls_actual_capture=_ActualCapture(),
        consensus_capture=consensus,
    )
    result = cycle.run_once(network_enabled=True, source_ids=["us_bls_release_calendar"], now=1000)
    assert result["status"] == "ok"
    assert result["source_failures"] == 0
    assert result["events_inserted"] == 1
    assert result["consensus_capture"]["status"] == "credential_missing"
    assert consensus.calls == [{"now": 1000.0, "network_enabled": True}]


def test_consensus_transport_failure_marks_cycle_partial_without_order_authority() -> None:
    consensus = _ConsensusCapture(
        {
            "status": "partial",
            "paper_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "credential_exposed": False,
            "capture_failures": 1,
        }
    )
    cycle = IntelligenceIngestCycle(
        conn=_conn(),
        fetchers={"us_bls_release_calendar": lambda now: [_event(now)]},
        bls_actual_capture=_ActualCapture(),
        consensus_capture=consensus,
    )
    result = cycle.run_once(network_enabled=True, source_ids=["us_bls_release_calendar"], now=2000)
    assert result["status"] == "partial"
    assert result["source_failures"] == 1
    assert result["events_inserted"] == 1
    assert result["paper_only"] is True
    assert result["can_place_orders"] is False
    assert result["score_mutation"] is False


def test_non_macro_source_does_not_invoke_consensus_capture() -> None:
    consensus = _ConsensusCapture({"status": "ok"})
    cycle = IntelligenceIngestCycle(
        conn=_conn(),
        fetchers={"us_fed_fomc_calendar": lambda now: []},
        consensus_capture=consensus,
    )
    result = cycle.run_once(network_enabled=True, source_ids=["us_fed_fomc_calendar"], now=3000)
    assert result["status"] == "ok"
    assert result["consensus_capture"]["status"] == "not_requested"
    assert consensus.calls == []
