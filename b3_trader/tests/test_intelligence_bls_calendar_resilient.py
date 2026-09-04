from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests

import b3_trader.intelligence_bls_calendar_resilient as resilient
from b3_trader.intelligence_bls_calendar_resilient import (
    ResilientBlsReleaseCalendarSource,
    parse_fred_bls_release_calendar_html,
)

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")


def _fred_fixture(title: str, date_text: str, time_text: str = "7:30 am") -> str:
    return f"""
    <html><body><table>
      <tr><th>Date</th><th>Time</th><th>Release</th></tr>
      <tr><td>{date_text} Updated</td><td>{time_text}</td><td>{title}</td></tr>
    </table></body></html>
    """


def _http_error(status: int, url: str) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    response.url = url
    return requests.HTTPError(f"{status} for {url}", response=response)


def test_parse_fred_secondary_calendar_uses_central_time_and_preserves_provenance() -> None:
    url = resilient.FRED_RELEASE_CALENDAR_URL.format(release_id=50, year=2026)
    received = datetime(2026, 9, 4, 9, 0, tzinfo=ET).timestamp()
    events = parse_fred_bls_release_calendar_html(
        _fred_fixture("Employment Situation", "Friday September 04, 2026"),
        source_url=url,
        expected_event_type="US_EMPLOYMENT",
        expected_title="Employment Situation",
        received_at=received,
    )

    assert len(events) == 1
    event = events[0]
    assert event.source_id == resilient.SOURCE_ID
    assert event.source_url == url
    assert datetime.fromtimestamp(event.scheduled_at, CT).hour == 7
    assert datetime.fromtimestamp(event.scheduled_at, ET).hour == 8
    assert event.attributes["calendar_source_format"] == "official_fred_secondary_calendar_fallback"
    assert event.attributes["calendar_source_authority"] == "Federal Reserve Bank of St. Louis (FRED)"
    assert event.attributes["upstream_release_agency"] == "U.S. Bureau of Labor Statistics"


def test_resilient_source_uses_fred_after_terminal_bls_403(monkeypatch: pytest.MonkeyPatch) -> None:
    class Primary:
        url = "https://www.bls.gov/schedule/news_release/bls.ics"

        def fetch(self, **kwargs: object):
            raise _http_error(403, self.url)

    fixtures = {
        50: _fred_fixture("Employment Situation", "Friday September 04, 2026"),
        10: _fred_fixture("Consumer Price Index", "Friday September 11, 2026"),
        46: _fred_fixture("Producer Price Index", "Thursday September 10, 2026"),
        11: _fred_fixture("Employment Cost Index", "Friday October 30, 2026"),
    }
    calls: list[str] = []

    class Response:
        def __init__(self, text: str) -> None:
            self.text = text

    def fake_get(url: str, **kwargs: object):
        calls.append(url)
        match = next(
            (release_id for _, release_id, _ in resilient.FRED_RELEASES if f"rid={release_id}" in url),
            None,
        )
        assert match is not None
        return Response(fixtures[match]), 0

    monkeypatch.setattr(resilient, "get_with_retry", fake_get)
    source = ResilientBlsReleaseCalendarSource(primary=Primary())
    now = datetime(2026, 9, 4, 9, 0, tzinfo=ET).timestamp()
    events = source.fetch(
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
    assert len(calls) == 4
    assert all("fred.stlouisfed.org/releases/calendar" in url for url in calls)


def test_resilient_source_does_not_mask_non_terminal_primary_failure() -> None:
    class Primary:
        url = "https://www.bls.gov/schedule/news_release/bls.ics"

        def fetch(self, **kwargs: object):
            raise _http_error(500, self.url)

    source = ResilientBlsReleaseCalendarSource(primary=Primary())
    with pytest.raises(requests.HTTPError):
        source.fetch(now=datetime(2026, 9, 4, 9, 0, tzinfo=ET).timestamp())
