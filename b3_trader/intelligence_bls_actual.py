from __future__ import annotations

import calendar
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Iterable

import requests

from .intelligence_macro_release_values import (
    MacroReleaseValue,
    MacroReleaseValueStore,
    normalize_macro_release_value,
)

BLS_PUBLIC_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_PROVIDER_ID = "bls_public_data_api"
BLS_AUTHORITY = "U.S. Bureau of Labor Statistics"
BLS_DATA_RIGHTS = "official_us_government_public_api"
DEFAULT_CAPTURE_WINDOW_SECONDS = 6 * 60 * 60
DEFAULT_MAX_EVENTS = 4
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_ATTEMPTS = 2

CPI_SA_ALL_ITEMS = "CUSR0000SA0"
CPI_NSA_ALL_ITEMS = "CUUR0000SA0"
TOTAL_NONFARM_EMPLOYMENT = "CES0000000001"
UNEMPLOYMENT_RATE = "LNS14000000"

SUPPORTED_EVENT_TYPES = {"US_CPI", "US_EMPLOYMENT"}
_MONTHS = {name.casefold(): index for index, name in enumerate(calendar.month_name) if name}
_REFERENCE_RE = re.compile(r"\bfor\s+([A-Za-z]+)\s+(\d{4})\b", re.IGNORECASE)


@dataclass(frozen=True)
class BlsReferencePeriod:
    year: int
    month: int

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def parse_bls_reference_period(title: str) -> BlsReferencePeriod | None:
    match = _REFERENCE_RE.search(str(title or ""))
    if not match:
        return None
    month = _MONTHS.get(match.group(1).casefold())
    year = int(match.group(2))
    if month is None or not 1 <= month <= 12 or year < 1900:
        return None
    return BlsReferencePeriod(year=year, month=month)


def _shift_month(period: BlsReferencePeriod, delta: int) -> BlsReferencePeriod:
    absolute = period.year * 12 + (period.month - 1) + int(delta)
    year, month0 = divmod(absolute, 12)
    return BlsReferencePeriod(year=year, month=month0 + 1)


