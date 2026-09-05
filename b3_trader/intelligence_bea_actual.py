from __future__ import annotations

import calendar
import os
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

BEA_API_URL = "https://apps.bea.gov/api/data"
BEA_PROVIDER_ID = "bea_data_api"
BEA_AUTHORITY = "U.S. Bureau of Economic Analysis"
BEA_DATA_RIGHTS = "official_us_government_registered_api"
BEA_NIPA_DATASET = "NIPA"
PCE_PRICE_INDEX_TABLE = "T20804"
PCE_PRICE_MOM_TABLE = "T20807"
DEFAULT_CAPTURE_WINDOW_SECONDS = 6 * 60 * 60
DEFAULT_MAX_EVENTS = 4
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_ATTEMPTS = 2

EXPECTED_METRIC_IDS = (
    "US_PCE_PRICE_MOM_PCT",
    "US_CORE_PCE_PRICE_MOM_PCT",
    "US_PCE_PRICE_YOY_PCT",
    "US_CORE_PCE_PRICE_YOY_PCT",
)

_MONTHS = {name.casefold(): index for index, name in enumerate(calendar.month_name) if name}
_REFERENCE_RE = re.compile(r",\s*([A-Za-z]+)\s+(\d{4})\s*$", re.IGNORECASE)
_TIME_PERIOD_RE = re.compile(r"^(\d{4})M(0?[1-9]|1[0-2])$", re.IGNORECASE)


@dataclass(frozen=True)
class BeaReferencePeriod:
    year: int
    month: int

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def parse_bea_reference_period(title: str) -> BeaReferencePeriod | None:
    match = _REFERENCE_RE.search(str(title or "").strip())
    if not match:
        return None
    month = _MONTHS.get(match.group(1).casefold())
    year = int(match.group(2))
    if month is None or not 1 <= month <= 12 or year < 1900:
        return None
    return BeaReferencePeriod(year=year, month=month)


