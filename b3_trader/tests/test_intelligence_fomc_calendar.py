from __future__ import annotations

import sqlite3

import pytest

import b3_trader.intelligence_fomc_calendar as fomc
from b3_trader.intelligence_event_store import IntelligenceEventStore
from b3_trader.intelligence_fomc_calendar import FomcMeetingCalendarSource, parse_fomc_meeting_calendar


def _fixture() -> str:
    return """
    <html><body>
      <h4>2026 FOMC Meetings</h4>
      <div><span>January</span><span>27-28</span><span>Statement:</span><a>HTML</a></div>
      <div><span>Minutes:</span><span>(Released February 18, 2026)</span></div>
      <div><span>March</span><span>17-18*</span><span>Projection Materials</span></div>
      <div><span>April</span><span>28-29</span></div>
      <div><span>June</span><span>16-17*</span></div>
      <div><span>July</span><span>28-29</span></div>
      <div><span>September</span><span>15-16*</span></div>
      <div><span>October</span><span>27-28</span></div>
      <div><span>December</span><span>8-9*</span></div>
      <p>* Meeting associated with a Summary of Economic Projections.</p>
      <h4>2025 FOMC Meetings</h4>
      <div><span>August</span><span>22 (notation vote)</span></div>
      <div><span>September</span><span>16-17*</span></div>
      <h4>2024 FOMC Meetings</h4>
      <div><span>Apr/May</span><span>30-1</span></div>
    </body></html>
    """


def test_fomc_parser_extracts_meeting_date_ranges_without_inventing_clock_time() -> None:
    events = parse_fomc_meeting_calendar(_fixture(), min_year=2026, max_year=2026, received_at=1000)
    assert len(events) == 8
    september = next(event for event in events if event.attributes["scheduled_date_start"] == "2026-09-15")
    assert september.attributes["scheduled_date_end"] == "2026-09-16"
    assert september.attributes["projection_meeting"] is True
    assert september.attributes["date_only"] is True
    assert september.attributes["exact_release_time_known"] is False
    assert september.scheduled_at == 0
    assert september.source_ts == 0
    assert september.freshness_seconds(now=2000) is None


def test_fomc_parser_does_not_misread_minutes_release_text_or_notation_vote_as_meeting() -> None:
    events = parse_fomc_meeting_calendar(_fixture(), min_year=2025, max_year=2026, received_at=1000)
    starts = {event.attributes["scheduled_date_start"] for event in events}
    assert "2026-02-18" not in starts
    assert "2025-08-22" not in starts
    assert "2025-09-16" in starts


def test_fomc_parser_handles_cross_month_meeting_and_year_filter() -> None:
    events = parse_fomc_meeting_calendar(_fixture(), min_year=2024, max_year=2024, received_at=1000)
    assert len(events) == 1
    assert events[0].attributes["scheduled_date_start"] == "2024-04-30"
    assert events[0].attributes["scheduled_date_end"] == "2024-05-01"


def test_fomc_parser_is_bounded() -> None:
    events = parse_fomc_meeting_calendar(_fixture(), min_year=2026, max_year=2026, max_events=2, received_at=1000)
    assert len(events) == 2
    with pytest.raises(ValueError, match="bounded size"):
        parse_fomc_meeting_calendar("X" * (fomc.MAX_HTML_BYTES + 1))


def test_fomc_source_uses_shared_retry_without_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        text = _fixture()

    def fake_get(url: str, **kwargs: object):
        calls.append({"url": url, **kwargs})
        return Response(), 0

    monkeypatch.setattr(fomc, "get_with_retry", fake_get)
    events = FomcMeetingCalendarSource().fetch(min_year=2026, max_year=2026, received_at=1000)
    assert len(events) == 8
    assert calls == [
        {
            "url": fomc.SOURCE_URL,
            "headers": {
                "User-Agent": fomc.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            },
            "timeout": 12,
            "attempts": 3,
        }
    ]


def test_fomc_date_only_events_fit_phase5_store_contract() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = IntelligenceEventStore(conn)
    events = parse_fomc_meeting_calendar(_fixture(), min_year=2026, max_year=2026, received_at=1000)
    assert store.ingest(events, seen_at=1000) == {
        "received": 8,
        "inserted": 8,
        "updated": 0,
    }
    rows = store.recent(source_id="us_fed_fomc_calendar", limit=20, now=2000)
    assert len(rows) == 8
    assert all(row["scheduled_at"] == 0 for row in rows)
    assert all(row["attributes"]["date_only"] is True for row in rows)