class BlsPublicDataClient:
    """Minimal official BLS API client for bounded Phase 5 release capture."""

    def __init__(
        self,
        *,
        session: Any | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        attempts: int = DEFAULT_ATTEMPTS,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.attempts = max(1, min(3, int(attempts)))

    def fetch_series(
        self,
        series_ids: Iterable[str],
        *,
        start_year: int,
        end_year: int,
    ) -> dict[str, dict[tuple[int, int], float]]:
        clean_series = list(
            dict.fromkeys(
                str(value or "").strip().upper()
                for value in series_ids
                if str(value or "").strip()
            )
        )
        if not clean_series:
            raise ValueError("at least one BLS series id is required")
        if len(clean_series) > 8:
            raise ValueError("bounded BLS request supports at most 8 series")
        if int(end_year) < int(start_year) or int(end_year) - int(start_year) > 2:
            raise ValueError("bounded BLS request supports at most 3 calendar years")

        payload = {
            "seriesid": clean_series,
            "startyear": str(int(start_year)),
            "endyear": str(int(end_year)),
        }
        response = None
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = self.session.post(
                    BLS_PUBLIC_API_URL,
                    json=payload,
                    timeout=self.timeout_seconds,
                    headers={"User-Agent": "crypto-event-notifier-phase5/1.0"},
                )
                status_code = int(getattr(response, "status_code", 200))
                if status_code in {429, 500, 502, 503, 504}:
                    last_error = RuntimeError(f"BLS API transient HTTP {status_code}")
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
            raise RuntimeError("BLS API request failed")

        if response is None:
            raise RuntimeError("BLS API request returned no response")
        body = response.json()
        if not isinstance(body, dict) or str(body.get("status") or "") != "REQUEST_SUCCEEDED":
            messages = body.get("message") if isinstance(body, dict) else None
            raise ValueError(f"BLS API request did not succeed: {messages!r}")
        results = body.get("Results")
        series_rows = results.get("series") if isinstance(results, dict) else None
        if not isinstance(series_rows, list):
            raise ValueError("BLS API response is missing Results.series")

        output: dict[str, dict[tuple[int, int], float]] = {}
        for series in series_rows:
            if not isinstance(series, dict):
                continue
            series_id = str(series.get("seriesID") or "").strip().upper()
            if series_id not in clean_series:
                continue
            values: dict[tuple[int, int], float] = {}
            for row in series.get("data") or []:
                if not isinstance(row, dict):
                    continue
                period = str(row.get("period") or "").strip().upper()
                if not re.fullmatch(r"M(0[1-9]|1[0-2])", period):
                    continue
                try:
                    year = int(row.get("year"))
                    month = int(period[1:])
                    value = float(str(row.get("value") or "").replace(",", ""))
                except (TypeError, ValueError):
                    continue
                values[(year, month)] = value
            output[series_id] = values

        missing = [series_id for series_id in clean_series if series_id not in output]
        if missing:
            raise ValueError(f"BLS API response missing requested series: {missing}")
        return output


def _require_value(
    data: dict[str, dict[tuple[int, int], float]],
    series_id: str,
    period: BlsReferencePeriod,
) -> float:
    try:
        return float(data[series_id][(period.year, period.month)])
    except KeyError as exc:
        raise ValueError(f"missing BLS value for {series_id} {period.label}") from exc


def _metric(
    *,
    event_id: str,
    event_type: str,
    metric_id: str,
    numeric_value: float,
    unit: str,
    reference_period: BlsReferencePeriod,
    known_at: float,
    series_ids: list[str],
    formula: str,
    inputs: dict[str, float],
) -> MacroReleaseValue:
    return normalize_macro_release_value(
        event_id=event_id,
        event_type=event_type,
        metric_id=metric_id,
        value_role="actual",
        numeric_value=numeric_value,
        unit=unit,
        reference_period=reference_period.label,
        provider_id=BLS_PROVIDER_ID,
        provider_url=BLS_PUBLIC_API_URL,
        authority=BLS_AUTHORITY,
        data_rights=BLS_DATA_RIGHTS,
        known_at=known_at,
        received_at=known_at,
        revision_no=0,
        revision_label="initial_api_capture",
        attributes={
            "series_ids": series_ids,
            "formula": formula,
            "inputs": inputs,
            "capture_policy": "first_complete_official_api_observation_within_release_window",
            "score_authority": False,
        },
    )


def build_bls_actual_values(
    *,
    event_id: str,
    event_type: str,
    title: str,
    known_at: float,
    data: dict[str, dict[tuple[int, int], float]],
) -> list[MacroReleaseValue]:
    clean_type = str(event_type or "").strip().upper()
    reference = parse_bls_reference_period(title)
    if clean_type not in SUPPORTED_EVENT_TYPES:
        raise ValueError(f"unsupported BLS actual event type: {event_type!r}")
    if reference is None:
        raise ValueError("cannot derive BLS reference month from event title")

    if clean_type == "US_CPI":
        previous = _shift_month(reference, -1)
        prior_year = BlsReferencePeriod(reference.year - 1, reference.month)
        current_sa = _require_value(data, CPI_SA_ALL_ITEMS, reference)
        previous_sa = _require_value(data, CPI_SA_ALL_ITEMS, previous)
        current_nsa = _require_value(data, CPI_NSA_ALL_ITEMS, reference)
        prior_year_nsa = _require_value(data, CPI_NSA_ALL_ITEMS, prior_year)
        if previous_sa <= 0 or prior_year_nsa <= 0:
            raise ValueError("CPI denominator must be positive")
        mom = (current_sa / previous_sa - 1.0) * 100.0
        yoy = (current_nsa / prior_year_nsa - 1.0) * 100.0
        return [
            _metric(
                event_id=event_id,
                event_type=clean_type,
                metric_id="US_CPI_ALL_ITEMS_MOM_PCT",
                numeric_value=mom,
                unit="PERCENT",
                reference_period=reference,
                known_at=known_at,
                series_ids=[CPI_SA_ALL_ITEMS],
                formula="(current_sa_index / previous_month_sa_index - 1) * 100",
                inputs={"current_sa_index": current_sa, "previous_month_sa_index": previous_sa},
            ),
            _metric(
                event_id=event_id,
                event_type=clean_type,
                metric_id="US_CPI_ALL_ITEMS_YOY_PCT",
                numeric_value=yoy,
                unit="PERCENT",
                reference_period=reference,
                known_at=known_at,
                series_ids=[CPI_NSA_ALL_ITEMS],
                formula="(current_nsa_index / prior_year_same_month_nsa_index - 1) * 100",
                inputs={"current_nsa_index": current_nsa, "prior_year_same_month_nsa_index": prior_year_nsa},
            ),
        ]

    previous = _shift_month(reference, -1)
    current_nonfarm = _require_value(data, TOTAL_NONFARM_EMPLOYMENT, reference)
    previous_nonfarm = _require_value(data, TOTAL_NONFARM_EMPLOYMENT, previous)
    unemployment = _require_value(data, UNEMPLOYMENT_RATE, reference)
    return [
        _metric(
            event_id=event_id,
            event_type=clean_type,
            metric_id="US_NONFARM_PAYROLL_CHANGE_K",
            numeric_value=current_nonfarm - previous_nonfarm,
            unit="THOUSANDS",
            reference_period=reference,
            known_at=known_at,
            series_ids=[TOTAL_NONFARM_EMPLOYMENT],
            formula="current_total_nonfarm_k - previous_month_total_nonfarm_k",
            inputs={"current_total_nonfarm_k": current_nonfarm, "previous_month_total_nonfarm_k": previous_nonfarm},
        ),
        _metric(
            event_id=event_id,
            event_type=clean_type,
            metric_id="US_UNEMPLOYMENT_RATE_PCT",
            numeric_value=unemployment,
            unit="PERCENT",
            reference_period=reference,
            known_at=known_at,
            series_ids=[UNEMPLOYMENT_RATE],
            formula="published_seasonally_adjusted_unemployment_rate",
            inputs={"unemployment_rate_pct": unemployment},
        ),
    ]


class BlsActualCaptureService:
    """Capture initial BLS actuals only near the official release boundary.

    Historical backfill outside the bounded window is intentionally rejected:
    the current BLS time-series API can contain later revisions and does not by
    itself prove what value was visible at the original release instant.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        client: BlsPublicDataClient | None = None,
        capture_window_seconds: float = DEFAULT_CAPTURE_WINDOW_SECONDS,
        max_events: int = DEFAULT_MAX_EVENTS,
    ) -> None:
        self.conn = conn
        self.client = client or BlsPublicDataClient()
        self.capture_window_seconds = max(60.0, min(24 * 60 * 60, float(capture_window_seconds)))
        self.max_events = max(1, min(12, int(max_events)))
        self.store = MacroReleaseValueStore(conn)

    @staticmethod
    def _metric_ids(event_type: str) -> tuple[str, ...]:
        if event_type == "US_CPI":
            return ("US_CPI_ALL_ITEMS_MOM_PCT", "US_CPI_ALL_ITEMS_YOY_PCT")
        if event_type == "US_EMPLOYMENT":
            return ("US_NONFARM_PAYROLL_CHANGE_K", "US_UNEMPLOYMENT_RATE_PCT")
        return ()

    def _existing_metrics(self, event_id: str) -> set[str]:
        rows = self.conn.execute(
            """SELECT metric_id FROM research_intelligence_macro_values
               WHERE event_id=? AND value_role='actual' AND provider_id=?
                 AND revision_no=0""",
            (event_id, BLS_PROVIDER_ID),
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
            """SELECT event_id,event_type,title,scheduled_at
               FROM research_intelligence_events
               WHERE source_id='us_bls_release_calendar'
                 AND event_type IN ('US_CPI','US_EMPLOYMENT')
                 AND scheduled_at>0 AND scheduled_at<=?
               ORDER BY scheduled_at DESC,event_id
               LIMIT ?""",
            (now, self.max_events),
        ).fetchall()

    def _fetch_event_values(self, row: sqlite3.Row, *, now: float) -> list[MacroReleaseValue]:
        reference = parse_bls_reference_period(str(row["title"]))
        if reference is None:
            raise ValueError("cannot derive BLS reference month from stored event title")
        event_type = str(row["event_type"]).upper()
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
        return build_bls_actual_values(
            event_id=str(row["event_id"]),
            event_type=event_type,
            title=str(row["title"]),
            known_at=now,
            data=data,
        )

    def run_once(self, *, now: float | None = None, network_enabled: bool = False) -> dict[str, Any]:
        current = float(now if now is not None else time.time())
        result: dict[str, Any] = {
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "network_enabled": bool(network_enabled),
            "events_considered": 0,
            "events_captured": 0,
            "actual_values_inserted": 0,
            "already_captured": 0,
            "missed_capture_window": 0,
            "partial_existing_fail_closed": 0,
            "capture_failures": 0,
            "network_requests": 0,
        }
        if not network_enabled:
            result["status"] = "network_disabled"
            return result

        for row in self._due_events(current):
            result["events_considered"] += 1
            event_id = str(row["event_id"])
            event_type = str(row["event_type"]).upper()
            expected = set(self._metric_ids(event_type))
            if not expected:
                continue
            existing = self._existing_metrics(event_id)
            if expected.issubset(existing):
                result["already_captured"] += 1
                continue
            if existing:
                result["partial_existing_fail_closed"] += 1
                continue
            scheduled_at = float(row["scheduled_at"])
            if current - scheduled_at > self.capture_window_seconds:
                result["missed_capture_window"] += 1
                continue
            try:
                result["network_requests"] += 1
                values = self._fetch_event_values(row, now=current)
                built_ids = {value.metric_id for value in values}
                if built_ids != expected:
                    raise ValueError(f"incomplete BLS metric set: {sorted(built_ids)} != {sorted(expected)}")
                ingest = self.store.ingest(values, seen_at=current)
            except Exception as exc:
                result["capture_failures"] += 1
                result.setdefault("errors", []).append(
                    {"event_id": event_id, "error": f"{type(exc).__name__}: {exc}"[:300]}
                )
                continue
            result["events_captured"] += 1
            result["actual_values_inserted"] += int(ingest["inserted"])

        result["status"] = "ok" if int(result["capture_failures"]) == 0 else "partial"
        return result
