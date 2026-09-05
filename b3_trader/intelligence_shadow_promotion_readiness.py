from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from typing import Any

from .intelligence_event_response import (
    DATA_RIGHTS as EVENT_RESPONSE_DATA_RIGHTS,
    HORIZONS,
    OBSERVATION_TOLERANCE_SECONDS,
    PROVIDER_ID as EVENT_RESPONSE_PROVIDER_ID,
)
from .intelligence_event_response_us_sensitivity import MIN_DESCRIPTIVE_SAMPLES
from .intelligence_us_index_intraday import TWELVE_DATA_DATA_RIGHTS, TWELVE_DATA_PROVIDER_ID
from .intelligence_us_market_reference import SERIES_BY_SOURCE

STATUS_WAITING = "waiting_for_samples"
STATUS_INSUFFICIENT = "insufficient_evidence"
STATUS_READY = "evidence_ready_manual_review"

REQUIRED_HORIZONS = tuple(label for label, _ in HORIZONS)
REQUIRED_REFERENCE_SOURCES = tuple(SERIES_BY_SOURCE)
EXPECTED_COIN_PROVIDER_ID = EVENT_RESPONSE_PROVIDER_ID
EXPECTED_REFERENCE_PROVIDER_ID = TWELVE_DATA_PROVIDER_ID
EXPECTED_COIN_DATA_RIGHTS = EVENT_RESPONSE_DATA_RIGHTS
EXPECTED_REFERENCE_DATA_RIGHTS = TWELVE_DATA_DATA_RIGHTS
MIN_SAMPLES_PER_CELL = MIN_DESCRIPTIVE_SAMPLES
MIN_DISTINCT_EVENTS_PER_CELL = MIN_DESCRIPTIVE_SAMPLES
MAX_BLOCKERS = 50
REQUIRED_CELLS_PER_CANDIDATE = len(REQUIRED_HORIZONS) * len(REQUIRED_REFERENCE_SOURCES)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _safe_json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _finite(value: Any) -> bool:
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


