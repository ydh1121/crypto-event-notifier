from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests

import b3_trader.intelligence_bls_calendar as bls
from b3_trader.intelligence_bls_calendar import (
    BlsReleaseCalendarSource,
    parse_bls_release_schedule_html,
)

ET = ZoneInfo("America/New_York")


def _html_fixture() -> str:
    return """
    <html><body><table>
      <tr><th>Date</th><th>Time</th><th>Release</th></tr>
      <tr><td>Friday, September 4, 2026</td><td>08:30 AM</td><td>Employment Situation for August 2026</td></tr>
      <tr><td>Thursday, September 10, 2026</td><td>08:30 AM</td><td>Producer Price Index for August 2026</td></tr>
      <tr><td>Friday, September 11, 2026</td><td>08:30 AM</td><td>Consumer Price Index for August 2026</td></tr>
      <tr><td>Friday, October 30, 2026</td><td>08:30 AM</td><td>Employment Cost Index for Third Quarter 2026</td></tr>
      <tr><td>Tuesday, September 29, 2026</td><td>10:00 AM</td><td>Job Openings and Labor Turnover Survey for August 2026</td></tr>
    </table></body></html>
    """


def _http_error(status: int, url: str) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    response.url = url
    return requests.HTTPError(f"{status} for {url}", response=response)


def test_parse_bls_yearly_html_fallback_keeps_registered_high_impact_releases() -> None:
    received = datetime(2026, 9, 4, 9, 0, tzinfo=ET).timestamp()
    events = parse_bls_release_schedule_html(
        _html_fixture(),
        source_url=bls.YEARLY_SCHEDULE_URL.format(year=2026),
        min_scheduled_at=datetime(2026, 9, 4, 0, 0, tzinfo=ET).timestamp(),
        max_scheduled_at=datetime(2026, 11, 1, 0, 0, tzinfo=ET).timestamp(),
        received_at=received,
    )

    assert [event.event_type for event in events] == [
        "US_EMPLOYMENT",
        "US_PPI",
        "US_CPI",
        "US_ECI",
    ]
    assert all(event.source_id == bls.SOURCE_ID for event in events)
    assert all(
        event.attributes["calendar_source_format"] == "official_yearly_html_fallback"
        for event in events
    )
    assert datetime.fromtimestamp(events[0].scheduled_at, ET).hour == 8


def test_bls_source_falls_back_to_official_yearly_html_on_ics_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        text = _html_fixture()

    def fake_get(url: str, **kwargs: object):
        calls.append({"url": url, **kwargs})
        if url == bls.SOURCE_URL:
            raise _http_error(403, url)
        assert url == bls.YEARLY_SCHEDULE_URL.format(year=2026)
        return Response(), 0

    monkeypatch.setattr(bls, "get_with_retry", fake_get)
    now = datetime(2026, 9, 4, 9, 0, tzinfo=ET).timestamp()
    events = BlsReleaseCalendarSource().fetch(
        now=now,
        lookback_seconds=86400,
        horizon_seconds=90 * 86400,
        max_events=10,
    )

    assert {event.event_type for event in events} == {
        "US_EMPLOYMENT",
        "US_CPI",
        "US_PPI",
        "US_ECI",
    }
    assert [call["url"] for call in calls] == [
        bls.SOURCE_URL,
        bls.YEARLY_SCHEDULE_URL.format(year=2026),
    ]
    assert "+https://github.com/ydh1121/crypto-event-notifier" in bls.USER_AGENT


def test_bls_source_does_not_mask_unrelated_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, **kwargs: object):
        raise _http_error(500, url)

    monkeypatch.setattr(bls, "get_with_retry", fake_get)
    with pytest.raises(requests.HTTPError):
        BlsReleaseCalendarSource().fetch(
            now=datetime(2026, 9, 4, 9, 0, tzinfo=ET).timestamp(),
            horizon_seconds=30 * 86400,
        )
