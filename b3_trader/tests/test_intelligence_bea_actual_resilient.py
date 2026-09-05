from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import b3_trader.intelligence_bea_actual_resilient as resilient
from b3_trader.intelligence_bea_actual import BeaNipaClient
from b3_trader.intelligence_bea_actual_resilient import (
    BEA_NEWS_PROVIDER_ID,
    ResilientBeaActualCaptureService,
    parse_bea_pce_news_release,
)
from b3_trader.intelligence_event import normalize_intelligence_event
from b3_trader.intelligence_event_store import IntelligenceEventStore
from b3_trader.intelligence_source_registry import MACRO_CALENDAR

ET = ZoneInfo("America/New_York")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _release_html() -> str:
    return """
    <html><body>
      <h1>Personal Income and Outlays, July 2026</h1>
      <p>
        From the preceding month, the PCE price index for July increased 0.2 percent.
        Excluding food and energy, the PCE price index also increased 0.2 percent.
      </p>
      <p>
        From the same month one year ago, the PCE price index for July increased 3.7 percent.
        Excluding food and energy, the PCE price index increased 3.3 percent from one year ago.
      </p>
    </body></html>
    """


def _store_event(conn: sqlite3.Connection) -> tuple[str, float]:
    scheduled_at = datetime(2026, 8, 26, 8, 30, tzinfo=ET).timestamp()
    event = normalize_intelligence_event(
        source_id="us_bea_release_schedule",
        source_family=MACRO_CALENDAR,
        event_type="US_PCE",
        title="Personal Income and Outlays, July 2026",
        source_url="https://www.bea.gov/news/schedule",
        external_id="pce-july-2026",
        scheduled_at=scheduled_at,
        received_at=scheduled_at - 60,
        entities=("US",),
    )
    IntelligenceEventStore(conn).ingest([event], seen_at=scheduled_at - 60)
    return event.event_id, scheduled_at


def test_news_release_parser_extracts_four_initial_pce_actuals() -> None:
    reference = resilient.parse_bea_reference_period("Personal Income and Outlays, July 2026")
    assert reference is not None
    values = parse_bea_pce_news_release(
        _release_html(),
        event_id="evt-pce",
        reference=reference,
        known_at=1000,
        source_url="https://www.bea.gov/news/2026/personal-income-and-outlays-july-2026",
    )
    by_metric = {value.metric_id: value for value in values}
    assert by_metric["US_PCE_PRICE_MOM_PCT"].numeric_value == 0.2
    assert by_metric["US_CORE_PCE_PRICE_MOM_PCT"].numeric_value == 0.2
    assert by_metric["US_PCE_PRICE_YOY_PCT"].numeric_value == 3.7
    assert by_metric["US_CORE_PCE_PRICE_YOY_PCT"].numeric_value == 3.3
    assert {value.provider_id for value in values} == {BEA_NEWS_PROVIDER_ID}
    assert {value.reference_period for value in values} == {"2026-07"}
    assert all(value.revision_no == 0 for value in values)
    assert all(value.attributes["score_authority"] is False for value in values)


def test_news_release_parser_tolerates_live_inline_markup_and_footnote_text() -> None:
    reference = resilient.parse_bea_reference_period("Personal Income and Outlays, July 2026")
    assert reference is not None
    html = """
    <html><body>
      <h1>Personal Income and Outlays, July 2026</h1>
      <p>
        From the preceding month, the PCE price index for July
        <strong>increased 0.2 percent</strong><sup>1</sup>.
        Excluding food and energy, the PCE price index <em>also</em>
        increased <span>0.2 percent</span>.
      </p>
      <div class="release-note">Chart and table content may appear here.</div>
      <p>
        From the same month one year ago, the PCE price index for July
        increased <strong>3.7 percent</strong><sup>2</sup>.
        Excluding food and energy, the PCE price index
        increased <span>3.3 percent</span> from one year ago.
      </p>
    </body></html>
    """
    values = parse_bea_pce_news_release(
        html,
        event_id="evt-live-markup",
        reference=reference,
        known_at=1000,
        source_url="https://www.bea.gov/news/2026/personal-income-and-outlays-july-2026",
    )
    by_metric = {value.metric_id: value.numeric_value for value in values}
    assert by_metric == {
        "US_PCE_PRICE_MOM_PCT": 0.2,
        "US_CORE_PCE_PRICE_MOM_PCT": 0.2,
        "US_PCE_PRICE_YOY_PCT": 3.7,
        "US_CORE_PCE_PRICE_YOY_PCT": 3.3,
    }


def test_news_release_parser_preserves_negative_direction() -> None:
    reference = resilient.parse_bea_reference_period("Personal Income and Outlays, July 2026")
    assert reference is not None
    html = _release_html().replace(
        "PCE price index for July increased 0.2 percent",
        "PCE price index for July decreased 0.2 percent",
        1,
    )
    values = parse_bea_pce_news_release(
        html,
        event_id="evt-negative",
        reference=reference,
        known_at=1000,
        source_url="https://www.bea.gov/news/2026/personal-income-and-outlays-july-2026",
    )
    by_metric = {value.metric_id: value.numeric_value for value in values}
    assert by_metric["US_PCE_PRICE_MOM_PCT"] == -0.2


def test_missing_bea_api_key_uses_official_news_release_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _conn()
    event_id, scheduled_at = _store_event(conn)
    calls: list[str] = []

    class Response:
        text = _release_html()

    def fake_get(url: str, **kwargs: object):
        calls.append(url)
        return Response(), 0

    monkeypatch.setattr(resilient, "get_with_retry", fake_get)
    service = ResilientBeaActualCaptureService(
        conn,
        client=BeaNipaClient(user_id=""),
    )
    result = service.run_once(now=scheduled_at + 60, network_enabled=True)

    assert result["status"] == "ok"
    assert result["credential_status"] == "missing"
    assert result["provider_mode"] == "official_bea_news_release_fallback"
    assert result["events_captured"] == 1
    assert result["actual_values_inserted"] == 4
    assert result["capture_failures"] == 0
    assert result["network_requests"] == 1
    assert calls == [
        "https://www.bea.gov/news/2026/personal-income-and-outlays-july-2026"
    ]

    rows = conn.execute(
        """SELECT metric_id,provider_id,reference_period,revision_label
           FROM research_intelligence_macro_values
           WHERE event_id=? ORDER BY metric_id""",
        (event_id,),
    ).fetchall()
    assert len(rows) == 4
    assert {row["provider_id"] for row in rows} == {BEA_NEWS_PROVIDER_ID}
    assert {row["reference_period"] for row in rows} == {"2026-07"}
    assert {row["revision_label"] for row in rows} == {"initial_news_release_capture"}


def test_news_release_fallback_is_atomic_fail_closed_on_incomplete_release(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _conn()
    event_id, scheduled_at = _store_event(conn)

    class Response:
        text = "<h1>Personal Income and Outlays, July 2026</h1><p>release incomplete</p>"

    monkeypatch.setattr(resilient, "get_with_retry", lambda *args, **kwargs: (Response(), 0))
    service = ResilientBeaActualCaptureService(
        conn,
        client=BeaNipaClient(user_id=""),
    )
    result = service.run_once(now=scheduled_at + 60, network_enabled=True)

    assert result["status"] == "partial"
    assert result["events_captured"] == 0
    assert result["capture_failures"] == 1
    count = conn.execute(
        "SELECT COUNT(*) FROM research_intelligence_macro_values WHERE event_id=?",
        (event_id,),
    ).fetchone()[0]
    assert count == 0
