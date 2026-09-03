from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .http_retry import get_with_retry
from .intelligence_event import IntelligenceEvent, normalize_intelligence_event
from .intelligence_source_registry import MACRO_CALENDAR

SOURCE_ID = "us_bls_release_calendar"
SOURCE_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
USER_AGENT = "crypto-paper-phase5-intelligence/1.0"
BLS_TIMEZONE = ZoneInfo("America/New_York")
MAX_ICS_BYTES = 2_000_000
DEFAULT_LOOKBACK_SECONDS = 7 * 86400
DEFAULT_HORIZON_SECONDS = 400 * 86400
DEFAULT_MAX_EVENTS = 256

_EVENT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("consumer price index", "US_CPI"),
    ("employment situation", "US_EMPLOYMENT"),
    ("employment cost index", "US_ECI"),
    ("producer price index", "US_PPI"),
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
            },
        )
        output.append(event)
        if len(output) >= limit:
            break

    return output


class BlsReleaseCalendarSource:
    """Bounded official BLS calendar adapter.

    This adapter is not wired to a supervisor in this build. Calling fetch() is
    an explicit network action and does not imply score/PAPER authority.
    """

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
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/calendar,text/plain;q=0.9,*/*;q=0.1",
            },
            timeout=12,
            attempts=3,
        )
        payload = str(response.text or "")
        if len(payload.encode("utf-8", errors="ignore")) > MAX_ICS_BYTES:
            raise ValueError("BLS ICS payload exceeds bounded size")
        return parse_bls_release_calendar(
            payload,
            min_scheduled_at=current - max(0.0, float(lookback_seconds)),
            max_scheduled_at=current + max(0.0, float(horizon_seconds)),
            max_events=max_events,
            received_at=current,
        )
