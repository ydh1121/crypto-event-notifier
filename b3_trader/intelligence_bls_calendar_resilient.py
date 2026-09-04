from __future__ import annotations

import re
import time
from datetime import datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import requests

from .http_retry import get_with_retry
from .intelligence_bls_calendar import (
    DEFAULT_HORIZON_SECONDS,
    DEFAULT_LOOKBACK_SECONDS,
    DEFAULT_MAX_EVENTS,
    MAX_HTML_BYTES,
    SOURCE_ID,
    USER_AGENT,
    BlsReleaseCalendarSource as PrimaryBlsReleaseCalendarSource,
)
from .intelligence_event import IntelligenceEvent, normalize_intelligence_event
from .intelligence_source_registry import MACRO_CALENDAR

FRED_TIMEZONE = ZoneInfo("America/Chicago")
EASTERN_TIMEZONE = ZoneInfo("America/New_York")
FRED_RELEASE_CALENDAR_URL = "https://fred.stlouisfed.org/releases/calendar?rid={release_id}&y={year}"
FRED_RELEASES: tuple[tuple[str, int, str], ...] = (
    ("US_EMPLOYMENT", 50, "Employment Situation"),
    ("US_CPI", 10, "Consumer Price Index"),
    ("US_PPI", 46, "Producer Price Index"),
    ("US_ECI", 11, "Employment Cost Index"),
)
_MONTH_RE = (
    r"(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
)


class _FredCalendarHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if lower == "tr":
            self._row = []
            self._cell = None
        elif lower in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._cell is None:
            return
        self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if lower in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif lower == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def _parse_fred_release_clock(value: str) -> float:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    date_match = re.search(
        rf"{_MONTH_RE}\s+(\d{{1,2}}),\s+(\d{{4}})",
        normalized,
        flags=re.IGNORECASE,
    )
    time_match = re.search(
        r"(\d{1,2}):(\d{2})\s*([AP])\.?\s*M\.?",
        normalized,
        flags=re.IGNORECASE,
    )
    if not date_match or not time_match:
        return 0.0

    month, day, year = date_match.groups()
    hour, minute, meridiem = time_match.groups()
    try:
        parsed = datetime.strptime(
            f"{month} {day} {year} {hour}:{minute} {meridiem.upper()}M",
            "%B %d %Y %I:%M %p",
        ).replace(tzinfo=FRED_TIMEZONE)
    except ValueError:
        return 0.0
    return parsed.timestamp()


def parse_fred_bls_release_calendar_html(
    text: str,
    *,
    source_url: str,
    expected_event_type: str,
    expected_title: str,
    received_at: float | None = None,
) -> list[IntelligenceEvent]:
    payload = str(text or "")
    if len(payload.encode("utf-8", errors="ignore")) > MAX_HTML_BYTES:
        raise ValueError("FRED calendar HTML payload exceeds bounded size")

    parser = _FredCalendarHtmlParser()
    parser.feed(payload)
    parser.close()

    received = float(received_at if received_at is not None else time.time())
    expected_name = re.sub(r"\s+", " ", expected_title).strip().casefold()
    output: list[IntelligenceEvent] = []

    for cells in parser.rows:
        title_index = -1
        title = ""
        for index, cell in enumerate(cells):
            normalized = re.sub(r"\s+", " ", str(cell or "")).strip()
            if normalized.casefold() == expected_name:
                title_index = index
                title = normalized
                break
        if title_index < 0:
            continue

        scheduled_at = _parse_fred_release_clock(" ".join(cells[:title_index]))
        if scheduled_at <= 0:
            continue

        eastern = datetime.fromtimestamp(scheduled_at, EASTERN_TIMEZONE)
        external_id = f"{expected_event_type.lower()}-{eastern.strftime('%Y%m%dT%H%M')}"
        output.append(
            normalize_intelligence_event(
                source_id=SOURCE_ID,
                source_family=MACRO_CALENDAR,
                event_type=expected_event_type,
                title=title,
                source_url=source_url,
                external_id=external_id,
                scheduled_at=scheduled_at,
                received_at=received,
                entities=("US",),
                market_scope=("GLOBAL", "CRYPTO"),
                attributes={
                    "calendar_timezone": "America/Chicago",
                    "time_semantics": "fred_release_calendar_all_times_central",
                    "calendar_source_format": "official_fred_secondary_calendar_fallback",
                    "calendar_source_authority": "Federal Reserve Bank of St. Louis (FRED)",
                    "upstream_release_agency": "U.S. Bureau of Labor Statistics",
                },
            )
        )

    output.sort(key=lambda event: (event.scheduled_at, event.event_type, event.title))
    return output


