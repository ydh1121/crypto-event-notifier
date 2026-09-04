from __future__ import annotations

import math
import sqlite3
from typing import Any

from .intelligence_us_market_reference import SERIES_BY_SOURCE

PATH_QUALITY_VERSION = 1
DEFAULT_EXPECTED_INTERVAL_SECONDS = 60.0
DEFAULT_MIN_COVERAGE_RATIO = 0.80
DEFAULT_MAX_GAP_SECONDS = 180.0
DEFAULT_MAX_ENDPOINT_SKEW_SECONDS = 120.0


def _clean(value: object) -> str:
    return str(value or "").strip().lower()


def _finite(value: object, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def assess_us_market_reference_path(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    provider_id: str,
    start_at: float,
    end_at: float,
    expected_interval_seconds: float = DEFAULT_EXPECTED_INTERVAL_SECONDS,
    min_coverage_ratio: float = DEFAULT_MIN_COVERAGE_RATIO,
    max_gap_seconds: float = DEFAULT_MAX_GAP_SECONDS,
    max_endpoint_skew_seconds: float = DEFAULT_MAX_ENDPOINT_SKEW_SECONDS,
) -> dict[str, Any]:
    """Assess whether one provider's reference path is dense enough for pairing.

    This is a data-quality gate only. It does not infer market direction, confidence,
    regime, or score contribution. Missing provider bars remain missing; the helper
    never interpolates or synthesizes observations.
    """

    clean_source = _clean(source_id)
    clean_provider = _clean(provider_id)
    if clean_source not in SERIES_BY_SOURCE:
        raise ValueError(f"unsupported US market reference source: {source_id!r}")
    if not clean_provider:
        raise ValueError("provider_id is required")

    start = _finite(start_at, name="start_at")
    end = _finite(end_at, name="end_at")
    interval = _finite(expected_interval_seconds, name="expected_interval_seconds")
    min_coverage = _finite(min_coverage_ratio, name="min_coverage_ratio")
    max_gap = _finite(max_gap_seconds, name="max_gap_seconds")
    endpoint_skew = _finite(max_endpoint_skew_seconds, name="max_endpoint_skew_seconds")
    if start <= 0 or end <= 0 or end < start:
        raise ValueError("start_at/end_at must be positive and ordered")
    if interval <= 0:
        raise ValueError("expected_interval_seconds must be > 0")
    if not 0.0 <= min_coverage <= 1.0:
        raise ValueError("min_coverage_ratio must be between 0 and 1")
    if max_gap < interval:
        raise ValueError("max_gap_seconds must be >= expected_interval_seconds")
    if endpoint_skew < 0:
        raise ValueError("max_endpoint_skew_seconds must be >= 0")

    result: dict[str, Any] = {
        "source_id": clean_source,
        "series": SERIES_BY_SOURCE[clean_source],
        "provider_id": clean_provider,
        "target_start_at": start,
        "target_end_at": end,
        "expected_interval_seconds": interval,
        "min_coverage_ratio": min_coverage,
        "max_gap_threshold_seconds": max_gap,
        "max_endpoint_skew_seconds": endpoint_skew,
        "path_quality_version": PATH_QUALITY_VERSION,
        "eligible_for_pairing": False,
        "status": "not_evaluated",
        "reasons": [],
        "observation_count": 0,
        "expected_count": 0,
        "coverage_ratio": 0.0,
        "max_gap_seconds": None,
        "start_observed_at": None,
        "end_observed_at": None,
        "start_skew_seconds": None,
        "end_skew_seconds": None,
        "latency_classes": [],
        "delayed_seconds_values": [],
        "session_states": [],
        "data_rights_complete": False,
    }

    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "research_us_market_reference" not in tables:
        result["status"] = "reference_table_missing"
        result["reasons"] = ["reference_table_missing"]
        return result

    start_row = conn.execute(
        """SELECT * FROM research_us_market_reference
           WHERE source_id=? AND provider_id=? AND observed_at>=? AND observed_at<=?
           ORDER BY observed_at ASC LIMIT 1""",
        (clean_source, clean_provider, start, start + endpoint_skew),
    ).fetchone()
    end_row = conn.execute(
        """SELECT * FROM research_us_market_reference
           WHERE source_id=? AND provider_id=? AND observed_at>=? AND observed_at<=?
           ORDER BY observed_at ASC LIMIT 1""",
        (clean_source, clean_provider, end, end + endpoint_skew),
    ).fetchone()
    reasons: list[str] = []
    if start_row is None:
        reasons.append("start_endpoint_missing")
    if end_row is None:
        reasons.append("end_endpoint_missing")
    if reasons:
        result["status"] = "endpoint_missing"
        result["reasons"] = reasons
        return result

    start_observed = float(start_row["observed_at"])
    end_observed = float(end_row["observed_at"])
    if end_observed < start_observed:
        result["status"] = "invalid_observation_order"
        result["reasons"] = ["invalid_observation_order"]
        return result

    rows = conn.execute(
        """SELECT observed_at,latency_class,delayed_seconds,session_state,data_rights
           FROM research_us_market_reference
           WHERE source_id=? AND provider_id=? AND observed_at>=? AND observed_at<=?
           ORDER BY observed_at ASC""",
        (clean_source, clean_provider, start_observed, end_observed),
    ).fetchall()
    observed_times = [float(row["observed_at"]) for row in rows]
    observation_count = len(observed_times)
    span = max(0.0, end_observed - start_observed)
    expected_count = int(math.floor(span / interval + 1e-9)) + 1
    coverage_ratio = min(1.0, observation_count / max(1, expected_count))
    gaps = [right - left for left, right in zip(observed_times, observed_times[1:])]
    path_max_gap = max(gaps) if gaps else 0.0

    latency_classes = sorted({_clean(row["latency_class"]) for row in rows if _clean(row["latency_class"])})
    delayed_values = sorted(
        {
            float(row["delayed_seconds"])
            for row in rows
            if row["delayed_seconds"] is not None
        }
    )
    session_states = sorted({_clean(row["session_state"]) for row in rows if _clean(row["session_state"])})
    rights_complete = all(bool(str(row["data_rights"] or "").strip()) for row in rows) and bool(rows)

    start_skew = start_observed - start
    end_skew = end_observed - end
    result.update(
        {
            "observation_count": observation_count,
            "expected_count": expected_count,
            "coverage_ratio": coverage_ratio,
            "max_gap_seconds": path_max_gap,
            "start_observed_at": start_observed,
            "end_observed_at": end_observed,
            "start_skew_seconds": start_skew,
            "end_skew_seconds": end_skew,
            "latency_classes": latency_classes,
            "delayed_seconds_values": delayed_values,
            "session_states": session_states,
            "data_rights_complete": rights_complete,
        }
    )

    if observation_count == 0:
        reasons.append("no_observations")
    if coverage_ratio + 1e-12 < min_coverage:
        reasons.append("insufficient_coverage")
    if path_max_gap > max_gap + 1e-12:
        reasons.append("gap_exceeded")
    if len(latency_classes) != 1:
        reasons.append("mixed_or_missing_latency_class")
    if len(delayed_values) > 1:
        reasons.append("mixed_delay_contract")
    if not rights_complete:
        reasons.append("missing_data_rights")
    if start_skew < -1e-9 or start_skew > endpoint_skew + 1e-9:
        reasons.append("start_endpoint_skew_exceeded")
    if end_skew < -1e-9 or end_skew > endpoint_skew + 1e-9:
        reasons.append("end_endpoint_skew_exceeded")

    result["reasons"] = reasons
    if reasons:
        result["status"] = reasons[0]
        result["eligible_for_pairing"] = False
    else:
        result["status"] = "ok"
        result["eligible_for_pairing"] = True
    return result
