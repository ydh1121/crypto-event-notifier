from __future__ import annotations

import re
import time
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .http_retry import get_with_retry
from .intelligence_event import IntelligenceEvent, normalize_intelligence_event
from .intelligence_source_registry import MACRO_CALENDAR

SOURCE_ID = "us_bls_release_calendar"
SOURCE_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
YEARLY_SCHEDULE_URL = "https://www.bls.gov/schedule/{year}/"
USER_AGENT = "crypto-paper-phase5-intelligence/1.1 (+https://github.com/ydh1121/crypto-event-notifier)"
BLS_TIMEZONE = ZoneInfo("America/New_York")
MAX_ICS_BYTES = 2_000_000
MAX_HTML_BYTES = 2_000_000
DEFAULT_LOOKBACK_SECONDS = 7 * 86400
DEFAULT_HORIZON_SECONDS = 400 * 86400
DEFAULT_MAX_EVENTS = 256

_EVENT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("consumer price index", "US_CPI"),
    ("employment situation", "US_EMPLOYMENT"),
    ("employment cost index", "US_ECI"),
    ("producer price index", "US_PPI"),
)
_MONTH_RE = (
    r"(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
)


def _unfold_ics_lines(text: str) -> list[str]:
    output: list[str] = []
    for raw in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and output:
            output[-1] += raw[1:]
        else:
            output.append(raw)
    return output


def _ics_text(value: str) -> str:
    # RFC 5545 text escaping. Keep this deliberately small and deterministic.
    return (
        str(value or "")
        .replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def _split_property(line: str) -> tuple[str, str, str]:
    if ":" not in line:
        return "", "", ""
    head, value = line.split(":", 1)
    parts = head.split(";", 1)
    name = parts[0].strip().upper()
    params = parts[1].strip() if len(parts) > 1 else ""
    return name, params, value.strip()


def _parse_bls_wall_clock(value: str) -> float:
    """Parse BLS release time using the agency's documented Eastern-time clock.

    BLS states that all times on its release calendar are Eastern Time. Historical
    versions of the ICS have carried inconsistent VALUE/Z metadata, so this
    adapter intentionally treats the displayed HH:MM[:SS] as an Eastern wall
    clock instead of reinterpreting a trailing Z as UTC. Date-only values remain
    unknown rather than inventing a release hour.
    """
    raw = str(value or "").strip()
    match = re.fullmatch(r"(\d{8})T(\d{4}|\d{6})Z?", raw, flags=re.IGNORECASE)
    if not match:
        return 0.0
    date_part, clock_part = match.groups()
    fmt = "%Y%m%d%H%M%S" if len(clock_part) == 6 else "%Y%m%d%H%M"
    try:
        parsed = datetime.strptime(date_part + clock_part, fmt).replace(tzinfo=BLS_TIMEZONE)
    except ValueError:
        return 0.0
    return parsed.timestamp()


def _event_type(summary: str) -> str:
    normalized = re.sub(r"\s+", " ", str(summary or "")).strip().casefold()
    for prefix, event_type in _EVENT_PREFIXES:
        if normalized == prefix or normalized.startswith(prefix + " for "):
            return event_type
    return ""


def _vevents(text: str) -> list[dict[str, tuple[str, str]]]:
    events: list[dict[str, tuple[str, str]]] = []
    current: dict[str, tuple[str, str]] | None = None
    for line in _unfold_ics_lines(text):
        marker = line.strip().upper()
        if marker == "BEGIN:VEVENT":
            current = {}
            continue
        if marker == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None:
            continue
        name, params, value = _split_property(line)
        if name and name not in current:
            current[name] = (params, value)
    return events


class _BlsScheduleHtmlParser(HTMLParser):
    """Extract table rows from the official yearly BLS schedule page."""

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


def _parse_html_release_clock(value: str) -> float:
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
        ).replace(tzinfo=BLS_TIMEZONE)
    except ValueError:
        return 0.0
    return parsed.timestamp()


def parse_bls_release_schedule_html(
    text: str,
    *,
    source_url: str,
    min_scheduled_at: float = 0.0,
    max_scheduled_at: float = 0.0,
    max_events: int = DEFAULT_MAX_EVENTS,
    received_at: float | None = None,
) -> list[IntelligenceEvent]:
    """Parse high-impact releases from an official yearly BLS HTML schedule.

    This is a bounded fallback for environments where the documented ICS
    subscription endpoint returns an access-control response. It keeps the same
    source_id and time semantics while preserving the exact official schedule
    page used for evidence provenance.
    """
    payload = str(text or "")
    if len(payload.encode("utf-8", errors="ignore")) > MAX_HTML_BYTES:
        raise ValueError("BLS HTML payload exceeds bounded size")

    parser = _BlsScheduleHtmlParser()
    parser.feed(payload)
    parser.close()

    limit = max(1, min(1000, int(max_events)))
    received = float(received_at if received_at is not None else time.time())
    output: list[IntelligenceEvent] = []

    for cells in parser.rows:
        title_index = -1
        event_type = ""
        for index, cell in enumerate(cells):
            candidate = _event_type(cell)
            if candidate:
                title_index = index
                event_type = candidate
                break
        if title_index < 0:
            continue

        scheduled_at = _parse_html_release_clock(" ".join(cells[:title_index]))
        if scheduled_at <= 0:
            continue
        if min_scheduled_at > 0 and scheduled_at < float(min_scheduled_at):
            continue
        if max_scheduled_at > 0 and scheduled_at > float(max_scheduled_at):
            continue

        title = re.sub(r"\s+", " ", cells[title_index]).strip()
        external_id = (
            f"{event_type.lower()}-"
            f"{datetime.fromtimestamp(scheduled_at, BLS_TIMEZONE).strftime('%Y%m%dT%H%M')}"
        )
        output.append(
            normalize_intelligence_event(
                source_id=SOURCE_ID,
                source_family=MACRO_CALENDAR,
                event_type=event_type,
                title=title,
                source_url=source_url,
                external_id=external_id,
                scheduled_at=scheduled_at,
                received_at=received,
                entities=("US",),
                market_scope=("GLOBAL", "CRYPTO"),
                attributes={
                    "calendar_timezone": "America/New_York",
                    "time_semantics": "bls_calendar_all_times_eastern",
                    "calendar_source_format": "official_yearly_html_fallback",
                },
            )
        )

    output.sort(key=lambda event: (event.scheduled_at, event.event_type, event.title))
    return output[:limit]


