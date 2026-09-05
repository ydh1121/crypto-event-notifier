from __future__ import annotations

import re
import time
from calendar import monthrange
from html.parser import HTMLParser

from .http_retry import get_with_retry
from .intelligence_event import IntelligenceEvent, normalize_intelligence_event
from .intelligence_source_registry import MACRO_CALENDAR

SOURCE_ID = "us_fed_fomc_calendar"
SOURCE_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
USER_AGENT = "crypto-paper-phase5-intelligence/1.0"
MAX_HTML_BYTES = 3_000_000
DEFAULT_MAX_EVENTS = 32

_MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Sept": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}
_MONTH_TOKEN_RE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December|Jan/Feb|Apr/May|Oct/Nov)$"
)
_DAY_TOKEN_RE = re.compile(r"^(\d{1,2})(?:-(\d{1,2}))?(\*)?$", flags=re.IGNORECASE)
_SECTION_RE = re.compile(r"^(20\d{2})\s+FOMC\s+Meetings$", flags=re.IGNORECASE)


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []

    def handle_data(self, data: str) -> None:
        value = re.sub(r"\s+", " ", str(data or "")).strip()
        if value:
            self.tokens.append(value)


def _month_pair(token: str) -> tuple[int, int] | None:
    if "/" in token:
        first, second = token.split("/", 1)
        start = _MONTHS.get(first)
        end = _MONTHS.get(second)
    else:
        start = end = _MONTHS.get(token)
    if not start or not end:
        return None
    return int(start), int(end)


def _iso_date(year: int, month: int, day: int) -> str:
    if day < 1 or day > monthrange(year, month)[1]:
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_fomc_meeting_calendar(
    html: str,
    *,
    min_year: int = 0,
    max_year: int = 0,
    max_events: int = DEFAULT_MAX_EVENTS,
    received_at: float | None = None,
) -> list[IntelligenceEvent]:
    payload = str(html or "")
    if len(payload.encode("utf-8", errors="ignore")) > MAX_HTML_BYTES:
        raise ValueError("FOMC calendar payload exceeds bounded size")
    parser = _VisibleTextParser()
    parser.feed(payload)
    tokens = parser.tokens
    received = float(received_at if received_at is not None else time.time())
    limit = max(1, min(128, int(max_events)))
    output: list[IntelligenceEvent] = []

    index = 0
    while index < len(tokens):
        section = _SECTION_RE.fullmatch(tokens[index])
        if not section:
            index += 1
            continue
        year = int(section.group(1))
        section_end = index + 1
        while section_end < len(tokens) and not _SECTION_RE.fullmatch(tokens[section_end]):
            section_end += 1
        if (min_year and year < int(min_year)) or (max_year and year > int(max_year)):
            index = section_end
            continue

        cursor = index + 1
        while cursor < section_end and len(output) < limit:
            month_token = tokens[cursor]
            if not _MONTH_TOKEN_RE.fullmatch(month_token):
                cursor += 1
                continue
            months = _month_pair(month_token)
            if months is None:
                cursor += 1
                continue
            day_token = ""
            day_index = -1
            for candidate_index in range(cursor + 1, min(section_end, cursor + 5)):
                candidate = tokens[candidate_index]
                if "notation vote" in candidate.casefold():
                    break
                if _DAY_TOKEN_RE.fullmatch(candidate):
                    day_token = candidate
                    day_index = candidate_index
                    break
                if _MONTH_TOKEN_RE.fullmatch(candidate) or _SECTION_RE.fullmatch(candidate):
                    break
            if day_index < 0:
                cursor += 1
                continue

            day_match = _DAY_TOKEN_RE.fullmatch(day_token)
            if day_match is None:
                cursor = day_index + 1
                continue
            start_day = int(day_match.group(1))
            end_day = int(day_match.group(2) or start_day)
            projection_meeting = bool(day_match.group(3))
            start_month, end_month = months
            start_date = _iso_date(year, start_month, start_day)
            end_year = year
            if end_month < start_month:
                end_year += 1
            end_date = _iso_date(end_year, end_month, end_day)
            if not start_date or not end_date:
                cursor = day_index + 1
                continue

            date_label = start_date if start_date == end_date else f"{start_date}~{end_date}"
            output.append(
                normalize_intelligence_event(
                    source_id=SOURCE_ID,
                    source_family=MACRO_CALENDAR,
                    event_type="FOMC_MEETING",
                    title=f"FOMC meeting {date_label}",
                    source_url=SOURCE_URL,
                    external_id=f"fomc-meeting-{start_date}-{end_date}",
                    received_at=received,
                    entities=("US", "FED"),
                    market_scope=("GLOBAL", "US_EQUITY", "CRYPTO"),
                    attributes={
                        "scheduled_date_start": start_date,
                        "scheduled_date_end": end_date,
                        "date_only": True,
                        "projection_meeting": projection_meeting,
                        "exact_release_time_known": False,
                    },
                )
            )
            cursor = day_index + 1
        index = section_end
        if len(output) >= limit:
            break
    return output


class FomcMeetingCalendarSource:
    """Official date-only FOMC meeting calendar adapter; not supervisor-wired.

    The Fed calendar establishes meeting dates but this adapter does not invent a
    statement/decision clock time. Exact statement/minutes publication timestamps
    belong to later official release events.
    """

    source_id = SOURCE_ID
    url = SOURCE_URL

    def fetch(
        self,
        *,
        min_year: int = 0,
        max_year: int = 0,
        max_events: int = DEFAULT_MAX_EVENTS,
        received_at: float | None = None,
    ) -> list[IntelligenceEvent]:
        current = float(received_at if received_at is not None else time.time())
        response, _ = get_with_retry(
            self.url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=12,
            attempts=3,
        )
        payload = str(response.text or "")
        if len(payload.encode("utf-8", errors="ignore")) > MAX_HTML_BYTES:
            raise ValueError("FOMC calendar payload exceeds bounded size")
        return parse_fomc_meeting_calendar(
            payload,
            min_year=min_year,
            max_year=max_year,
            max_events=max_events,
            received_at=current,
        )
