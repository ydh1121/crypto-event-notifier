from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import b3_trader.intelligence_bls_calendar as bls
from b3_trader.intelligence_bls_calendar import (
    BlsReleaseCalendarSource,
    parse_bls_release_calendar,
)
from b3_trader.intelligence_event_store import IntelligenceEventStore

ET = ZoneInfo("America/New_York")


def _fixture() -> str:
    return "\r\n".join(
        (
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "BEGIN:VEVENT",
            "UID:empsit-2026-08",
            "DTSTART;VALUE=DATE:20260904T083000Z",
            "SUMMARY:Employment Situation for August 2026",
            "DESCRIPTION:Employment Situation for August 2026",
            "LOCATION:Washington\\, DC",
            "STATUS:CONFIRMED",
            "END:VEVENT",
            "BEGIN:VEVENT",
            "UID:cpi-2026-08",
            "DTSTART;TZID=America/New_York:20260911T083000",
            "SUMMARY:Consumer Price Index for August 2026",
            "DESCRIPTION:Consumer Price Index for August 2026",
            "STATUS:CONFIRMED",
            "END:VEVENT",
            "BEGIN:VEVENT",
            "UID:ppi-2026-08",
            "DTSTART:20260910T083000",
            "SUMMARY:Producer Price Index for August 2026",
            "DESCRIPTION:Producer Price Index for August 2026",
            "STATUS:CONFIRMED",
            "END:VEVENT",
            "BEGIN:VEVENT",
            "UID:eci-2026-q3",
            "DTSTART:20261030T083000",
            "SUMMARY:Employment Cost Index for Third Quarter 2026",
            "DESCRIPTION:Employment Cost Index for Third Quarter 2026",
            "STATUS:CONFIRMED",
            "END:VEVENT",
            "BEGIN:VEVENT",
            "UID:jolts-2026-08",
            "DTSTART:20260929T100000",
            "SUMMARY:Job Openings and Labor Turnover Survey for August 2026",
            "STATUS:CONFIRMED",
            "END:VEVENT",
            "BEGIN:VEVENT",
            "UID:cancelled-cpi",
            "DTSTART:20261101T083000",
            "SUMMARY:Consumer Price Index for September 2026",
            "STATUS:CANCELLED",
            "END:VEVENT",
            "BEGIN:VEVENT",
            "UID:date-only",
            "DTSTART;VALUE=DATE:20261201",
            "SUMMARY:Consumer Price Index for October 2026",
            "STATUS:CONFIRMED",
            "END:VEVENT",
            "END:VCALENDAR",
        )
    )


def test_parse_bls_release_calendar_keeps_only_registered_high_impact_bls_events() -> None:
    received = datetime(2026, 9, 4, 0, 0, tzinfo=ET).timestamp()
    events = parse_bls_release_calendar(_fixture(), received_at=received)
    assert [event.event_type for event in events] == [
        "US_EMPLOYMENT",
        "US_CPI",
        "US_PPI",
        "US_ECI",
    ]
    assert all(event.source_id == "us_bls_release_calendar" for event in events)
    assert all(event.confidence is None for event in events)
    assert events[0].attributes["time_semantics"] == "bls_calendar_all_times_eastern"
    assert events[0].attributes["location"] == "Washington, DC"


def test_bls_calendar_treats_displayed_clock_as_eastern_even_when_legacy_z_is_present() -> None:
    events = parse_bls_release_calendar(_fixture(), received_at=1_000_000_000)
    employment = next(event for event in events if event.event_type == "US_EMPLOYMENT")
    expected = datetime(2026, 9, 4, 8, 30, tzinfo=ET).timestamp()
    assert employment.scheduled_at == expected
    assert datetime.fromtimestamp(employment.scheduled_at, ET).hour == 8
    assert employment.freshness_seconds(now=expected - 60) is None


def test_bls_parser_is_bounded_by_window_and_count() -> None:
    start = datetime(2026, 9, 9, 0, 0, tzinfo=ET).timestamp()
    end = datetime(2026, 9, 12, 0, 0, tzinfo=ET).timestamp()
    events = parse_bls_release_calendar(
        _fixture(),
        min_scheduled_at=start,
        max_scheduled_at=end,
        max_events=1,
        received_at=start,
    )
    assert len(events) == 1
    assert events[0].event_type == "US_CPI" or events[0].event_type == "US_PPI"
    assert start <= events[0].scheduled_at <= end


def test_bls_parser_unfolds_ics_text_and_rejects_oversized_payload() -> None:
    folded = "\r\n".join(
        (
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "UID:cpi-folded",
            "DTSTART:20260911T083000",
            "SUMMARY:Consumer Price Index for August",
            " 2026",
            "DESCRIPTION:Consumer Price Index",
            "STATUS:CONFIRMED",
            "END:VEVENT",
            "END:VCALENDAR",
        )
    )
    events = parse_bls_release_calendar(folded, received_at=1_000_000_000)
    assert len(events) == 1
    assert events[0].title == "Consumer Price Index for August2026"

    with pytest.raises(ValueError, match="bounded size"):
        parse_bls_release_calendar("X" * (bls.MAX_ICS_BYTES + 1))


def test_bls_source_reuses_bounded_http_retry_without_network_in_test(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        text = _fixture()

    def fake_get(url: str, **kwargs: object):
        calls.append({"url": url, **kwargs})
        return Response(), 0

    monkeypatch.setattr(bls, "get_with_retry", fake_get)
    now = datetime(2026, 9, 4, 9, 0, tzinfo=ET).timestamp()
    events = BlsReleaseCalendarSource().fetch(
        now=now,
        lookback_seconds=86400,
        horizon_seconds=60 * 86400,
        max_events=10,
    )
    assert {event.event_type for event in events} == {"US_EMPLOYMENT", "US_CPI", "US_PPI", "US_ECI"}
    assert len(calls) == 1
    assert calls[0]["url"] == bls.SOURCE_URL
    assert calls[0]["attempts"] == 3
    assert calls[0]["timeout"] == 12


def test_bls_events_fit_phase5_store_contract() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = IntelligenceEventStore(conn)
    received = datetime(2026, 9, 4, 0, 0, tzinfo=ET).timestamp()
    events = parse_bls_release_calendar(_fixture(), received_at=received)
    result = store.ingest(events, seen_at=received)
    assert result == {"received": 4, "inserted": 4, "updated": 0}
    upcoming = store.upcoming(
        now=received,
        horizon_seconds=90 * 86400,
        limit=20,
    )
    assert len(upcoming) == 4
    assert all(row["freshness_seconds"] is None for row in upcoming)
