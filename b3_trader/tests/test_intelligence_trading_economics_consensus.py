from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from b3_trader.intelligence_event import normalize_intelligence_event
from b3_trader.intelligence_event_store import IntelligenceEventStore
from b3_trader.intelligence_source_registry import MACRO_CALENDAR
from b3_trader.intelligence_trading_economics_consensus import (
    TE_PROVIDER_ID,
    TradingEconomicsCalendarClient,
    TradingEconomicsConsensusCaptureService,
    build_trading_economics_consensus_values,
)

UTC = timezone.utc


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _stamp(year: int, month: int, day: int, hour: int = 12, minute: int = 30) -> float:
    return datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp()


def _event(conn: sqlite3.Connection, *, event_type: str, source_id: str, scheduled_at: float, external_id: str) -> str:
    event = normalize_intelligence_event(
        source_id=source_id,
        source_family=MACRO_CALENDAR,
        event_type=event_type,
        title=f"{event_type} fixture",
        source_url="https://example.com/official",
        external_id=external_id,
        scheduled_at=scheduled_at,
        received_at=scheduled_at - 86400,
        entities=("US",),
    )
    IntelligenceEventStore(conn).ingest([event], seen_at=scheduled_at - 86400)
    return event.event_id


def _row(event: str, forecast: str, reference_date: str, *, date: str = "2026-09-11T12:30:00", unit: str = "%") -> dict[str, object]:
    return {
        "CalendarId": f"id-{event}",
        "Date": date,
        "Country": "United States",
        "Category": event,
        "Event": event,
        "Reference": "Aug",
        "ReferenceDate": reference_date,
        "Source": "Official source",
        "SourceURL": "https://example.com/source",
        "Forecast": forecast,
        "ForecastValue": None,
        "DateSpan": "0",
        "Importance": 3,
        "LastUpdate": "2026-09-11T11:45:00",
        "Unit": unit,
        "Ticker": event.upper().replace(" ", ""),
        "Symbol": event.upper().replace(" ", ""),
    }


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

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.payload)


class _Client:
    credential_status = "ready"

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def fetch_us_calendar(self, *, start_at: float, end_at: float):
        self.calls.append((start_at, end_at))
        return list(self.rows)