def _normalized_line_description(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    return re.sub(r"\s+\d+$", "", text).strip()


def _line_kind(description: object) -> str:
    value = _normalized_line_description(description)
    if value in {"personal consumption expenditures pce", "personal consumption expenditures"}:
        return "headline"
    if value in {
        "pce excluding food and energy",
        "personal consumption expenditures excluding food and energy",
    }:
        return "core"
    return ""


def _parse_data_value(value: object) -> float:
    text = str(value or "").replace(",", "").strip()
    if not text or text in {"---", "--", "...", "NA", "N/A"}:
        raise ValueError("BEA data value is missing")
    return float(text)


class BeaNipaClient:
    """Minimal registered-user BEA NIPA client for bounded PCE release capture."""

    def __init__(
        self,
        *,
        user_id: str | None = None,
        session: Any | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        attempts: int = DEFAULT_ATTEMPTS,
    ) -> None:
        configured = (
            user_id
            if user_id is not None
            else (os.getenv("BEA_API_KEY") or os.getenv("BEA_USER_ID") or "")
        )
        self.user_id = str(configured or "").strip()
        self.session = session or requests.Session()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.attempts = max(1, min(3, int(attempts)))

    @property
    def credential_status(self) -> str:
        if not self.user_id:
            return "missing"
        if len(self.user_id) != 36:
            return "invalid"
        return "ready"

    def fetch_table(
        self,
        table_name: str,
        *,
        years: Iterable[int],
    ) -> dict[str, dict[tuple[int, int], float]]:
        if self.credential_status != "ready":
            raise ValueError(f"BEA API credential is {self.credential_status}")
        table = str(table_name or "").strip().upper()
        if table not in {PCE_PRICE_INDEX_TABLE, PCE_PRICE_MOM_TABLE}:
            raise ValueError(f"unsupported bounded BEA NIPA table: {table!r}")
        clean_years = sorted({int(year) for year in years})
        if not clean_years or len(clean_years) > 3:
            raise ValueError("bounded BEA request supports 1 to 3 calendar years")
        if clean_years[-1] - clean_years[0] > 2:
            raise ValueError("bounded BEA request year span exceeds 3 calendar years")

        params = {
            "UserID": self.user_id,
            "method": "GetData",
            "DataSetName": BEA_NIPA_DATASET,
            "TableName": table,
            "Frequency": "M",
            "Year": ",".join(str(year) for year in clean_years),
            "ResultFormat": "JSON",
        }
        response = None
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = self.session.get(
                    BEA_API_URL,
                    params=params,
                    timeout=self.timeout_seconds,
                    headers={"User-Agent": "crypto-event-notifier-phase5/1.0"},
                )
                status_code = int(getattr(response, "status_code", 200))
                if status_code in {429, 500, 502, 503, 504}:
                    last_error = RuntimeError(f"BEA API transient HTTP {status_code}")
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
            raise RuntimeError("BEA API request failed")

        if response is None:
            raise RuntimeError("BEA API request returned no response")
        body = response.json()
        root = body.get("BEAAPI") if isinstance(body, dict) else None
        results = root.get("Results") if isinstance(root, dict) else None
        if not isinstance(results, dict):
            raise ValueError("BEA API response is missing BEAAPI.Results")
        error = results.get("Error")
        if error:
            if isinstance(error, dict):
                description = str(error.get("APIErrorDescription") or "BEA API error").strip()
            else:
                description = "BEA API error"
            raise ValueError(description[:240])
        rows = results.get("Data")
        if not isinstance(rows, list):
            raise ValueError("BEA API response is missing Results.Data")

        output: dict[str, dict[tuple[int, int], float]] = {"headline": {}, "core": {}}
        for row in rows:
            if not isinstance(row, dict):
                continue
            returned_table = str(row.get("TableName") or table).strip().upper()
            if returned_table != table:
                continue
            kind = _line_kind(row.get("LineDescription"))
            if not kind:
                continue
            period_match = _TIME_PERIOD_RE.fullmatch(str(row.get("TimePeriod") or "").strip())
            if not period_match:
                continue
            year = int(period_match.group(1))
            month = int(period_match.group(2))
            if year not in clean_years:
                continue
            try:
                value = _parse_data_value(row.get("DataValue"))
            except (TypeError, ValueError):
                continue
            key = (year, month)
            previous = output[kind].get(key)
            if previous is not None and abs(previous - value) > 1e-12:
                raise ValueError(f"conflicting BEA {kind} value for {table} {year:04d}-{month:02d}")
            output[kind][key] = value

        if not output["headline"] or not output["core"]:
            raise ValueError(f"BEA table {table} is missing headline/core PCE rows")
        return output


def _require_value(
    data: dict[str, dict[tuple[int, int], float]],
    kind: str,
    period: BeaReferencePeriod,
) -> float:
    try:
        return float(data[kind][(period.year, period.month)])
    except KeyError as exc:
        raise ValueError(f"missing BEA {kind} value for {period.label}") from exc


def _metric(
    *,
    event_id: str,
    metric_id: str,
    numeric_value: float,
    reference_period: BeaReferencePeriod,
    known_at: float,
    source_tables: list[str],
    formula: str,
    inputs: dict[str, float],
) -> MacroReleaseValue:
    return normalize_macro_release_value(
        event_id=event_id,
        event_type="US_PCE",
        metric_id=metric_id,
        value_role="actual",
        numeric_value=numeric_value,
        unit="PERCENT",
        reference_period=reference_period.label,
        provider_id=BEA_PROVIDER_ID,
        provider_url=BEA_API_URL,
        authority=BEA_AUTHORITY,
        data_rights=BEA_DATA_RIGHTS,
        known_at=known_at,
        received_at=known_at,
        revision_no=0,
        revision_label="initial_api_capture",
        attributes={
            "dataset": BEA_NIPA_DATASET,
            "table_names": source_tables,
            "formula": formula,
            "inputs": inputs,
            "capture_policy": "first_complete_official_api_observation_within_release_window",
            "score_authority": False,
            "credential_exposed": False,
        },
    )


def build_bea_pce_actual_values(
    *,
    event_id: str,
    title: str,
    known_at: float,
    mom_data: dict[str, dict[tuple[int, int], float]],
    index_data: dict[str, dict[tuple[int, int], float]],
) -> list[MacroReleaseValue]:
    reference = parse_bea_reference_period(title)
    if reference is None:
        raise ValueError("cannot derive BEA PCE reference month from event title")
    prior_year = BeaReferencePeriod(reference.year - 1, reference.month)

    headline_mom = _require_value(mom_data, "headline", reference)
    core_mom = _require_value(mom_data, "core", reference)
    headline_index = _require_value(index_data, "headline", reference)
    headline_prior = _require_value(index_data, "headline", prior_year)
    core_index = _require_value(index_data, "core", reference)
    core_prior = _require_value(index_data, "core", prior_year)
    if headline_prior <= 0 or core_prior <= 0:
        raise ValueError("PCE prior-year price-index denominator must be positive")

    headline_yoy = (headline_index / headline_prior - 1.0) * 100.0
    core_yoy = (core_index / core_prior - 1.0) * 100.0
    return [
        _metric(
            event_id=event_id,
            metric_id="US_PCE_PRICE_MOM_PCT",
            numeric_value=headline_mom,
            reference_period=reference,
            known_at=known_at,
            source_tables=[PCE_PRICE_MOM_TABLE],
            formula="published_monthly_percent_change",
            inputs={"published_mom_pct": headline_mom},
        ),
        _metric(
            event_id=event_id,
            metric_id="US_CORE_PCE_PRICE_MOM_PCT",
            numeric_value=core_mom,
            reference_period=reference,
            known_at=known_at,
            source_tables=[PCE_PRICE_MOM_TABLE],
            formula="published_monthly_percent_change_ex_food_energy",
            inputs={"published_core_mom_pct": core_mom},
        ),
        _metric(
            event_id=event_id,
            metric_id="US_PCE_PRICE_YOY_PCT",
            numeric_value=headline_yoy,
            reference_period=reference,
            known_at=known_at,
            source_tables=[PCE_PRICE_INDEX_TABLE],
            formula="(current_price_index / prior_year_same_month_price_index - 1) * 100",
            inputs={"current_price_index": headline_index, "prior_year_same_month_price_index": headline_prior},
        ),
        _metric(
            event_id=event_id,
            metric_id="US_CORE_PCE_PRICE_YOY_PCT",
            numeric_value=core_yoy,
            reference_period=reference,
            known_at=known_at,
            source_tables=[PCE_PRICE_INDEX_TABLE],
            formula="(current_core_price_index / prior_year_same_month_core_price_index - 1) * 100",
            inputs={"current_core_price_index": core_index, "prior_year_same_month_core_price_index": core_prior},
        ),
    ]


class BeaActualCaptureService:
    """Capture initial PCE actuals only near the official BEA release boundary."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        client: BeaNipaClient | None = None,
        capture_window_seconds: float = DEFAULT_CAPTURE_WINDOW_SECONDS,
        max_events: int = DEFAULT_MAX_EVENTS,
    ) -> None:
        self.conn = conn
        self.client = client or BeaNipaClient()
        self.capture_window_seconds = max(60.0, min(24 * 60 * 60, float(capture_window_seconds)))
        self.max_events = max(1, min(12, int(max_events)))
        self.store = MacroReleaseValueStore(conn)

    def _existing_metrics(self, event_id: str) -> set[str]:
        rows = self.conn.execute(
            """SELECT metric_id FROM research_intelligence_macro_values
               WHERE event_id=? AND value_role='actual' AND provider_id=?
                 AND revision_no=0""",
            (event_id, BEA_PROVIDER_ID),
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
               WHERE source_id='us_bea_release_schedule'
                 AND event_type='US_PCE'
                 AND scheduled_at>0 AND scheduled_at<=?
               ORDER BY scheduled_at DESC,event_id
               LIMIT ?""",
            (now, self.max_events),
        ).fetchall()

    def _fetch_event_values(self, row: sqlite3.Row, *, now: float) -> list[MacroReleaseValue]:
        reference = parse_bea_reference_period(str(row["title"]))
        if reference is None:
            raise ValueError("cannot derive BEA PCE reference month from stored event title")
        years = [reference.year - 1, reference.year]
        mom_data = self.client.fetch_table(PCE_PRICE_MOM_TABLE, years=years)
        index_data = self.client.fetch_table(PCE_PRICE_INDEX_TABLE, years=years)
        return build_bea_pce_actual_values(
            event_id=str(row["event_id"]),
            title=str(row["title"]),
            known_at=now,
            mom_data=mom_data,
            index_data=index_data,
        )

    def run_once(self, *, now: float | None = None, network_enabled: bool = False) -> dict[str, Any]:
        current = float(now if now is not None else time.time())
        credential_status = self.client.credential_status
        result: dict[str, Any] = {
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "network_enabled": bool(network_enabled),
            "credential_status": credential_status,
            "credential_exposed": False,
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
        if credential_status != "ready":
            result["status"] = f"credentials_{credential_status}"
            return result

        expected = set(EXPECTED_METRIC_IDS)
        for row in self._due_events(current):
            result["events_considered"] += 1
            event_id = str(row["event_id"])
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
                result["network_requests"] += 2
                values = self._fetch_event_values(row, now=current)
                built_ids = {value.metric_id for value in values}
                if built_ids != expected:
                    raise ValueError(f"incomplete BEA metric set: {sorted(built_ids)} != {sorted(expected)}")
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