class ShadowPromotionReadinessEvaluator:
    """Read-only evidence gate for future manual review.

    A positive result means only that bounded shadow-research evidence is complete
    enough for a human to inspect. This evaluator never promotes, scores, sizes or
    places orders.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=10000")

    @staticmethod
    def _base_result() -> dict[str, Any]:
        return {
            "ok": True,
            "status": STATUS_WAITING,
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "score_authority": False,
            "promotion_eligible": False,
            "automatic_promotion": False,
            "manual_review_ready": False,
            "missing_values_coerced_to_zero": False,
            "network_requests": 0,
            "minimum_samples_per_cell": MIN_SAMPLES_PER_CELL,
            "minimum_distinct_events_per_cell": MIN_DISTINCT_EVENTS_PER_CELL,
            "required_horizons": list(REQUIRED_HORIZONS),
            "required_reference_sources": list(REQUIRED_REFERENCE_SOURCES),
            "required_cells_per_candidate": REQUIRED_CELLS_PER_CANDIDATE,
            "expected_coin_provider_id": EXPECTED_COIN_PROVIDER_ID,
            "expected_reference_provider_id": EXPECTED_REFERENCE_PROVIDER_ID,
            "sensitivity_rows_considered": 0,
            "expected_provider_rows": 0,
            "candidates_considered": 0,
            "candidates_ready": 0,
            "blockers": [],
            "candidate_summaries": [],
        }

    @staticmethod
    def _append(blockers: list[str], code: str) -> None:
        if code and code not in blockers and len(blockers) < MAX_BLOCKERS:
            blockers.append(code)

    def _response_index(self) -> dict[tuple[str, str, str, str, str], sqlite3.Row]:
        if not _table_exists(self.conn, "research_intelligence_event_responses"):
            return {}
        rows = self.conn.execute(
            """SELECT event_id,exchange,market,horizon_label,provider_id,data_rights,attributes_json
               FROM research_intelligence_event_responses
               WHERE provider_id=?""",
            (EXPECTED_COIN_PROVIDER_ID,),
        ).fetchall()
        return {
            (
                _clean(row["event_id"]),
                _clean(row["exchange"]).lower(),
                _clean(row["market"]).upper(),
                _clean(row["horizon_label"]).lower(),
                _clean(row["provider_id"]).lower(),
            ): row
            for row in rows
        }

    def _validate_sensitivity_row(self, row: sqlite3.Row, blockers: list[str]) -> None:
        if int(row["score_authority"] or 0) != 0:
            self._append(blockers, "sensitivity_score_authority_enabled")
        if int(row["promotion_eligible"] or 0) != 0:
            self._append(blockers, "sensitivity_promotion_eligible_enabled")
        if int(row["sample_count"] or 0) < MIN_SAMPLES_PER_CELL:
            self._append(blockers, "insufficient_samples_per_cell")
        if int(row["distinct_event_count"] or 0) < MIN_DISTINCT_EVENTS_PER_CELL:
            self._append(blockers, "insufficient_distinct_events_per_cell")
        if _clean(row["readiness"]).lower() != "descriptive_ready":
            self._append(blockers, "sensitivity_not_descriptive_ready")
        for column in (
            "mean_coin_return_pct",
            "mean_reference_return_pct",
            "stdev_coin_return_pct",
            "stdev_reference_return_pct",
            "covariance",
            "beta",
            "correlation",
            "mean_abs_coin_return_pct",
            "mean_start_skew_seconds",
            "mean_end_skew_seconds",
        ):
            if not _finite(row[column]):
                self._append(blockers, "non_finite_sensitivity_statistics")
                break

    def _validate_pairs(
        self,
        *,
        candidate: tuple[str, str, str, str, str, str],
        horizon_label: str,
        reference_source_id: str,
        response_index: dict[tuple[str, str, str, str, str], sqlite3.Row],
        blockers: list[str],
    ) -> None:
        event_type, event_source_id, exchange, market, coin_provider_id, reference_provider_id = candidate
        rows = self.conn.execute(
            """SELECT * FROM research_intelligence_event_response_us_pairs
               WHERE event_type=? AND event_source_id=? AND exchange=? AND market=?
                 AND horizon_label=? AND coin_provider_id=?
                 AND reference_source_id=? AND reference_provider_id=?
               ORDER BY event_ts,event_id""",
            (
                event_type,
                event_source_id,
                exchange,
                market,
                horizon_label,
                coin_provider_id,
                reference_source_id,
                reference_provider_id,
            ),
        ).fetchall()
        if len(rows) < MIN_SAMPLES_PER_CELL:
            self._append(blockers, "insufficient_pair_rows")
            return
        if len({_clean(row["event_id"]) for row in rows}) < MIN_DISTINCT_EVENTS_PER_CELL:
            self._append(blockers, "insufficient_pair_distinct_events")
            return

        expected_series = SERIES_BY_SOURCE.get(reference_source_id, "")
        for row in rows:
            if _clean(row["reference_series"]) != expected_series:
                self._append(blockers, "reference_series_mismatch")
            if _clean(row["start_data_rights"]) != EXPECTED_REFERENCE_DATA_RIGHTS:
                self._append(blockers, "reference_data_rights_mismatch")
            if _clean(row["end_data_rights"]) != EXPECTED_REFERENCE_DATA_RIGHTS:
                self._append(blockers, "reference_data_rights_mismatch")

            numeric_columns = (
                "coin_return_pct",
                "reference_return_pct",
                "reference_start_value",
                "reference_end_value",
                "start_skew_seconds",
                "end_skew_seconds",
            )
            if any(not _finite(row[column]) for column in numeric_columns):
                self._append(blockers, "non_finite_pair_value")
                continue
            if float(row["reference_start_value"]) <= 0 or float(row["reference_end_value"]) <= 0:
                self._append(blockers, "non_positive_reference_value")
            start_skew = float(row["start_skew_seconds"])
            end_skew = float(row["end_skew_seconds"])
            if (
                start_skew < 0
                or end_skew < 0
                or start_skew > OBSERVATION_TOLERANCE_SECONDS + 1e-9
                or end_skew > OBSERVATION_TOLERANCE_SECONDS + 1e-9
            ):
                self._append(blockers, "reference_endpoint_skew_out_of_bounds")

            if _clean(row["start_latency_class"]).lower() in {"", "unknown"}:
                self._append(blockers, "reference_quality_metadata_unresolved")
            if _clean(row["end_latency_class"]).lower() in {"", "unknown"}:
                self._append(blockers, "reference_quality_metadata_unresolved")
            if _clean(row["start_session_state"]).lower() in {"", "unknown"}:
                self._append(blockers, "reference_quality_metadata_unresolved")
            if _clean(row["end_session_state"]).lower() in {"", "unknown"}:
                self._append(blockers, "reference_quality_metadata_unresolved")

            response_key = (
                _clean(row["event_id"]),
                exchange,
                market,
                horizon_label,
                coin_provider_id,
            )
            response = response_index.get(response_key)
            if response is None:
                self._append(blockers, "source_response_missing")
                continue
            if _clean(response["data_rights"]) != EXPECTED_COIN_DATA_RIGHTS:
                self._append(blockers, "coin_data_rights_mismatch")
            attrs = _safe_json(response["attributes_json"])
            if attrs.get("score_authority") not in (False, 0):
                self._append(blockers, "source_response_score_authority_enabled")
            if attrs.get("missing_values_coerced_to_zero") not in (False, 0):
                self._append(blockers, "source_response_missing_value_contract_violation")
            if attrs.get("point_in_time_backfill_used") not in (False, 0):
                self._append(blockers, "source_response_backfill_used")

    def run(self) -> dict[str, Any]:
        result = self._base_result()
        sensitivity_table = "research_intelligence_event_response_us_sensitivity"
        pair_table = "research_intelligence_event_response_us_pairs"

        if not _table_exists(self.conn, sensitivity_table):
            result["blockers"] = ["sensitivity_table_missing"]
            return result

        all_rows = self.conn.execute(f"SELECT * FROM {sensitivity_table}").fetchall()
        result["sensitivity_rows_considered"] = len(all_rows)
        if not all_rows:
            result["blockers"] = ["no_sensitivity_samples"]
            return result

        if not _table_exists(self.conn, pair_table):
            result["status"] = STATUS_INSUFFICIENT
            result["blockers"] = ["pair_table_missing"]
            return result

        expected_rows = [
            row
            for row in all_rows
            if _clean(row["coin_provider_id"]).lower() == EXPECTED_COIN_PROVIDER_ID
            and _clean(row["reference_provider_id"]).lower() == EXPECTED_REFERENCE_PROVIDER_ID
        ]
        result["expected_provider_rows"] = len(expected_rows)
        if not expected_rows:
            result["status"] = STATUS_INSUFFICIENT
            result["blockers"] = ["expected_provider_evidence_missing"]
            return result

        groups: dict[tuple[str, str, str, str, str, str], dict[tuple[str, str], sqlite3.Row]] = defaultdict(dict)
        for row in expected_rows:
            candidate = (
                _clean(row["event_type"]).upper(),
                _clean(row["event_source_id"]).lower(),
                _clean(row["exchange"]).lower(),
                _clean(row["market"]).upper(),
                _clean(row["coin_provider_id"]).lower(),
                _clean(row["reference_provider_id"]).lower(),
            )
            cell = (
                _clean(row["horizon_label"]).lower(),
                _clean(row["reference_source_id"]).lower(),
            )
            groups[candidate][cell] = row

        response_index = self._response_index()
        summaries: list[dict[str, Any]] = []
        global_blockers: list[str] = []
        ready_count = 0
        required_cells = {
            (horizon, source)
            for horizon in REQUIRED_HORIZONS
            for source in REQUIRED_REFERENCE_SOURCES
        }

        for candidate in sorted(groups):
            cells = groups[candidate]
            blockers: list[str] = []
            missing_cells = sorted(required_cells.difference(cells))
            if missing_cells:
                self._append(blockers, "required_cells_missing")

            for horizon_label, reference_source_id in sorted(required_cells.intersection(cells)):
                row = cells[(horizon_label, reference_source_id)]
                if _clean(row["reference_series"]) != SERIES_BY_SOURCE[reference_source_id]:
                    self._append(blockers, "reference_series_mismatch")
                self._validate_sensitivity_row(row, blockers)
                self._validate_pairs(
                    candidate=candidate,
                    horizon_label=horizon_label,
                    reference_source_id=reference_source_id,
                    response_index=response_index,
                    blockers=blockers,
                )

            candidate_ready = not blockers and not missing_cells
            if candidate_ready:
                ready_count += 1
            for blocker in blockers:
                self._append(global_blockers, blocker)
            summaries.append(
                {
                    "event_type": candidate[0],
                    "event_source_id": candidate[1],
                    "exchange": candidate[2],
                    "market": candidate[3],
                    "coin_provider_id": candidate[4],
                    "reference_provider_id": candidate[5],
                    "cells_present": len(cells),
                    "required_cells": REQUIRED_CELLS_PER_CANDIDATE,
                    "missing_cells": [f"{horizon}:{source}" for horizon, source in missing_cells][:24],
                    "manual_review_ready": candidate_ready,
                    "blockers": blockers[:20],
                }
            )

        result["candidates_considered"] = len(groups)
        result["candidates_ready"] = ready_count
        result["candidate_summaries"] = summaries[:20]
        result["blockers"] = global_blockers[:MAX_BLOCKERS]
        if ready_count > 0:
            result["status"] = STATUS_READY
            result["manual_review_ready"] = True
        else:
            result["status"] = STATUS_INSUFFICIENT
        return result
