from __future__ import annotations

import math
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Iterable

import requests

from .intelligence_macro_release_values import (
    MacroReleaseValue,
    MacroReleaseValueStore,
    normalize_macro_release_value,
)

TE_API_ROOT = "https://api.tradingeconomics.com"
TE_CALENDAR_URL = f"{TE_API_ROOT}/calendar"
TE_PROVIDER_ID = "trading_economics_calendar_consensus"
TE_AUTHORITY = "Trading Economics"
TE_DATA_RIGHTS = "subscription_api_internal_research_only_unless_license_allows_distribution"
DEFAULT_CAPTURE_LEAD_SECONDS = 45 * 60
DEFAULT_MAX_EVENTS = 6
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_ATTEMPTS = 2
RELEASE_MATCH_TOLERANCE_SECONDS = 5 * 60
SUPPORTED_EVENT_TYPES = {"US_CPI", "US_EMPLOYMENT", "US_PCE"}

EXPECTED_METRICS: dict[str, tuple[str, ...]] = {
    "US_CPI": (
        "US_CPI_ALL_ITEMS_MOM_PCT",
        "US_CPI_ALL_ITEMS_YOY_PCT",
    ),
    "US_EMPLOYMENT": (
        "US_NONFARM_PAYROLL_CHANGE_K",
        "US_UNEMPLOYMENT_RATE_PCT",
    ),
    "US_PCE": (
        "US_PCE_PRICE_MOM_PCT",
        "US_CORE_PCE_PRICE_MOM_PCT",
        "US_PCE_PRICE_YOY_PCT",
        "US_CORE_PCE_PRICE_YOY_PCT",
    ),
}

_LABEL_TO_METRIC = {
    "inflation rate mom": "US_CPI_ALL_ITEMS_MOM_PCT",
    "inflation rate yoy": "US_CPI_ALL_ITEMS_YOY_PCT",
    "inflation rate": "US_CPI_ALL_ITEMS_YOY_PCT",
    "non farm payrolls": "US_NONFARM_PAYROLL_CHANGE_K",
    "nonfarm payrolls": "US_NONFARM_PAYROLL_CHANGE_K",
    "unemployment rate": "US_UNEMPLOYMENT_RATE_PCT",
    "pce price index mom": "US_PCE_PRICE_MOM_PCT",
    "pce price index monthly change": "US_PCE_PRICE_MOM_PCT",
    "pce price index yoy": "US_PCE_PRICE_YOY_PCT",
    "pce price index annual change": "US_PCE_PRICE_YOY_PCT",
    "core pce price index mom": "US_CORE_PCE_PRICE_MOM_PCT",
    "core pce price index monthly change": "US_CORE_PCE_PRICE_MOM_PCT",
    "core pce price index yoy": "US_CORE_PCE_PRICE_YOY_PCT",
    "core pce price index annual change": "US_CORE_PCE_PRICE_YOY_PCT",
}


