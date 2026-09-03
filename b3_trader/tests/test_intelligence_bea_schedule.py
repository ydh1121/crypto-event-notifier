from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import b3_trader.intelligence_bea_schedule as bea
from b3_trader.intelligence_bea_schedule import BeaReleaseScheduleSource, parse_bea_release_schedule
from b3_trader.intelligence_event_store import IntelligenceEventStore

ET = ZoneInfo("America/New_York")


def _fixture() -> str:
    return """
    <html><body>
      <div>Year 2026</div>
      <table>
        <tr><th>Date</th><th>Release type</th><th>Release</th></tr>
        <tr><td>August 26 8:30 AM</td><td>News</td><td>GDP (Second Estimate) and Corporate Profits, 2nd Quarter 2026</td></tr>
        <tr><td>August 26 8:30 AM</td><td>News</td><td>Personal Income and Outlays, July 2026</td></tr>
        <tr><td>September 3 8:30 AM</td><td>News</td><td>U.S. International Trade in Goods and Services, July 2026</td></tr>
        <tr><td>October 6 10:00 AM</td><td>Data</td><td>Services Supplied Through Affiliates, 2024</td></tr>
        <tr><td>To Be Announced</td><td>News</td><td>Personal Income and Outlays, December 2026</td></tr>
      </table>
    </body></html>
    """


def test_bea_parser_keeps_only_registered_macro_release_families() -> None:
    received = datetime(2026, 8, 20, 0, 0, tzinfo=ET).timestamp()
    events = parse_bea_release_schedule(_fixture(), received_at=received)
    assert [event.event_type for event in events] == ["US_GDP", "US_PCE", "US_TRADE"]
    assert all(event.source_id == "us_bea_release_schedule" for event in events)
    assert all(event.attributes["calendar_timezone"] == "America/New_York" for event in events)
    assert all(event.confidence is None for event in events)


def test_bea_schedule_uses_explicit_eastern_clock_and_does_not_invent_tba_time() -> None:
    events = parse_bea_release_schedule(_fixture(), received_at=1_000_000_000)
    gdp = next(event for event in events if event.event_type == "US_GDP")
    expected = datetime(2026, 8, 26, 8, 30, tzinfo=ET).timestamp()
    assert gdp.scheduled_at == expected
    assert datetime.fromtimestamp(gdp.scheduled_at, ET).hour == 8
    assert not any("December 2026" in event.title for event in events)


def test_bea_parser_window_and_payload_bounds() -> None:
    start = datetime(2026, 9, 1, 0, 0, tzinfo=ET).timestamp()
    end = datetime(2026, 9, 5, 0, 0, tzinfo=ET).timestamp()
    events = parse_bea_release_schedule(
        _fixture(),
        min_scheduled_at=start,
        max_scheduled_at=end,
        max_events=10,
        received_at=start,
    )
    assert len(events) == 1
    assert events[0].event_type == "US_TRADE"

    with pytest.raises(ValueError, match="bounded size"):
        parse_bea_release_schedule("X" * (bea.MAX_HTML_BYTES + 1))


def test_bea_source_uses_shared_bounded_retry_without_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        text = _fixture()

    def fake_get(url: str, **kwargs: object):
        calls.append({"url": url, **kwargs})
        return Response(), 0

    monkeypatch.setattr(bea, "get_with_retry", fake_get)
    now = datetime(2026, 8, 20, 12, 0, tzinfo=ET).timestamp()
    events = BeaReleaseScheduleSource().fetch(
        now=now,
        lookback_seconds=0,
        horizon_seconds=60 * 86400,
        max_events=10,
    )
    assert {event.event_type for event in events} == {"US_GDP", "US_PCE", "US_TRADE"}
    assert calls == [
        {
            "url": bea.SOURCE_URL,
            "headers": {
                "User-Agent": bea.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            },
            "timeout": 12,
            "attempts": 3,
        }
    ]


def test_bea_events_ingest_into_phase5_store() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = IntelligenceEventStore(conn)
    received = datetime(2026, 8, 20, 0, 0, tzinfo=ET).timestamp()
    events = parse_bea_release_schedule(_fixture(), received_at=received)
    assert store.ingest(events, seen_at=received) == {
        "received": 3,
        "inserted": 3,
        "updated": 0,
    }
    upcoming = store.upcoming(now=received, horizon_seconds=60 * 86400, limit=20)
    assert {row["event_type"] for row in upcoming} == {"US_GDP", "US_PCE", "US_TRADE"}
