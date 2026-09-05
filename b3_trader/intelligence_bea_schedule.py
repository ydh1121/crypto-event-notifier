from __future__ import annotations

import re
import time
from datetime import datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from .http_retry import get_with_retry
from .intelligence_event import IntelligenceEvent, normalize_intelligence_event
from .intelligence_source_registry import MACRO_CALENDAR

SOURCE_ID = "us_bea_release_schedule"
SOURCE_URL = "https://www.bea.gov/news/schedule"
USER_AGENT = "crypto-paper-phase5-intelligence/1.0"
BEA_TIMEZONE = ZoneInfo("America/New_York")
MAX_HTML_BYTES = 2_000_000
DEFAULT_LOOKBACK_SECONDS = 7 * 86400
DEFAULT_HORIZON_SECONDS = 400 * 86400
DEFAULT_MAX_EVENTS = 256


class _ScheduleTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._all_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name == "tr":
            self._row = []
        elif name in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if data:
            self._all_text.append(data)
            if self._cell is not None:
                self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", " ".join(self._cell)).strip())
            self._cell = None
        elif name == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None
            self._cell = None

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._all_text)).strip()


def _event_type(title: str) -> str:
    value = re.sub(r"\s+", " ", str(title or "")).strip().casefold()
    if value.startswith("personal income and outlays"):
        return "US_PCE"
    if value.startswith("gdp (") or value.startswith("gross domestic product"):
        return "US_GDP"
    if value.startswith("u.s. international trade in goods and services"):
        return "US_TRADE"
    return ""


def _parse_scheduled_at(value: str, *, year: int) -> float:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    match = re.fullmatch(
        r"([A-Za-z]+)\s+(\d{1,2})\s+(\d{1,2}:\d{2})\s*([APap][Mm])",
        cleaned,
    )
    if not match:
        return 0.0
    month, day, clock, ampm = match.groups()
    try:
        parsed = datetime.strptime(
            f"{month} {day} {clock} {ampm.upper()} {int(year)}",
            "%B %d %I:%M %p %Y",
        ).replace(tzinfo=BEA_TIMEZONE)
    except ValueError:
        return 0.0
    return parsed.timestamp()


def parse_bea_release_schedule(
    html: str,
    *,
    min_scheduled_at: float = 0.0,
    max_scheduled_at: float = 0.0,
    max_events: int = DEFAULT_MAX_EVENTS,
    received_at: float | None = None,
) -> list[IntelligenceEvent]:
    payload = str(html or "")
    if len(payload.encode("utf-8", errors="ignore")) > MAX_HTML_BYTES:
        raise ValueError("BEA schedule payload exceeds bounded size")
    parser = _ScheduleTableParser()
    parser.feed(payload)
    year_match = re.search(r"\bYear\s+(20\d{2})\b", parser.text, flags=re.IGNORECASE)
    if not year_match:
        return []
    year = int(year_match.group(1))
    received = float(received_at if received_at is not None else time.time())
    limit = max(1, min(1000, int(max_events)))
    output: list[IntelligenceEvent] = []

    for row in parser.rows:
        if len(row) < 3:
            continue
        date_text = row[0]
        release_kind = row[1]
        title = row[-1]
        event_type = _event_type(title)
        if not event_type:
            continue
        scheduled_at = _parse_scheduled_at(date_text, year=year)
        if scheduled_at <= 0:
            continue
        if min_scheduled_at > 0 and scheduled_at < float(min_scheduled_at):
            continue
        if max_scheduled_at > 0 and scheduled_at > float(max_scheduled_at):
            continue
        output.append(
            normalize_intelligence_event(
                source_id=SOURCE_ID,
                source_family=MACRO_CALENDAR,
                event_type=event_type,
                title=title,
                source_url=SOURCE_URL,
                scheduled_at=scheduled_at,
                received_at=received,
                entities=("US",),
                market_scope=("GLOBAL", "CRYPTO"),
                attributes={
                    "release_kind": release_kind,
                    "calendar_year": year,
                    "calendar_timezone": "America/New_York",
                    "time_semantics": "bea_release_schedule_eastern",
                },
            )
        )
        if len(output) >= limit:
            break
    return output


class BeaReleaseScheduleSource:
    """Bounded official BEA release-schedule adapter; not supervisor-wired."""

    source_id = SOURCE_ID
    url = SOURCE_URL

    def fetch(
        self,
        *,
        now: float | None = None,
        lookback_seconds: float = DEFAULT_LOOKBACK_SECONDS,
        horizon_seconds: float = DEFAULT_HORIZON_SECONDS,
        max_events: int = DEFAULT_MAX_EVENTS,
    ) -> list[IntelligenceEvent]:
        current = float(now if now is not None else time.time())
        response, _ = get_with_retry(
            self.url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=12,
            attempts=3,
        )
        payload = str(response.text or "")
        if len(payload.encode("utf-8", errors="ignore")) > MAX_HTML_BYTES:
            raise ValueError("BEA schedule payload exceeds bounded size")
        return parse_bea_release_schedule(
            payload,
            min_scheduled_at=current - max(0.0, float(lookback_seconds)),
            max_scheduled_at=current + max(0.0, float(horizon_seconds)),
            max_events=max_events,
            received_at=current,
        )
