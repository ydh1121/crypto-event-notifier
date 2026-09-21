from __future__ import annotations

import calendar
import json
import sqlite3
from dataclasses import replace
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .intelligence_bls_actual import (
    CPI_NSA_ALL_ITEMS,
    CPI_SA_ALL_ITEMS,
    TOTAL_NONFARM_EMPLOYMENT,
    UNEMPLOYMENT_RATE,
    BlsActualCaptureService as BaseBlsActualCaptureService,
    BlsReferencePeriod,
    MacroReleaseValue,
    build_bls_actual_values,
    parse_bls_reference_period,
)

FRED_FALLBACK_FORMAT = "official_fred_secondary_calendar_fallback"
FRED_HOST = "fred.stlouisfed.org"
BLS_SCHEDULE_TIMEZONE = ZoneInfo("America/New_York")
_GENERIC_FRED_TITLES = {
    "US_CPI": "Consumer Price Index",
    "US_EMPLOYMENT": "Employment Situation",
}


def _previous_calendar_month(timestamp: float) -> BlsReferencePeriod:
    release = datetime.fromtimestamp(float(timestamp), BLS_SCHEDULE_TIMEZONE)
    if release.month == 1:
        return BlsReferencePeriod(year=release.year - 1, month=12)
    return BlsReferencePeriod(year=release.year, month=release.month - 1)


def _decode_attributes(raw: object) -> dict[str, object]:
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def resolve_bls_reference_period(row: sqlite3.Row) -> tuple[BlsReferencePeriod, str]:
    """Resolve a BLS monthly reference period without fabricating source text.

    Native BLS calendar titles contain e.g. ``for August 2026`` and remain the
    primary path. The official FRED release-calendar fallback exposes only the
    generic release name, so for that exact provenance we infer the reference
    month as the previous calendar month. This fallback is intentionally bounded
    to CPI and Employment Situation and is recorded on captured value attributes.
    """

    title = str(row["title"] or "").strip()
    parsed = parse_bls_reference_period(title)
    if parsed is not None:
        return parsed, "event_title"

    event_type = str(row["event_type"] or "").strip().upper()
    expected_title = _GENERIC_FRED_TITLES.get(event_type)
    if not expected_title or title.casefold() != expected_title.casefold():
        raise ValueError("cannot derive BLS reference month from stored event title")

    attributes = _decode_attributes(row["attributes_json"])
    source_format = str(attributes.get("calendar_source_format") or "").strip()
    source_url = str(row["source_url"] or "").strip()
    host = (urlparse(source_url).hostname or "").lower()
    if source_format != FRED_FALLBACK_FORMAT or host != FRED_HOST:
        raise ValueError("generic BLS title lacks verified FRED fallback provenance")

    scheduled_at = float(row["scheduled_at"] or 0.0)
    if scheduled_at <= 0:
        raise ValueError("generic FRED BLS event is missing scheduled_at")

    return _previous_calendar_month(scheduled_at), "fred_calendar_previous_month_inference"


class BlsActualCaptureService(BaseBlsActualCaptureService):
    """BLS actual capture with fail-closed FRED-calendar reference resolution."""

    def _due_events(self, now: float) -> list[sqlite3.Row]:
        tables = {
            str(row[0])
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "research_intelligence_events" not in tables:
            return []
        return self.conn.execute(
            """SELECT event_id,event_type,title,source_url,attributes_json,scheduled_at
               FROM research_intelligence_events
               WHERE source_id='us_bls_release_calendar'
                 AND event_type IN ('US_CPI','US_EMPLOYMENT')
                 AND scheduled_at>0 AND scheduled_at<=?
               ORDER BY scheduled_at DESC,event_id
               LIMIT ?""",
            (now, self.max_events),
        ).fetchall()

    def _fetch_event_values(self, row: sqlite3.Row, *, now: float) -> list[MacroReleaseValue]:
        reference, reference_source = resolve_bls_reference_period(row)
        event_type = str(row["event_type"] or "").strip().upper()

        if event_type == "US_CPI":
            series_ids = [CPI_SA_ALL_ITEMS, CPI_NSA_ALL_ITEMS]
        elif event_type == "US_EMPLOYMENT":
            series_ids = [TOTAL_NONFARM_EMPLOYMENT, UNEMPLOYMENT_RATE]
        else:
            raise ValueError(f"unsupported BLS event type: {event_type}")

        data = self.client.fetch_series(
            series_ids,
            start_year=reference.year - 1,
            end_year=reference.year,
        )

        source_title = str(row["title"] or "").strip()
        builder_title = source_title
        if parse_bls_reference_period(builder_title) is None:
            builder_title = (
                f"{source_title} for {calendar.month_name[reference.month]} {reference.year}"
            )

        values = build_bls_actual_values(
            event_id=str(row["event_id"]),
            event_type=event_type,
            title=builder_title,
            known_at=now,
            data=data,
        )

        if reference_source == "event_title":
            return values

        source_url = str(row["source_url"] or "").strip()
        return [
            replace(
                value,
                attributes={
                    **value.attributes,
                    "reference_period_source": reference_source,
                    "reference_period_inference": "previous_calendar_month_from_release_schedule",
                    "schedule_source_format": FRED_FALLBACK_FORMAT,
                    "schedule_source_url": source_url,
                    "source_title_preserved": source_title,
                },
            )
            for value in values
        ]
