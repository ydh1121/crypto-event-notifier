from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from b3_trader.intelligence_bea_actual import (
    BEA_API_URL,
    BEA_PROVIDER_ID,
    EXPECTED_METRIC_IDS,
    PCE_PRICE_INDEX_TABLE,
    PCE_PRICE_MOM_TABLE,
    BeaActualCaptureService,
    BeaNipaClient,
    build_bea_pce_actual_values,
    parse_bea_reference_period,
)
from b3_trader.intelligence_event import normalize_intelligence_event
from b3_trader.intelligence_event_store import IntelligenceEventStore
from b3_trader.intelligence_source_registry import MACRO_CALENDAR


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _event(conn: sqlite3.Connection, *, scheduled_at: float, external_id: str = "pce-fixture") -> str:
    received_at = max(1.0, scheduled_at - 3600)
    event = normalize_intelligence_event(
        source_id="us_bea_release_schedule",
        source_family=MACRO_CALENDAR,
        event_type="US_PCE",
        title="Personal Income and Outlays, July 2026",
        source_url="https://www.bea.gov/news/schedule",
        external_id=external_id,
        scheduled_at=scheduled_at,
        received_at=received_at,
        entities=("US",),
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

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.payload)


class _Client:
    credential_status = "ready"

    def __init__(self, *, mom_data=None, index_data=None, error: Exception | None = None):
        self.mom_data = mom_data or {}
        self.index_data = index_data or {}
        self.error = error
        self.calls = []

    def fetch_table(self, table_name: str, *, years):
        self.calls.append((table_name, tuple(years)))
        if self.error is not None:
            raise self.error
        if table_name == PCE_PRICE_MOM_TABLE:
            return self.mom_data
        if table_name == PCE_PRICE_INDEX_TABLE:
            return self.index_data
        raise AssertionError(table_name)


def _mom_data() -> dict[str, dict[tuple[int, int], float]]:
    return {
        "headline": {(2026, 7): 0.2},
        "core": {(2026, 7): 0.3},
    }


def _index_data() -> dict[str, dict[tuple[int, int], float]]:
    return {
        "headline": {(2026, 7): 125.0, (2025, 7): 120.0},
        "core": {(2026, 7): 123.0, (2025, 7): 120.0},
    }


def test_reference_period_parser_reads_bea_schedule_title() -> None:
    period = parse_bea_reference_period("Personal Income and Outlays, July 2026")
    assert period is not None
    assert period.label == "2026-07"
    assert parse_bea_reference_period("Personal Income and Outlays") is None


def test_client_refuses_missing_or_invalid_key_without_network() -> None:
    session = _Session({})
    missing = BeaNipaClient(user_id="", session=session, attempts=1)
    invalid = BeaNipaClient(user_id="short", session=session, attempts=1)
    assert missing.credential_status == "missing"
    assert invalid.credential_status == "invalid"
    with pytest.raises(ValueError, match="missing"):
        missing.fetch_table(PCE_PRICE_MOM_TABLE, years=[2026])
    with pytest.raises(ValueError, match="invalid"):
        invalid.fetch_table(PCE_PRICE_MOM_TABLE, years=[2026])
    assert session.calls == []


def test_client_queries_bounded_nipa_table_and_matches_descriptions_not_line_numbers() -> None:
    key = "A" * 36
    session = _Session(
        {
            "BEAAPI": {
                "Results": {
                    "Data": [
                        {
                            "TableName": PCE_PRICE_MOM_TABLE,
                            "SeriesCode": "HEADLINE",
                            "LineNumber": "999",
                            "LineDescription": "Personal consumption expenditures (PCE)",
                            "TimePeriod": "2026M7",
                            "DataValue": "0.2",
                        },
                        {
                            "TableName": PCE_PRICE_MOM_TABLE,
                            "SeriesCode": "CORE",
                            "LineNumber": "123",
                            "LineDescription": "PCE excluding food and energy",
                            "TimePeriod": "2026M07",
                            "DataValue": "0.3",
                        },
                        {
                            "TableName": PCE_PRICE_MOM_TABLE,
                            "SeriesCode": "GOODS",
                            "LineNumber": "2",
                            "LineDescription": "Goods",
                            "TimePeriod": "2026M7",
                            "DataValue": "9.9",
                        },
                    ]
                }
            }
        }
    )
    data = BeaNipaClient(user_id=key, session=session, attempts=1).fetch_table(
        PCE_PRICE_MOM_TABLE, years=[2026]
    )
    assert data == {
        "headline": {(2026, 7): 0.2},
        "core": {(2026, 7): 0.3},
    }
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == BEA_API_URL
    assert kwargs["params"]["UserID"] == key
    assert kwargs["params"]["DataSetName"] == "NIPA"
    assert kwargs["params"]["TableName"] == PCE_PRICE_MOM_TABLE
    assert kwargs["params"]["Frequency"] == "M"
    assert kwargs["params"]["Year"] == "2026"


