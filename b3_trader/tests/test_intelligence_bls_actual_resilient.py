from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from b3_trader.intelligence_bls_actual import (
    TOTAL_NONFARM_EMPLOYMENT,
    UNEMPLOYMENT_RATE,
)
from b3_trader.intelligence_bls_actual_resilient import (
    FRED_FALLBACK_FORMAT,
    BlsActualCaptureService,
)
from b3_trader.intelligence_event import normalize_intelligence_event
from b3_trader.intelligence_event_store import IntelligenceEventStore
from b3_trader.intelligence_source_registry import MACRO_CALENDAR

ET = ZoneInfo("America/New_York")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class _Client:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def fetch_series(self, series_ids, *, start_year: int, end_year: int):
        self.calls.append((tuple(series_ids), start_year, end_year))
        return self.data


def _store_event(
    conn: sqlite3.Connection,
    *,
    source_url: str,
    attributes: dict[str, object],
) -> tuple[str, float]:
    scheduled_at = datetime(2026, 9, 4, 8, 30, tzinfo=ET).timestamp()
    event = normalize_intelligence_event(
        source_id="us_bls_release_calendar",
        source_family=MACRO_CALENDAR,
        event_type="US_EMPLOYMENT",
        title="Employment Situation",
        source_url=source_url,
        external_id="us_employment-20260904T0830",
        scheduled_at=scheduled_at,
        received_at=scheduled_at - 60,
        attributes=attributes,
    )
    IntelligenceEventStore(conn).ingest([event], seen_at=scheduled_at - 60)
    return event.event_id, scheduled_at


def test_fred_fallback_generic_title_resolves_previous_month_with_audit_attributes() -> None:
    conn = _conn()
    event_id, scheduled_at = _store_event(
        conn,
        source_url="https://fred.stlouisfed.org/releases/calendar?rid=50&y=2026",
        attributes={
            "calendar_source_format": FRED_FALLBACK_FORMAT,
            "calendar_source_authority": "Federal Reserve Bank of St. Louis (FRED)",
            "upstream_release_agency": "U.S. Bureau of Labor Statistics",
        },
    )
    client = _Client(
        {
            TOTAL_NONFARM_EMPLOYMENT: {
                (2026, 8): 160125.0,
                (2026, 7): 160000.0,
            },
            UNEMPLOYMENT_RATE: {(2026, 8): 4.2},
        }
    )

    result = BlsActualCaptureService(conn, client=client).run_once(
        now=scheduled_at + 60,
        network_enabled=True,
    )

    assert result["status"] == "ok"
    assert result["events_captured"] == 1
    assert result["actual_values_inserted"] == 2
    assert result["capture_failures"] == 0
    assert client.calls == [
        ((TOTAL_NONFARM_EMPLOYMENT, UNEMPLOYMENT_RATE), 2025, 2026)
    ]

    rows = conn.execute(
        """SELECT metric_id,reference_period,attributes_json
           FROM research_intelligence_macro_values
           WHERE event_id=? ORDER BY metric_id""",
        (event_id,),
    ).fetchall()
    assert len(rows) == 2
    assert {row["reference_period"] for row in rows} == {"2026-08"}
    for row in rows:
        attrs = json.loads(row["attributes_json"])
        assert attrs["reference_period_source"] == "fred_calendar_previous_month_inference"
        assert attrs["reference_period_inference"] == "previous_calendar_month_from_release_schedule"
        assert attrs["schedule_source_format"] == FRED_FALLBACK_FORMAT
        assert attrs["source_title_preserved"] == "Employment Situation"


def test_generic_title_without_verified_fred_provenance_fails_closed_before_client_fetch() -> None:
    conn = _conn()
    _, scheduled_at = _store_event(
        conn,
        source_url="https://www.bls.gov/schedule/",
        attributes={},
    )
    client = _Client({})

    result = BlsActualCaptureService(conn, client=client).run_once(
        now=scheduled_at + 60,
        network_enabled=True,
    )

    assert result["status"] == "partial"
    assert result["events_captured"] == 0
    assert result["capture_failures"] == 1
    assert client.calls == []
    assert "verified FRED fallback provenance" in result["errors"][0]["error"]
