from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from b3_trader.intelligence_bls_actual import (
    BLS_PUBLIC_API_URL,
    CPI_NSA_ALL_ITEMS,
    CPI_SA_ALL_ITEMS,
    TOTAL_NONFARM_EMPLOYMENT,
    UNEMPLOYMENT_RATE,
    BlsActualCaptureService,
    BlsPublicDataClient,
    build_bls_actual_values,
    parse_bls_reference_period,
)
from b3_trader.intelligence_event import normalize_intelligence_event
from b3_trader.intelligence_event_store import IntelligenceEventStore
from b3_trader.intelligence_source_registry import MACRO_CALENDAR


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    title: str,
    scheduled_at: float,
    external_id: str,
) -> str:
    received_at = max(1.0, scheduled_at - 3600)
    event = normalize_intelligence_event(
        source_id="us_bls_release_calendar",
        source_family=MACRO_CALENDAR,
        event_type=event_type,
        title=title,
        source_url="https://www.bls.gov/schedule/",
        external_id=external_id,
        scheduled_at=scheduled_at,
        received_at=received_at,
    )
    IntelligenceEventStore(conn).ingest([event], seen_at=received_at)
    return event.event_id


class _Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class _Session:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.payload)


class _Client:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def fetch_series(self, series_ids, *, start_year: int, end_year: int):
        self.calls.append((tuple(series_ids), start_year, end_year))
        return self.data


def test_reference_period_parser_reads_bls_calendar_title() -> None:
    period = parse_bls_reference_period("Consumer Price Index for August 2026")
    assert period is not None
    assert period.label == "2026-08"
    assert parse_bls_reference_period("Consumer Price Index release") is None


def test_public_api_client_posts_bounded_series_request_and_parses_months() -> None:
    session = _Session(
        {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [
                    {
                        "seriesID": CPI_SA_ALL_ITEMS,
                        "data": [
                            {"year": "2026", "period": "M08", "value": "325.100"},
                            {"year": "2026", "period": "M13", "value": "999"},
                        ],
                    }
                ]
            },
        }
    )
    data = BlsPublicDataClient(session=session, attempts=1).fetch_series(
        [CPI_SA_ALL_ITEMS], start_year=2025, end_year=2026
    )
    assert data[CPI_SA_ALL_ITEMS][(2026, 8)] == 325.1
    assert (2026, 13) not in data[CPI_SA_ALL_ITEMS]
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == BLS_PUBLIC_API_URL
    assert kwargs["json"] == {
        "seriesid": [CPI_SA_ALL_ITEMS],
        "startyear": "2025",
        "endyear": "2026",
    }


def test_cpi_builder_derives_mom_and_yoy_without_scoring() -> None:
    values = build_bls_actual_values(
        event_id="evt-cpi",
        event_type="US_CPI",
        title="Consumer Price Index for August 2026",
        known_at=2000,
        data={
            CPI_SA_ALL_ITEMS: {(2026, 8): 301.0, (2026, 7): 300.0},
            CPI_NSA_ALL_ITEMS: {(2026, 8): 306.0, (2025, 8): 300.0},
        },
    )
    by_metric = {value.metric_id: value for value in values}
    assert by_metric["US_CPI_ALL_ITEMS_MOM_PCT"].numeric_value == pytest.approx(1 / 3)
    assert by_metric["US_CPI_ALL_ITEMS_YOY_PCT"].numeric_value == pytest.approx(2.0)
    assert all(value.value_role == "actual" for value in values)
    assert all(value.revision_no == 0 for value in values)
    assert all(value.attributes["score_authority"] is False for value in values)


def test_employment_builder_derives_nonfarm_change_and_unemployment_rate() -> None:
    values = build_bls_actual_values(
        event_id="evt-jobs",
        event_type="US_EMPLOYMENT",
        title="Employment Situation for August 2026",
        known_at=3000,
        data={
            TOTAL_NONFARM_EMPLOYMENT: {(2026, 8): 160125.0, (2026, 7): 160000.0},
            UNEMPLOYMENT_RATE: {(2026, 8): 4.2},
        },
    )
    by_metric = {value.metric_id: value.numeric_value for value in values}
    assert by_metric["US_NONFARM_PAYROLL_CHANGE_K"] == 125.0
    assert by_metric["US_UNEMPLOYMENT_RATE_PCT"] == 4.2