def test_builder_produces_complete_headline_and_core_mom_yoy_without_scoring() -> None:
    values = build_bea_pce_actual_values(
        event_id="evt-pce",
        title="Personal Income and Outlays, July 2026",
        known_at=2000,
        mom_data=_mom_data(),
        index_data=_index_data(),
    )
    assert {value.metric_id for value in values} == set(EXPECTED_METRIC_IDS)
    by_metric = {value.metric_id: value for value in values}
    assert by_metric["US_PCE_PRICE_MOM_PCT"].numeric_value == 0.2
    assert by_metric["US_CORE_PCE_PRICE_MOM_PCT"].numeric_value == 0.3
    assert by_metric["US_PCE_PRICE_YOY_PCT"].numeric_value == pytest.approx(100.0 / 24.0)
    assert by_metric["US_CORE_PCE_PRICE_YOY_PCT"].numeric_value == pytest.approx(2.5)
    assert all(value.provider_id == BEA_PROVIDER_ID for value in values)
    assert all(value.value_role == "actual" for value in values)
    assert all(value.revision_no == 0 for value in values)
    assert all(value.attributes["score_authority"] is False for value in values)
    assert all(value.attributes["credential_exposed"] is False for value in values)


def test_service_missing_credentials_is_fail_closed_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _conn()
    _event(conn, scheduled_at=1000)
    monkeypatch.delenv("BEA_API_KEY", raising=False)
    monkeypatch.delenv("BEA_USER_ID", raising=False)
    client = BeaNipaClient(user_id="")
    result = BeaActualCaptureService(conn, client=client).run_once(now=1010, network_enabled=True)
    assert result["status"] == "credentials_missing"
    assert result["network_requests"] == 0
    assert result["credential_exposed"] is False


def test_service_refuses_historical_backfill_outside_window_without_api_call() -> None:
    conn = _conn()
    _event(conn, scheduled_at=1000, external_id="expired")
    client = _Client(mom_data=_mom_data(), index_data=_index_data())
    result = BeaActualCaptureService(
        conn, client=client, capture_window_seconds=3600
    ).run_once(now=5001, network_enabled=True)
    assert result["missed_capture_window"] == 1
    assert result["events_captured"] == 0
    assert result["network_requests"] == 0
    assert client.calls == []


def test_service_captures_complete_initial_actual_once_and_never_refetches() -> None:
    conn = _conn()
    event_id = _event(conn, scheduled_at=1000, external_id="current")
    client = _Client(mom_data=_mom_data(), index_data=_index_data())
    service = BeaActualCaptureService(conn, client=client, capture_window_seconds=3600)
    first = service.run_once(now=1010, network_enabled=True)
    second = service.run_once(now=1020, network_enabled=True)
    assert first["events_captured"] == 1
    assert first["actual_values_inserted"] == 4
    assert first["network_requests"] == 2
    assert second["already_captured"] == 1
    assert second["network_requests"] == 0
    assert client.calls == [
        (PCE_PRICE_MOM_TABLE, (2025, 2026)),
        (PCE_PRICE_INDEX_TABLE, (2025, 2026)),
    ]
    rows = conn.execute(
        """SELECT metric_id,known_at,revision_no FROM research_intelligence_macro_values
           WHERE event_id=? ORDER BY metric_id""",
        (event_id,),
    ).fetchall()
    assert len(rows) == 4
    assert {row["metric_id"] for row in rows} == set(EXPECTED_METRIC_IDS)
    assert {row["known_at"] for row in rows} == {1010.0}
    assert {row["revision_no"] for row in rows} == {0}


def test_service_incomplete_metric_set_is_atomic_fail_closed() -> None:
    conn = _conn()
    event_id = _event(conn, scheduled_at=1000, external_id="incomplete")
    client = _Client(
        mom_data={"headline": {(2026, 7): 0.2}, "core": {}},
        index_data=_index_data(),
    )
    result = BeaActualCaptureService(conn, client=client).run_once(now=1010, network_enabled=True)
    assert result["capture_failures"] == 1
    assert result["events_captured"] == 0
    count = conn.execute(
        "SELECT COUNT(*) FROM research_intelligence_macro_values WHERE event_id=?",
        (event_id,),
    ).fetchone()[0]
    assert count == 0


def test_bea_actual_module_has_no_score_paper_decision_or_order_dependency() -> None:
    path = Path(__file__).resolve().parents[1] / "intelligence_bea_actual.py"
    text = path.read_text(encoding="utf-8").casefold()
    assert "score_engine" not in text
    assert "paper_engine" not in text
    assert "order_executor" not in text
    assert "trading_decision" not in text