class _MissingClient:
    credential_status = "missing"

    def __init__(self):
        self.calls = []

    def fetch_us_calendar(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("network must not be called without credential")


def test_client_uses_authorization_header_and_never_puts_key_in_url() -> None:
    session = _Session([])
    client = TradingEconomicsCalendarClient(api_key="secret-key", session=session, attempts=1)
    start = _stamp(2026, 9, 11)
    assert client.fetch_us_calendar(start_at=start, end_at=start) == []
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert "secret-key" not in url
    assert kwargs["headers"]["Authorization"] == "secret-key"
    assert kwargs["params"] == {"values": "true", "f": "json"}


def test_cpi_consensus_builder_requires_complete_pre_release_snapshot() -> None:
    scheduled = _stamp(2026, 9, 11)
    rows = [
        _row("Inflation Rate MoM", "0.3%", "2026-08-31T00:00:00"),
        _row("Inflation Rate YoY", "3.4%", "2026-08-31T00:00:00"),
    ]
    values = build_trading_economics_consensus_values(
        event_id="evt-cpi",
        event_type="US_CPI",
        scheduled_at=scheduled,
        rows=rows,
        known_at=scheduled - 900,
    )
    by_metric = {value.metric_id: value for value in values}
    assert by_metric["US_CPI_ALL_ITEMS_MOM_PCT"].numeric_value == 0.3
    assert by_metric["US_CPI_ALL_ITEMS_YOY_PCT"].numeric_value == 3.4
    assert {value.reference_period for value in values} == {"2026-08"}
    assert all(value.value_role == "consensus" for value in values)
    assert all(value.provider_id == TE_PROVIDER_ID for value in values)
    assert all(value.known_at < scheduled for value in values)
    assert all(value.attributes["score_authority"] is False for value in values)

    with pytest.raises(ValueError, match="incomplete"):
        build_trading_economics_consensus_values(
            event_id="evt-cpi",
            event_type="US_CPI",
            scheduled_at=scheduled,
            rows=rows[:1],
            known_at=scheduled - 900,
        )


def test_employment_consensus_normalizes_nfp_to_thousands() -> None:
    scheduled = _stamp(2026, 9, 4)
    rows = [
        _row("Non Farm Payrolls", "80K", "2026-08-31T00:00:00", date="2026-09-04T12:30:00", unit="K"),
        _row("Unemployment Rate", "4.2%", "2026-08-31T00:00:00", date="2026-09-04T12:30:00"),
    ]
    values = build_trading_economics_consensus_values(
        event_id="evt-jobs",
        event_type="US_EMPLOYMENT",
        scheduled_at=scheduled,
        rows=rows,
        known_at=scheduled - 600,
    )
    by_metric = {value.metric_id: value for value in values}
    assert by_metric["US_NONFARM_PAYROLL_CHANGE_K"].numeric_value == 80.0
    assert by_metric["US_NONFARM_PAYROLL_CHANGE_K"].unit == "THOUSANDS"
    assert by_metric["US_UNEMPLOYMENT_RATE_PCT"].numeric_value == 4.2


def test_pce_consensus_builder_maps_headline_and_core_mom_yoy() -> None:
    scheduled = _stamp(2026, 9, 30)
    rows = [
        _row("PCE Price Index MoM", "0.2%", "2026-08-31T00:00:00", date="2026-09-30T12:30:00"),
        _row("Core PCE Price Index MoM", "0.2%", "2026-08-31T00:00:00", date="2026-09-30T12:30:00"),
        _row("PCE Price Index YoY", "3.6%", "2026-08-31T00:00:00", date="2026-09-30T12:30:00"),
        _row("Core PCE Price Index YoY", "3.3%", "2026-08-31T00:00:00", date="2026-09-30T12:30:00"),
    ]
    values = build_trading_economics_consensus_values(
        event_id="evt-pce",
        event_type="US_PCE",
        scheduled_at=scheduled,
        rows=rows,
        known_at=scheduled - 1200,
    )
    assert {value.metric_id for value in values} == {
        "US_PCE_PRICE_MOM_PCT",
        "US_CORE_PCE_PRICE_MOM_PCT",
        "US_PCE_PRICE_YOY_PCT",
        "US_CORE_PCE_PRICE_YOY_PCT",
    }


def test_capture_service_missing_credential_and_post_release_do_not_call_network() -> None:
    conn = _conn()
    scheduled = _stamp(2026, 9, 11)
    _event(conn, event_type="US_CPI", source_id="us_bls_release_calendar", scheduled_at=scheduled, external_id="cpi")
    missing = _MissingClient()
    result = TradingEconomicsConsensusCaptureService(conn, client=missing).run_once(
        now=scheduled - 1200, network_enabled=True
    )
    assert result["status"] == "credential_missing"
    assert result["network_requests"] == 0
    assert missing.calls == []

    ready = _Client([])
    result = TradingEconomicsConsensusCaptureService(conn, client=ready).run_once(
        now=scheduled + 1, network_enabled=True
    )
    assert result["status"] == "idle"
    assert result["network_requests"] == 0
    assert ready.calls == []


def test_capture_service_stores_complete_snapshot_once_and_never_refetches() -> None:
    conn = _conn()
    scheduled = _stamp(2026, 9, 11)
    event_id = _event(
        conn,
        event_type="US_CPI",
        source_id="us_bls_release_calendar",
        scheduled_at=scheduled,
        external_id="cpi-live",
    )
    client = _Client(
        [
            _row("Inflation Rate MoM", "0.3%", "2026-08-31T00:00:00"),
            _row("Inflation Rate YoY", "3.4%", "2026-08-31T00:00:00"),
        ]
    )
    service = TradingEconomicsConsensusCaptureService(conn, client=client)
    first = service.run_once(now=scheduled - 1200, network_enabled=True)
    second = service.run_once(now=scheduled - 600, network_enabled=True)
    assert first["events_captured"] == 1
    assert first["consensus_values_inserted"] == 2
    assert first["network_requests"] == 1
    assert second["already_captured"] == 1
    assert second["network_requests"] == 0
    assert len(client.calls) == 1
    rows = conn.execute(
        """SELECT metric_id,known_at FROM research_intelligence_macro_values
           WHERE event_id=? AND provider_id=? ORDER BY metric_id""",
        (event_id, TE_PROVIDER_ID),
    ).fetchall()
    assert len(rows) == 2
    assert {row["known_at"] for row in rows} == {scheduled - 1200}


def test_capture_service_incomplete_snapshot_is_atomic_and_retriable() -> None:
    conn = _conn()
    scheduled = _stamp(2026, 9, 11)
    event_id = _event(
        conn,
        event_type="US_CPI",
        source_id="us_bls_release_calendar",
        scheduled_at=scheduled,
        external_id="cpi-incomplete",
    )
    client = _Client([_row("Inflation Rate MoM", "0.3%", "2026-08-31T00:00:00")])
    result = TradingEconomicsConsensusCaptureService(conn, client=client).run_once(
        now=scheduled - 1200, network_enabled=True
    )
    assert result["status"] == "ok"
    assert result["incomplete_consensus"] == 1
    assert result["events_captured"] == 0
    count = conn.execute(
        "SELECT COUNT(*) FROM research_intelligence_macro_values WHERE event_id=? AND provider_id=?",
        (event_id, TE_PROVIDER_ID),
    ).fetchone()[0]
    assert count == 0


def test_consensus_module_has_no_score_paper_decision_or_order_dependency() -> None:
    path = Path(__file__).resolve().parents[1] / "intelligence_trading_economics_consensus.py"
    text = path.read_text(encoding="utf-8").casefold()
    assert "score_engine" not in text
    assert "paper_engine" not in text
    assert "order_executor" not in text
    assert "trading_decision" not in text