def parse_bls_release_calendar(
    text: str,
    *,
    min_scheduled_at: float = 0.0,
    max_scheduled_at: float = 0.0,
    max_events: int = DEFAULT_MAX_EVENTS,
    received_at: float | None = None,
) -> list[IntelligenceEvent]:
    if len(str(text or "").encode("utf-8", errors="ignore")) > MAX_ICS_BYTES:
        raise ValueError("BLS ICS payload exceeds bounded size")
    limit = max(1, min(1000, int(max_events)))
    received = float(received_at if received_at is not None else time.time())
    output: list[IntelligenceEvent] = []

    for row in _vevents(text):
        summary = _ics_text(row.get("SUMMARY", ("", ""))[1])
        event_type = _event_type(summary)
        if not event_type:
            continue
        if _ics_text(row.get("STATUS", ("", ""))[1]).upper() == "CANCELLED":
            continue
        scheduled_at = _parse_bls_wall_clock(row.get("DTSTART", ("", ""))[1])
        if scheduled_at <= 0:
            continue
        if min_scheduled_at > 0 and scheduled_at < float(min_scheduled_at):
            continue
        if max_scheduled_at > 0 and scheduled_at > float(max_scheduled_at):
            continue

        uid = _ics_text(row.get("UID", ("", ""))[1])
        description = _ics_text(row.get("DESCRIPTION", ("", ""))[1])
        location = _ics_text(row.get("LOCATION", ("", ""))[1])
        status = _ics_text(row.get("STATUS", ("", ""))[1]).upper()
        event = normalize_intelligence_event(
            source_id=SOURCE_ID,
            source_family=MACRO_CALENDAR,
            event_type=event_type,
            title=summary,
            source_url=SOURCE_URL,
            external_id=uid,
            scheduled_at=scheduled_at,
            received_at=received,
            entities=("US",),
            market_scope=("GLOBAL", "CRYPTO"),
            raw_text=description,
            attributes={
                "calendar_uid": uid,
                "location": location,
                "status": status,
                "calendar_timezone": "America/New_York",
                "time_semantics": "bls_calendar_all_times_eastern",
                "calendar_source_format": "ics",
            },
        )
        output.append(event)
        if len(output) >= limit:
            break

    return output


def _window_years(min_scheduled_at: float, max_scheduled_at: float, current: float) -> list[int]:
    lower = float(min_scheduled_at or current)
    upper = float(max_scheduled_at or current)
    if upper < lower:
        lower, upper = upper, lower
    first = datetime.fromtimestamp(lower, BLS_TIMEZONE).year
    last = datetime.fromtimestamp(upper, BLS_TIMEZONE).year
    # A normal Phase 5 window spans at most two calendar years. Keep a hard
    # three-year cap so malformed caller input cannot fan out network requests.
    return list(range(first, min(last, first + 2) + 1))


class BlsReleaseCalendarSource:
    """Bounded official BLS calendar adapter.

    Fetching is an explicit network action and does not imply score/PAPER
    authority. The documented ICS endpoint remains primary. A bounded official
    BLS yearly-HTML fallback is used only when the ICS endpoint returns an
    access-control/not-found response.
    """

    source_id = SOURCE_ID
    url = SOURCE_URL

    def _fetch_yearly_html_fallback(
        self,
        *,
        current: float,
        min_scheduled_at: float,
        max_scheduled_at: float,
        max_events: int,
    ) -> list[IntelligenceEvent]:
        events: list[IntelligenceEvent] = []
        seen_ids: set[str] = set()

        for year in _window_years(min_scheduled_at, max_scheduled_at, current):
            url = YEARLY_SCHEDULE_URL.format(year=year)
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
                # Future-year pages may not have been published yet. That is not
                # a source failure when the current-year official page succeeded.
                if status in {404, 410}:
                    continue
                raise

            payload = str(response.text or "")
            parsed = parse_bls_release_schedule_html(
                payload,
                source_url=url,
                min_scheduled_at=min_scheduled_at,
                max_scheduled_at=max_scheduled_at,
                max_events=max_events,
                received_at=current,
            )
            for event in parsed:
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
            response, _ = get_with_retry(
                self.url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/calendar,text/plain;q=0.9,*/*;q=0.1",
                },
                timeout=12,
                attempts=3,
            )
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status not in {403, 404, 410}:
                raise
            return self._fetch_yearly_html_fallback(
                current=current,
                min_scheduled_at=min_scheduled_at,
                max_scheduled_at=max_scheduled_at,
                max_events=max_events,
            )

        payload = str(response.text or "")
        if len(payload.encode("utf-8", errors="ignore")) > MAX_ICS_BYTES:
            raise ValueError("BLS ICS payload exceeds bounded size")
        return parse_bls_release_calendar(
            payload,
            min_scheduled_at=min_scheduled_at,
            max_scheduled_at=max_scheduled_at,
            max_events=max_events,
            received_at=current,
        )