def _window_years(min_scheduled_at: float, max_scheduled_at: float, current: float) -> list[int]:
    lower = float(min_scheduled_at or current)
    upper = float(max_scheduled_at or current)
    if upper < lower:
        lower, upper = upper, lower
    first = datetime.fromtimestamp(lower, EASTERN_TIMEZONE).year
    last = datetime.fromtimestamp(upper, EASTERN_TIMEZONE).year
    return list(range(first, min(last, first + 2) + 1))


class ResilientBlsReleaseCalendarSource:
    """BLS calendar with a bounded official secondary fallback.

    The BLS ICS/yearly HTML adapter remains primary. If the BLS host returns a
    terminal access-control/not-found response, use the public FRED release
    calendar maintained by the Federal Reserve Bank of St. Louis. FRED states
    that its release dates are published by the data sources; provenance is kept
    on each normalized event and the adapter remains research/PAPER-unwired.
    """

    source_id = SOURCE_ID
    url = PrimaryBlsReleaseCalendarSource.url

    def __init__(self, primary: PrimaryBlsReleaseCalendarSource | None = None) -> None:
        self.primary = primary or PrimaryBlsReleaseCalendarSource()

    def _fetch_fred_secondary(
        self,
        *,
        current: float,
        min_scheduled_at: float,
        max_scheduled_at: float,
        max_events: int,
    ) -> list[IntelligenceEvent]:
        events: list[IntelligenceEvent] = []
        seen_ids: set[str] = set()
        current_year = datetime.fromtimestamp(current, EASTERN_TIMEZONE).year

        for year in _window_years(min_scheduled_at, max_scheduled_at, current):
            for event_type, release_id, title in FRED_RELEASES:
                url = FRED_RELEASE_CALENDAR_URL.format(release_id=release_id, year=year)
                try:
                    response, _ = get_with_retry(
                        url,
                        headers={
                            "User-Agent": USER_AGENT,
                            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                        },
                        timeout=12,
                        attempts=2,
                    )
                except requests.HTTPError as exc:
                    status = exc.response.status_code if exc.response is not None else 0
                    if status in {404, 410}:
                        continue
                    raise

                parsed = parse_fred_bls_release_calendar_html(
                    str(response.text or ""),
                    source_url=url,
                    expected_event_type=event_type,
                    expected_title=title,
                    received_at=current,
                )
                if not parsed:
                    if year > current_year:
                        continue
                    raise ValueError(f"FRED release calendar produced no {event_type} rows for {year}")

                for event in parsed:
                    if event.scheduled_at < min_scheduled_at or event.scheduled_at > max_scheduled_at:
                        continue
                    if event.event_id in seen_ids:
                        continue
                    seen_ids.add(event.event_id)
                    events.append(event)

        events.sort(key=lambda event: (event.scheduled_at, event.event_type, event.title))
        return events[: max(1, min(1000, int(max_events)))]

    def fetch(
        self,
        *,
        now: float | None = None,
        lookback_seconds: float = DEFAULT_LOOKBACK_SECONDS,
        horizon_seconds: float = DEFAULT_HORIZON_SECONDS,
        max_events: int = DEFAULT_MAX_EVENTS,
    ) -> list[IntelligenceEvent]:
        current = float(now if now is not None else time.time())
        min_scheduled_at = current - max(0.0, float(lookback_seconds))
        max_scheduled_at = current + max(0.0, float(horizon_seconds))

        try:
            return self.primary.fetch(
                now=current,
                lookback_seconds=lookback_seconds,
                horizon_seconds=horizon_seconds,
                max_events=max_events,
            )
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status not in {403, 404, 410}:
                raise

        return self._fetch_fred_secondary(
            current=current,
            min_scheduled_at=min_scheduled_at,
            max_scheduled_at=max_scheduled_at,
            max_events=max_events,
        )