def _clean_label(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    return re.sub(r"\s+", " ", text)


def _metric_id(row: dict[str, Any]) -> str:
    event_label = _clean_label(row.get("Event"))
    if event_label in _LABEL_TO_METRIC:
        return _LABEL_TO_METRIC[event_label]
    category_label = _clean_label(row.get("Category"))
    return _LABEL_TO_METRIC.get(category_label, "")


def _parse_utc_timestamp(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).timestamp()


def _reference_period(row: dict[str, Any]) -> str:
    stamp = _parse_utc_timestamp(row.get("ReferenceDate"))
    if stamp <= 0:
        return ""
    parsed = datetime.fromtimestamp(stamp, tz=timezone.utc)
    return f"{parsed.year:04d}-{parsed.month:02d}"


def _finite(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_forecast_string(value: object) -> tuple[float, str] | None:
    text = str(value or "").strip().upper().replace(",", "")
    if not text or text in {"NULL", "NONE", "N/A", "NA", "-", "--"}:
        return None
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([KMB%]?)", text)
    if not match:
        return None
    number = float(match.group(1))
    suffix = match.group(2)
    if suffix == "M":
        return number * 1000.0, "THOUSANDS"
    if suffix == "B":
        return number * 1_000_000.0, "THOUSANDS"
    if suffix == "K":
        return number, "THOUSANDS"
    if suffix == "%":
        return number, "PERCENT"
    return number, ""


def _forecast_value(row: dict[str, Any], metric_id: str) -> tuple[float, str] | None:
    parsed_text = _parse_forecast_string(row.get("Forecast"))
    if metric_id == "US_NONFARM_PAYROLL_CHANGE_K":
        if parsed_text is None:
            return None
        number, suffix_unit = parsed_text
        unit_label = _clean_label(row.get("Unit"))
        if suffix_unit == "THOUSANDS" or unit_label in {"k", "thousand", "thousands"}:
            return number, "THOUSANDS"
        return None

    if parsed_text is not None:
        number, suffix_unit = parsed_text
        if suffix_unit in {"", "PERCENT"}:
            return number, "PERCENT"

    numeric = _finite(row.get("ForecastValue"))
    if numeric is None:
        return None
    unit_label = _clean_label(row.get("Unit"))
    if unit_label in {"percent", "percentage", "pct"} or str(row.get("Unit") or "").strip() == "%":
        return numeric, "PERCENT"
    return None


class TradingEconomicsCalendarClient:
    """Bounded Trading Economics economic-calendar client using header auth only."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        session: Any | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        attempts: int = DEFAULT_ATTEMPTS,
    ) -> None:
        configured = api_key if api_key is not None else os.getenv("TRADING_ECONOMICS_API_KEY", "")
        self.api_key = str(configured or "").strip()
        self.session = session or requests.Session()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.attempts = max(1, min(3, int(attempts)))

    @property
    def credential_status(self) -> str:
        return "ready" if self.api_key else "missing"

    def fetch_us_calendar(self, *, start_at: float, end_at: float) -> list[dict[str, Any]]:
        if self.credential_status != "ready":
            raise ValueError("Trading Economics API credential is missing")
        start = datetime.fromtimestamp(float(start_at), tz=timezone.utc).date()
        end = datetime.fromtimestamp(float(end_at), tz=timezone.utc).date()
        if end < start or (end - start).days > 2:
            raise ValueError("bounded Trading Economics request supports at most 3 calendar days")
        url = f"{TE_CALENDAR_URL}/country/united%20states/{start.isoformat()}/{end.isoformat()}"
        response = None
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = self.session.get(
                    url,
                    params={"values": "true", "f": "json"},
                    headers={
                        "Authorization": self.api_key,
                        "User-Agent": "crypto-event-notifier-phase5/1.0",
                        "Accept": "application/json",
                    },
                    timeout=self.timeout_seconds,
                )
                status_code = int(getattr(response, "status_code", 200))
                if status_code in {409, 429, 500, 502, 503, 504}:
                    last_error = RuntimeError(f"Trading Economics API transient HTTP {status_code}")
                    if attempt + 1 < self.attempts:
                        time.sleep(0.25 * (attempt + 1))
                        continue
                response.raise_for_status()
                break
            except (requests.ConnectionError, requests.Timeout, RuntimeError) as exc:
                last_error = exc
                if attempt + 1 >= self.attempts:
                    raise
                time.sleep(0.25 * (attempt + 1))
        else:
            if last_error is not None:
                raise last_error
            raise RuntimeError("Trading Economics API request failed")

        if response is None:
            raise RuntimeError("Trading Economics API returned no response")
        body = response.json()
        if not isinstance(body, list):
            raise ValueError("Trading Economics calendar response must be a JSON array")
        return [dict(row) for row in body if isinstance(row, dict)]


def build_trading_economics_consensus_values(
    *,
    event_id: str,
    event_type: str,
    scheduled_at: float,
    rows: Iterable[dict[str, Any]],
    known_at: float,
) -> list[MacroReleaseValue]:
    clean_type = str(event_type or "").strip().upper()
    expected = EXPECTED_METRICS.get(clean_type)
    if expected is None:
        raise ValueError(f"unsupported consensus event type: {event_type!r}")
    if not (0 < float(known_at) < float(scheduled_at)):
        raise ValueError("consensus known_at must be strictly before scheduled release")

    selected: dict[str, tuple[dict[str, Any], float, str, str]] = {}
    for raw in rows:
        row = dict(raw)
        if str(row.get("Country") or "").strip().casefold() != "united states":
            continue
        if str(row.get("DateSpan") or "0").strip() != "0":
            continue
        metric_id = _metric_id(row)
        if metric_id not in expected:
            continue
        release_at = _parse_utc_timestamp(row.get("Date"))
        if release_at <= 0 or abs(release_at - float(scheduled_at)) > RELEASE_MATCH_TOLERANCE_SECONDS:
            continue
        reference_period = _reference_period(row)
        if not reference_period:
            continue
        parsed_forecast = _forecast_value(row, metric_id)
        if parsed_forecast is None:
            continue
        numeric_value, unit = parsed_forecast
        previous = selected.get(metric_id)
        if previous is not None:
            _, old_value, old_unit, old_period = previous
            if old_unit != unit or old_period != reference_period or abs(old_value - numeric_value) > 1e-12:
                raise ValueError(f"conflicting Trading Economics consensus rows for {metric_id}")
            continue
        selected[metric_id] = (row, numeric_value, unit, reference_period)

    missing = [metric_id for metric_id in expected if metric_id not in selected]
    if missing:
        raise ValueError(f"incomplete Trading Economics consensus metric set: {missing}")
    periods = {selected[metric_id][3] for metric_id in expected}
    if len(periods) != 1:
        raise ValueError("Trading Economics consensus metrics disagree on reference period")

    output: list[MacroReleaseValue] = []
    for metric_id in expected:
        row, numeric_value, unit, reference_period = selected[metric_id]
        output.append(
            normalize_macro_release_value(
                event_id=event_id,
                event_type=clean_type,
                metric_id=metric_id,
                value_role="consensus",
                numeric_value=numeric_value,
                unit=unit,
                reference_period=reference_period,
                provider_id=TE_PROVIDER_ID,
                provider_url=TE_CALENDAR_URL,
                authority=TE_AUTHORITY,
                data_rights=TE_DATA_RIGHTS,
                known_at=known_at,
                received_at=known_at,
                revision_no=0,
                revision_label="pre_release_snapshot",
                attributes={
                    "calendar_id": str(row.get("CalendarId") or row.get("CalendarID") or ""),
                    "ticker": str(row.get("Ticker") or ""),
                    "symbol": str(row.get("Symbol") or ""),
                    "event": str(row.get("Event") or ""),
                    "category": str(row.get("Category") or ""),
                    "source": str(row.get("Source") or ""),
                    "source_url": str(row.get("SourceURL") or ""),
                    "last_update": str(row.get("LastUpdate") or ""),
                    "date_span": str(row.get("DateSpan") or ""),
                    "consensus_definition": "average_forecast_among_representative_group_of_economists",
                    "capture_policy": "single_complete_snapshot_within_45m_pre_release_window",
                    "point_in_time_backfill_used": False,
                    "credential_exposed": False,
                    "score_authority": False,
                },
            )
        )
    return output


class TradingEconomicsConsensusCaptureService:
    """Capture one complete pre-release consensus snapshot per supported macro event."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        client: TradingEconomicsCalendarClient | None = None,
        capture_lead_seconds: float = DEFAULT_CAPTURE_LEAD_SECONDS,
        max_events: int = DEFAULT_MAX_EVENTS,
    ) -> None:
        self.conn = conn
        self.client = client or TradingEconomicsCalendarClient()
        self.capture_lead_seconds = max(5 * 60.0, min(2 * 60 * 60.0, float(capture_lead_seconds)))
        self.max_events = max(1, min(12, int(max_events)))
        self.store = MacroReleaseValueStore(conn)

    def _existing_metrics(self, event_id: str) -> set[str]:
        rows = self.conn.execute(
            """SELECT metric_id FROM research_intelligence_macro_values
               WHERE event_id=? AND value_role='consensus' AND provider_id=?
                 AND revision_no=0""",
            (event_id, TE_PROVIDER_ID),
        ).fetchall()
        return {str(row["metric_id"]) for row in rows}

    def _due_events(self, now: float) -> list[sqlite3.Row]:
        tables = {
            str(row[0])
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "research_intelligence_events" not in tables:
            return []
        return self.conn.execute(
            """SELECT event_id,event_type,title,scheduled_at,source_id
               FROM research_intelligence_events
               WHERE source_id IN ('us_bls_release_calendar','us_bea_release_schedule')
                 AND event_type IN ('US_CPI','US_EMPLOYMENT','US_PCE')
                 AND scheduled_at>? AND scheduled_at<=?
               ORDER BY scheduled_at,event_id
               LIMIT ?""",
            (now, now + self.capture_lead_seconds, self.max_events),
        ).fetchall()

    def run_once(self, *, now: float | None = None, network_enabled: bool = False) -> dict[str, Any]:
        current = float(now if now is not None else time.time())
        result: dict[str, Any] = {
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "network_enabled": bool(network_enabled),
            "credential_status": self.client.credential_status,
            "credential_exposed": False,
            "events_considered": 0,
            "events_captured": 0,
            "consensus_values_inserted": 0,
            "already_captured": 0,
            "partial_existing_fail_closed": 0,
            "incomplete_consensus": 0,
            "capture_failures": 0,
            "network_requests": 0,
        }
        if not network_enabled:
            result["status"] = "network_disabled"
            return result
        if self.client.credential_status != "ready":
            result["status"] = "credential_missing"
            return result

        due = self._due_events(current)
        result["events_considered"] = len(due)
        active: list[sqlite3.Row] = []
        for row in due:
            event_type = str(row["event_type"]).upper()
            expected = set(EXPECTED_METRICS[event_type])
            existing = self._existing_metrics(str(row["event_id"]))
            if expected.issubset(existing):
                result["already_captured"] += 1
                continue
            if existing:
                result["partial_existing_fail_closed"] += 1
                continue
            active.append(row)

        if not active:
            result["status"] = "idle"
            return result

        start_at = min(float(row["scheduled_at"]) for row in active)
        end_at = max(float(row["scheduled_at"]) for row in active)
        try:
            result["network_requests"] = 1
            calendar_rows = self.client.fetch_us_calendar(start_at=start_at, end_at=end_at)
        except Exception as exc:
            result["capture_failures"] = 1
            result["status"] = "partial"
            result["errors"] = [{"error": f"{type(exc).__name__}: {exc}"[:300]}]
            return result

        for row in active:
            event_id = str(row["event_id"])
            event_type = str(row["event_type"]).upper()
            try:
                values = build_trading_economics_consensus_values(
                    event_id=event_id,
                    event_type=event_type,
                    scheduled_at=float(row["scheduled_at"]),
                    rows=calendar_rows,
                    known_at=current,
                )
            except ValueError as exc:
                result["incomplete_consensus"] += 1
                result.setdefault("incomplete", []).append(
                    {"event_id": event_id, "reason": str(exc)[:240]}
                )
                continue
            ingest = self.store.ingest(values, seen_at=current)
            result["events_captured"] += 1
            result["consensus_values_inserted"] += int(ingest["inserted"])

        result["status"] = "ok"
        return result