def test_capture_service_refuses_historical_backfill_outside_window_without_network() -> None:
    conn = _conn()
    _event(
        conn,
        event_type="US_CPI",
        title="Consumer Price Index for August 2026",
        scheduled_at=1000,
        external_id="cpi-expired",
    )
    client = _Client({})
    result = BlsActualCaptureService(
        conn, client=client, capture_window_seconds=3600
    ).run_once(now=5001, network_enabled=True)
    assert result["missed_capture_window"] == 1
    assert result["events_captured"] == 0
    assert result["network_requests"] == 0
    assert client.calls == []


def test_capture_service_captures_complete_event_once_and_never_refetches() -> None:
    conn = _conn()
    event_id = _event(
        conn,
        event_type="US_CPI",
        title="Consumer Price Index for August 2026",
        scheduled_at=1000,
        external_id="cpi-current",
    )
    client = _Client(
        {
            CPI_SA_ALL_ITEMS: {(2026, 8): 301.0, (2026, 7): 300.0},
            CPI_NSA_ALL_ITEMS: {(2026, 8): 306.0, (2025, 8): 300.0},
        }
    )
    service = BlsActualCaptureService(conn, client=client, capture_window_seconds=3600)
    first = service.run_once(now=1010, network_enabled=True)
    second = service.run_once(now=1020, network_enabled=True)
    assert first["events_captured"] == 1
    assert first["actual_values_inserted"] == 2
    assert first["network_requests"] == 1
    assert second["already_captured"] == 1
    assert second["network_requests"] == 0
    assert len(client.calls) == 1
    rows = conn.execute(
        """SELECT metric_id,known_at,revision_no FROM research_intelligence_macro_values
           WHERE event_id=? ORDER BY metric_id""",
        (event_id,),
    ).fetchall()
    assert len(rows) == 2
    assert {row["known_at"] for row in rows} == {1010.0}
    assert {row["revision_no"] for row in rows} == {0}


def test_capture_service_missing_required_bls_row_is_atomic_fail_closed() -> None:
    conn = _conn()
    event_id = _event(
        conn,
        event_type="US_EMPLOYMENT",
        title="Employment Situation for August 2026",
        scheduled_at=1000,
        external_id="jobs-missing",
    )
    client = _Client(
        {
            TOTAL_NONFARM_EMPLOYMENT: {(2026, 8): 160125.0, (2026, 7): 160000.0},
            UNEMPLOYMENT_RATE: {},
        }
    )
    result = BlsActualCaptureService(conn, client=client).run_once(
        now=1010, network_enabled=True
    )
    assert result["capture_failures"] == 1
    assert result["events_captured"] == 0
    count = conn.execute(
        "SELECT COUNT(*) FROM research_intelligence_macro_values WHERE event_id=?",
        (event_id,),
    ).fetchone()[0]
    assert count == 0


def test_capture_service_network_is_opt_in() -> None:
    conn = _conn()
    _event(
        conn,
        event_type="US_CPI",
        title="Consumer Price Index for August 2026",
        scheduled_at=1000,
        external_id="cpi-offline",
    )
    client = _Client({})
    result = BlsActualCaptureService(conn, client=client).run_once(now=1010)
    assert result["status"] == "network_disabled"
    assert client.calls == []


def test_bls_actual_module_has_no_score_paper_decision_or_order_dependency() -> None:
    path = Path(__file__).resolve().parents[1] / "intelligence_bls_actual.py"
    text = path.read_text(encoding="utf-8").casefold()
    assert "score_engine" not in text
    assert "paper_engine" not in text
    assert "order_executor" not in text
    assert "trading_decision" not in text
