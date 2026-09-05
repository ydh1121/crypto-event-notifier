from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv

from .auto_demo_v2 import DB_PATH
from .config import Settings
from .intelligence_bea_actual import BEA_DATA_RIGHTS, BEA_PROVIDER_ID, EXPECTED_METRIC_IDS
from .intelligence_bea_actual_resilient import BEA_NEWS_DATA_RIGHTS, BEA_NEWS_PROVIDER_ID
from .intelligence_bls_actual import BLS_DATA_RIGHTS, BLS_PROVIDER_ID
from .intelligence_event_response import (
    DATA_RIGHTS as EVENT_RESPONSE_DATA_RIGHTS,
    HORIZONS,
    OBSERVATION_TOLERANCE_SECONDS,
    PROVIDER_ID as EVENT_RESPONSE_PROVIDER_ID,
)
from .intelligence_shadow_promotion_readiness import (
    STATUS_INSUFFICIENT,
    STATUS_READY,
    STATUS_WAITING,
    ShadowPromotionReadinessEvaluator,
)
from .intelligence_trading_economics_consensus import (
    EXPECTED_METRICS as TE_EXPECTED_METRICS,
    TE_DATA_RIGHTS,
    TE_PROVIDER_ID,
)
from .intelligence_us_index_intraday import TWELVE_DATA_DATA_RIGHTS, TWELVE_DATA_PROVIDER_ID
from .intelligence_us_market_reference import SERIES_BY_SOURCE
from .phase5_runtime_check import evaluate_phase5_runtime, fetch_runtime_snapshot

PASS = "PASS"
WAITING = "WAITING"
BLOCKED = "BLOCKED"
FAILED = "FAILED"

STATUS_PRIORITY = {PASS: 0, WAITING: 1, BLOCKED: 2, FAILED: 3}
BLS_EXPECTED_METRICS: dict[str, tuple[str, ...]] = {
    "US_CPI": ("US_CPI_ALL_ITEMS_MOM_PCT", "US_CPI_ALL_ITEMS_YOY_PCT"),
    "US_EMPLOYMENT": ("US_NONFARM_PAYROLL_CHANGE_K", "US_UNEMPLOYMENT_RATE_PCT"),
}
BEA_EXPECTED_METRICS = {"US_PCE": tuple(EXPECTED_METRIC_IDS)}
REQUIRED_REFERENCE_SOURCES = tuple(SERIES_BY_SOURCE)
EXPECTED_HORIZON_SECONDS = {label: float(seconds) for label, seconds in HORIZONS}
CAPTURE_FAILURE_STATUSES = {"partial", "capture_error", "provider_error", "error", "failed"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _safe_json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _gate(
    gate_id: str,
    status: str,
    summary: str,
    *,
    evidence: Mapping[str, Any] | None = None,
    action_required: str = "",
) -> dict[str, Any]:
    if status not in STATUS_PRIORITY:
        raise ValueError(f"unsupported gate status: {status}")
    return {
        "id": gate_id,
        "status": status,
        "summary": summary,
        "evidence": dict(evidence or {}),
        "action_required": action_required,
    }


def _component_last_result(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    rows = snapshot.get("components") if isinstance(snapshot.get("components"), list) else []
    for row in rows:
        if not isinstance(row, dict) or _clean(row.get("name")) != "phase5-intelligence-ingest":
            continue
        last_result = row.get("last_result")
        return dict(last_result) if isinstance(last_result, dict) else {}
    return {}


def _capture_failure(last_result: Mapping[str, Any], key: str) -> tuple[bool, str]:
    capture = last_result.get(key)
    if not isinstance(capture, dict):
        return False, ""
    status = _clean(capture.get("status")).lower()
    if status in CAPTURE_FAILURE_STATUSES:
        return True, status
    if capture.get("ok") is False and status not in {
        "credential_missing",
        "waiting_for_samples",
        "waiting_for_observable_event",
        "waiting_for_us_market_reference_table",
        "waiting_for_reference_observations",
    }:
        return True, status or "ok_false"
    return False, status


def _phase5_runtime_gate(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_phase5_runtime(dict(snapshot))
    if result.get("ok") is True:
        return _gate(
            "phase5_runtime",
            PASS,
            "Phase 5 supervisor and official-source cycle are healthy.",
            evidence={
                "runs": result.get("runs"),
                "last_result_status": result.get("last_result_status"),
                "source_failures": result.get("source_failures"),
                "events_received": result.get("events_received"),
            },
        )
    return _gate(
        "phase5_runtime",
        FAILED,
        "Phase 5 runtime contract is not healthy.",
        evidence={"reasons": list(result.get("reasons") or [])},
        action_required="Restore the Phase 5 runtime contract before trusting downstream evidence.",
    )


def _macro_initial_actual_gate(
    conn: sqlite3.Connection,
    *,
    gate_id: str,
    source_id: str,
    expected_metrics: Mapping[str, tuple[str, ...]],
    provider_rights: Mapping[str, str],
    revision_labels: Mapping[str, str],
    capture_key: str,
    last_result: Mapping[str, Any],
    waiting_summary: str,
    waiting_action: str,
) -> dict[str, Any]:
    failed, capture_status = _capture_failure(last_result, capture_key)
    if failed:
        return _gate(
            gate_id,
            FAILED,
            "Current initial-actual capture reported a failure.",
            evidence={"runtime_capture_status": capture_status},
            action_required="Diagnose the current capture failure without backfilling an initial value.",
        )

    if not _table_exists(conn, "research_intelligence_macro_values") or not _table_exists(
        conn, "research_intelligence_events"
    ):
        return _gate(gate_id, WAITING, waiting_summary, action_required=waiting_action)

    providers = tuple(provider_rights)
    placeholders = ",".join("?" for _ in providers)
    rows = conn.execute(
        f"""SELECT v.*,e.source_id AS event_source_id,e.scheduled_at AS event_scheduled_at
            FROM research_intelligence_macro_values v
            JOIN research_intelligence_events e ON e.event_id=v.event_id
            WHERE v.value_role='actual' AND v.revision_no=0
              AND v.provider_id IN ({placeholders})
            ORDER BY v.event_id,v.provider_id,v.metric_id,v.known_at""",
        providers,
    ).fetchall()
    if not rows:
        return _gate(gate_id, WAITING, waiting_summary, action_required=waiting_action)

    violations: list[str] = []
    groups: dict[tuple[str, str, str], set[str]] = {}
    for row in rows:
        provider = _clean(row["provider_id"]).lower()
        event_type = _clean(row["event_type"]).upper()
        event_id = _clean(row["event_id"])
        if _clean(row["event_source_id"]).lower() != source_id:
            violations.append("event_source_mismatch")
        if _clean(row["data_rights"]) != provider_rights.get(provider, ""):
            violations.append("data_rights_mismatch")
        if _clean(row["revision_label"]) != revision_labels.get(provider, ""):
            violations.append("revision_label_mismatch")
        scheduled = float(row["event_scheduled_at"] or 0.0)
        known = float(row["known_at"] or 0.0)
        if scheduled <= 0 or known < scheduled or known - scheduled > 6 * 60 * 60 + 1e-6:
            violations.append("initial_capture_window_violation")
        attrs = _safe_json(row["attributes_json"])
        if attrs.get("score_authority") not in (False, 0):
            violations.append("score_authority_not_disabled")
        key = (event_id, provider, event_type)
        groups.setdefault(key, set()).add(_clean(row["metric_id"]).upper())

    complete = 0
    incomplete = 0
    for (_, _, event_type), metrics in groups.items():
        expected = set(expected_metrics.get(event_type, ()))
        if expected and expected.issubset(metrics):
            complete += 1
        else:
            incomplete += 1
    if incomplete:
        violations.append("incomplete_initial_actual_metric_set")

    if violations:
        return _gate(
            gate_id,
            FAILED,
            "Stored initial-actual evidence violates the fail-closed contract.",
            evidence={
                "rows": len(rows),
                "complete_events": complete,
                "violations": sorted(set(violations)),
            },
            action_required="Inspect the stored evidence; do not repair it by inventing historical initial values.",
        )
    if complete < 1:
        return _gate(gate_id, WAITING, waiting_summary, action_required=waiting_action)
    return _gate(
        gate_id,
        PASS,
        "At least one complete release-time initial actual is stored with provenance.",
        evidence={"rows": len(rows), "complete_events": complete, "providers": sorted({k[1] for k in groups})},
    )


def _consensus_gate(
    conn: sqlite3.Connection,
    *,
    last_result: Mapping[str, Any],
    env: Mapping[str, str],
) -> dict[str, Any]:
    failed, capture_status = _capture_failure(last_result, "consensus_capture")
    if failed:
        return _gate(
            "consensus_provider",
            FAILED,
            "Consensus capture reported a provider/runtime failure.",
            evidence={"runtime_capture_status": capture_status},
            action_required="Resolve the provider failure before accepting new consensus snapshots.",
        )

    credential_ready = bool(_clean(env.get("TRADING_ECONOMICS_API_KEY")))
    rows: list[sqlite3.Row] = []
    if _table_exists(conn, "research_intelligence_macro_values") and _table_exists(
        conn, "research_intelligence_events"
    ):
        rows = conn.execute(
            """SELECT v.*,e.scheduled_at AS event_scheduled_at
               FROM research_intelligence_macro_values v
               JOIN research_intelligence_events e ON e.event_id=v.event_id
               WHERE v.value_role='consensus' AND v.provider_id=? AND v.revision_no=0
               ORDER BY v.event_id,v.metric_id,v.known_at""",
            (TE_PROVIDER_ID,),
        ).fetchall()

    violations: list[str] = []
    grouped: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        event_id = _clean(row["event_id"])
        event_type = _clean(row["event_type"]).upper()
        scheduled = float(row["event_scheduled_at"] or 0.0)
        known = float(row["known_at"] or 0.0)
        if scheduled <= 0 or not (0 < known < scheduled):
            violations.append("consensus_not_pre_release")
        if _clean(row["data_rights"]) != TE_DATA_RIGHTS:
            violations.append("data_rights_mismatch")
        if _clean(row["revision_label"]) != "pre_release_snapshot":
            violations.append("revision_label_mismatch")
        attrs = _safe_json(row["attributes_json"])
        if attrs.get("score_authority") not in (False, 0):
            violations.append("score_authority_not_disabled")
        if attrs.get("point_in_time_backfill_used") not in (False, 0):
            violations.append("point_in_time_backfill_used")
        grouped.setdefault((event_id, event_type), set()).add(_clean(row["metric_id"]).upper())

    complete = 0
    incomplete = 0
    for (_, event_type), metrics in grouped.items():
        expected = set(TE_EXPECTED_METRICS.get(event_type, ()))
        if expected and expected.issubset(metrics):
            complete += 1
        else:
            incomplete += 1
    if incomplete:
        violations.append("incomplete_consensus_metric_set")
    if violations:
        return _gate(
            "consensus_provider",
            FAILED,
            "Stored consensus evidence violates the point-in-time contract.",
            evidence={"rows": len(rows), "complete_events": complete, "violations": sorted(set(violations))},
            action_required="Inspect provider evidence and keep score/order paths disconnected.",
        )
    if not credential_ready:
        return _gate(
            "consensus_provider",
            BLOCKED,
            "Trading Economics credential/entitlement is not configured for future captures.",
            evidence={"credential_status": "missing", "stored_complete_events": complete},
            action_required="Configure TRADING_ECONOMICS_API_KEY only after entitlement is confirmed.",
        )
    if complete < 1:
        return _gate(
            "consensus_provider",
            WAITING,
            "Provider is configured but no complete pre-release consensus snapshot is stored yet.",
            evidence={"credential_status": "ready", "stored_complete_events": 0},
            action_required="Keep Phase 5 running through a supported release pre-window.",
        )
    return _gate(
        "consensus_provider",
        PASS,
        "A complete point-in-time consensus snapshot is stored and the provider remains configured.",
        evidence={"credential_status": "ready", "stored_complete_events": complete},
    )


def _us_reference_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    if not _table_exists(conn, "research_us_market_reference"):
        return []
    return conn.execute(
        """SELECT * FROM research_us_market_reference
           WHERE provider_id=? ORDER BY source_id,observed_at""",
        (TWELVE_DATA_PROVIDER_ID,),
    ).fetchall()


def _us_index_reference_gate(
    conn: sqlite3.Connection,
    *,
    last_result: Mapping[str, Any],
    env: Mapping[str, str],
) -> tuple[dict[str, Any], list[sqlite3.Row]]:
    failed, capture_status = _capture_failure(last_result, "us_market_reference_capture")
    rows = _us_reference_rows(conn)
    if failed:
        return (
            _gate(
                "us_index_reference",
                FAILED,
                "U.S. index reference capture reported a provider/runtime failure.",
                evidence={"runtime_capture_status": capture_status},
                action_required="Resolve the provider failure without substituting synthetic index values.",
            ),
            rows,
        )

    violations: list[str] = []
    sources: set[str] = set()
    for row in rows:
        source_id = _clean(row["source_id"]).lower()
        sources.add(source_id)
        if source_id not in SERIES_BY_SOURCE:
            violations.append("unsupported_reference_source")
        if _clean(row["data_rights"]) != TWELVE_DATA_DATA_RIGHTS:
            violations.append("data_rights_mismatch")
        if not _finite(row["value"]) or float(row["value"]) <= 0:
            violations.append("invalid_reference_value")
        attrs = _safe_json(row["attributes_json"])
        if attrs.get("score_authority") not in (False, 0):
            violations.append("score_authority_not_disabled")
        if attrs.get("promotion_eligible") not in (False, 0):
            violations.append("promotion_eligible_not_disabled")
        if attrs.get("missing_values_coerced_to_zero") not in (False, 0):
            violations.append("missing_value_contract_violation")
    if violations:
        return (
            _gate(
                "us_index_reference",
                FAILED,
                "Stored U.S. reference evidence violates the provider contract.",
                evidence={"rows": len(rows), "violations": sorted(set(violations))},
                action_required="Inspect the stored provider evidence before downstream use.",
            ),
            rows,
        )

    credential_ready = bool(_clean(env.get("TWELVE_DATA_API_KEY")))
    present = sorted(set(REQUIRED_REFERENCE_SOURCES).intersection(sources))
    missing = sorted(set(REQUIRED_REFERENCE_SOURCES) - sources)
    if not credential_ready:
        return (
            _gate(
                "us_index_reference",
                BLOCKED,
                "Twelve Data credential/entitlement is not configured for continuous U.S. index capture.",
                evidence={"credential_status": "missing", "stored_rows": len(rows), "sources_present": present},
                action_required="Configure TWELVE_DATA_API_KEY after SPX/IXIC/VIX entitlement is confirmed.",
            ),
            rows,
        )
    if missing:
        return (
            _gate(
                "us_index_reference",
                WAITING,
                "Provider is configured but all required U.S. reference series have not been observed yet.",
                evidence={"credential_status": "ready", "stored_rows": len(rows), "sources_missing": missing},
                action_required="Keep the collector running until SP500, Nasdaq Composite and VIX observations are stored.",
            ),
            rows,
        )
    return (
        _gate(
            "us_index_reference",
            PASS,
            "All required U.S. index reference series are persisted from the configured provider.",
            evidence={"credential_status": "ready", "stored_rows": len(rows), "sources_present": present},
        ),
        rows,
    )


def _reference_quality_gate(rows: list[sqlite3.Row]) -> dict[str, Any]:
    if not rows:
        return _gate(
            "us_reference_quality",
            WAITING,
            "No Twelve Data reference observations exist yet, so session/latency quality cannot be evaluated.",
            action_required="First satisfy the U.S. index reference gate.",
        )
    latest: dict[str, sqlite3.Row] = {}
    for row in rows:
        source = _clean(row["source_id"]).lower()
        current = latest.get(source)
        if current is None or float(row["observed_at"]) > float(current["observed_at"]):
            latest[source] = row
    missing = sorted(set(REQUIRED_REFERENCE_SOURCES) - set(latest))
    if missing:
        return _gate(
            "us_reference_quality",
            WAITING,
            "Reference quality cannot be evaluated until all required sources are present.",
            evidence={"sources_missing": missing},
            action_required="Accumulate all three U.S. reference series first.",
        )
    unresolved: list[str] = []
    for source, row in latest.items():
        if _clean(row["session_state"]).lower() in {"", "unknown"}:
            unresolved.append(f"{source}:session_state")
        if _clean(row["latency_class"]).lower() in {"", "unknown"}:
            unresolved.append(f"{source}:latency_class")
    if unresolved:
        return _gate(
            "us_reference_quality",
            BLOCKED,
            "Latest U.S. reference observations still have unresolved session/latency semantics.",
            evidence={"unresolved": sorted(unresolved)},
            action_required="Resolve provider session and latency semantics explicitly; do not infer them from price values.",
        )
    return _gate(
        "us_reference_quality",
        PASS,
        "Latest U.S. reference observations carry resolved session and latency metadata.",
        evidence={"sources_checked": sorted(latest)},
    )


def _event_response_gate(conn: sqlite3.Connection, last_result: Mapping[str, Any]) -> dict[str, Any]:
    failed, capture_status = _capture_failure(last_result, "event_response_capture")
    if failed:
        return _gate(
            "event_response_samples",
            FAILED,
            "Strict event-response capture reported a runtime failure.",
            evidence={"runtime_capture_status": capture_status},
            action_required="Diagnose the collector before using any response evidence.",
        )
    if not _table_exists(conn, "research_intelligence_event_responses"):
        return _gate(
            "event_response_samples",
            WAITING,
            "The strict response table has not been initialized yet.",
            action_required="Keep Phase 5 and market-flow collection running.",
        )
    rows = conn.execute(
        """SELECT * FROM research_intelligence_event_responses
           WHERE provider_id=? ORDER BY event_ts,horizon_seconds,exchange,market""",
        (EVENT_RESPONSE_PROVIDER_ID,),
    ).fetchall()
    if not rows:
        return _gate(
            "event_response_samples",
            WAITING,
            "No observable forward event-response sample exists yet.",
            evidence={"sample_count": 0},
            action_required="Maintain continuous BTC/ETH trade coverage through the next precise event and its +1d horizon.",
        )
    violations: list[str] = []
    horizons: dict[str, int] = {}
    events: set[str] = set()
    for row in rows:
        label = _clean(row["horizon_label"]).lower()
        expected_seconds = EXPECTED_HORIZON_SECONDS.get(label)
        events.add(_clean(row["event_id"]))
        horizons[label] = horizons.get(label, 0) + 1
        if expected_seconds is None or abs(float(row["horizon_seconds"]) - expected_seconds) > 1e-6:
            violations.append("invalid_horizon")
            continue
        if _clean(row["data_rights"]) != EVENT_RESPONSE_DATA_RIGHTS:
            violations.append("data_rights_mismatch")
        numeric = [
            row["event_ts"], row["baseline_trade_ts"], row["baseline_price"], row["target_ts"],
            row["target_trade_ts"], row["target_price"], row["return_pct"], row["observation_tolerance_seconds"],
        ]
        if any(not _finite(value) for value in numeric):
            violations.append("non_finite_response_value")
            continue
        event_ts = float(row["event_ts"])
        baseline_ts = float(row["baseline_trade_ts"])
        target_ts = float(row["target_ts"])
        target_trade_ts = float(row["target_trade_ts"])
        tolerance = float(row["observation_tolerance_seconds"])
        if float(row["baseline_price"]) <= 0 or float(row["target_price"]) <= 0:
            violations.append("non_positive_price")
        if baseline_ts > event_ts or event_ts - baseline_ts > tolerance + 1e-6:
            violations.append("baseline_semantics_violation")
        if abs(target_ts - (event_ts + expected_seconds)) > 1e-6:
            violations.append("target_timestamp_violation")
        if target_trade_ts < target_ts or target_trade_ts - target_ts > tolerance + 1e-6:
            violations.append("target_semantics_violation")
        if tolerance > OBSERVATION_TOLERANCE_SECONDS + 1e-6:
            violations.append("observation_tolerance_violation")
        attrs = _safe_json(row["attributes_json"])
        if attrs.get("score_authority") not in (False, 0):
            violations.append("score_authority_not_disabled")
        if attrs.get("point_in_time_backfill_used") not in (False, 0):
            violations.append("backfill_used")
        if attrs.get("missing_values_coerced_to_zero") not in (False, 0):
            violations.append("missing_value_contract_violation")
    if violations:
        return _gate(
            "event_response_samples",
            FAILED,
            "Stored event-response samples violate the strict observation contract.",
            evidence={"sample_count": len(rows), "violations": sorted(set(violations))},
            action_required="Quarantine invalid evidence; do not coerce or reconstruct missing observations.",
        )
    return _gate(
        "event_response_samples",
        PASS,
        "Strict forward event-response samples are present and contract-valid.",
        evidence={"sample_count": len(rows), "distinct_events": len(events), "horizon_counts": horizons},
    )


def _sensitivity_gate(conn: sqlite3.Connection, last_result: Mapping[str, Any]) -> dict[str, Any]:
    failed, runtime_status = _capture_failure(last_result, "event_response_us_sensitivity")
    if failed:
        return _gate(
            "us_market_sensitivity",
            FAILED,
            "U.S. market sensitivity calculation reported a runtime failure.",
            evidence={"runtime_status": runtime_status},
            action_required="Fix the calculation path before interpreting sensitivity output.",
        )
    table = "research_intelligence_event_response_us_sensitivity"
    if not _table_exists(conn, table):
        return _gate(
            "us_market_sensitivity",
            WAITING,
            "Sensitivity storage is not initialized yet.",
            action_required="First accumulate event responses and U.S. reference observations.",
        )
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return _gate(
            "us_market_sensitivity",
            WAITING,
            "No sensitivity sample group exists yet.",
            evidence={"groups": 0, "descriptive_ready_groups": 0},
            action_required="Accumulate matched crypto-response/U.S.-reference pairs.",
        )
    violations: list[str] = []
    descriptive = 0
    for row in rows:
        readiness = _clean(row["readiness"]).lower()
        if int(row["score_authority"] or 0) != 0:
            violations.append("score_authority_enabled")
        if int(row["promotion_eligible"] or 0) != 0:
            violations.append("promotion_eligible_enabled")
        if int(row["sample_count"] or 0) <= 0 or int(row["distinct_event_count"] or 0) <= 0:
            violations.append("invalid_sample_count")
        if readiness not in {"insufficient_sample", "exploratory", "descriptive_ready"}:
            violations.append("invalid_readiness")
        if readiness == "descriptive_ready":
            descriptive += 1
        for column in (
            "mean_coin_return_pct", "mean_reference_return_pct", "stdev_coin_return_pct",
            "stdev_reference_return_pct", "covariance", "mean_abs_coin_return_pct",
            "mean_start_skew_seconds", "mean_end_skew_seconds",
        ):
            if not _finite(row[column]):
                violations.append("non_finite_sensitivity_statistic")
                break
    if violations:
        return _gate(
            "us_market_sensitivity",
            FAILED,
            "Stored sensitivity output violates the descriptive-research contract.",
            evidence={"groups": len(rows), "violations": sorted(set(violations))},
            action_required="Inspect the affected groups before any readiness evaluation.",
        )
    if descriptive < 1:
        return _gate(
            "us_market_sensitivity",
            WAITING,
            "Sensitivity groups exist but none has reached the descriptive sample threshold.",
            evidence={"groups": len(rows), "descriptive_ready_groups": 0},
            action_required="Continue accumulating distinct forward events; do not promote exploratory groups.",
        )
    return _gate(
        "us_market_sensitivity",
        PASS,
        "At least one sensitivity group has reached descriptive-ready evidence depth.",
        evidence={"groups": len(rows), "descriptive_ready_groups": descriptive},
    )


def _shadow_readiness_gate(conn: sqlite3.Connection) -> dict[str, Any]:
    try:
        result = ShadowPromotionReadinessEvaluator(conn).run()
    except Exception as exc:
        return _gate(
            "shadow_promotion_readiness",
            FAILED,
            "Shadow promotion-readiness evaluator could not complete.",
            evidence={"error": f"{type(exc).__name__}: {exc}"[:240]},
            action_required="Repair the evidence evaluator; keep all promotion authority disabled.",
        )
    safety_ok = (
        result.get("paper_only") is True
        and result.get("shadow_only") is True
        and result.get("can_place_orders") is False
        and result.get("score_mutation") is False
        and result.get("score_authority") is False
        and result.get("promotion_eligible") is False
        and result.get("automatic_promotion") is False
        and result.get("missing_values_coerced_to_zero") is False
    )
    if not safety_ok:
        return _gate(
            "shadow_promotion_readiness",
            FAILED,
            "Shadow readiness safety invariants are not asserted.",
            evidence={"status": result.get("status")},
            action_required="Restore fail-closed safety before using the readiness output.",
        )
    status = _clean(result.get("status")).lower()
    evidence = {
        "readiness_status": status,
        "candidates_considered": result.get("candidates_considered", 0),
        "candidates_ready": result.get("candidates_ready", 0),
        "blockers": list(result.get("blockers") or []),
    }
    if status == STATUS_READY and result.get("manual_review_ready") is True:
        return _gate(
            "shadow_promotion_readiness",
            PASS,
            "Evidence is complete enough for manual review only; no automatic promotion authority exists.",
            evidence=evidence,
            action_required="Human review is permitted; automatic score/order promotion remains prohibited.",
        )
    if status in {STATUS_WAITING, STATUS_INSUFFICIENT} and result.get("manual_review_ready") is False:
        return _gate(
            "shadow_promotion_readiness",
            WAITING,
            "Shadow evidence is not yet complete enough for manual promotion review.",
            evidence=evidence,
            action_required="Wait for all required cells, distinct events and quality checks to clear.",
        )
    return _gate(
        "shadow_promotion_readiness",
        FAILED,
        "Shadow readiness returned an unexpected state.",
        evidence=evidence,
        action_required="Inspect the evaluator contract and keep promotion disabled.",
    )


def evaluate_gate_matrix(
    *,
    snapshot: Mapping[str, Any],
    conn: sqlite3.Connection,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    environment = dict(env or {})
    last_result = _component_last_result(snapshot)

    gates: list[dict[str, Any]] = []
    gates.append(_phase5_runtime_gate(snapshot))
    gates.append(
        _macro_initial_actual_gate(
            conn,
            gate_id="bls_initial_actual",
            source_id="us_bls_release_calendar",
            expected_metrics=BLS_EXPECTED_METRICS,
            provider_rights={BLS_PROVIDER_ID: BLS_DATA_RIGHTS},
            revision_labels={BLS_PROVIDER_ID: "initial_api_capture"},
            capture_key="macro_actual_capture",
            last_result=last_result,
            waiting_summary="No complete real BLS release-time initial actual is stored yet.",
            waiting_action="Keep Phase 5 running through a supported BLS release window.",
        )
    )
    gates.append(
        _macro_initial_actual_gate(
            conn,
            gate_id="bea_release_time_actual",
            source_id="us_bea_release_schedule",
            expected_metrics=BEA_EXPECTED_METRICS,
            provider_rights={
                BEA_PROVIDER_ID: BEA_DATA_RIGHTS,
                BEA_NEWS_PROVIDER_ID: BEA_NEWS_DATA_RIGHTS,
            },
            revision_labels={
                BEA_PROVIDER_ID: "initial_api_capture",
                BEA_NEWS_PROVIDER_ID: "initial_news_release_capture",
            },
            capture_key="bea_actual_capture",
            last_result=last_result,
            waiting_summary="No complete real BEA release-time initial actual is stored yet.",
            waiting_action="Keep Phase 5 running through the next Personal Income and Outlays release window.",
        )
    )
    gates.append(_consensus_gate(conn, last_result=last_result, env=environment))
    reference_gate, reference_rows = _us_index_reference_gate(
        conn, last_result=last_result, env=environment
    )
    gates.append(reference_gate)
    gates.append(_reference_quality_gate(reference_rows))
    gates.append(_event_response_gate(conn, last_result))
    gates.append(_sensitivity_gate(conn, last_result))
    gates.append(_shadow_readiness_gate(conn))

    counts = {status: sum(1 for gate in gates if gate["status"] == status) for status in STATUS_PRIORITY}
    overall = max((gate["status"] for gate in gates), key=lambda status: STATUS_PRIORITY[status])
    return {
        "ok": overall != FAILED,
        "overall_status": overall,
        "external_network_requests": 0,
        "credential_values_exposed": False,
        "safety": {
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "automatic_promotion": False,
            "missing_values_coerced_to_zero": False,
        },
        "summary": counts,
        "gates": gates,
    }


def run_gate_matrix(
    *,
    path: Path | str = DB_PATH,
    port: int | None = None,
    timeout_seconds: float = 2.5,
) -> tuple[dict[str, Any], int]:
    load_dotenv()
    settings = Settings()
    service_port = int(port if port is not None else settings.service_port)
    try:
        snapshot = fetch_runtime_snapshot(port=service_port, timeout_seconds=timeout_seconds)
    except Exception as exc:
        result = {
            "ok": False,
            "overall_status": FAILED,
            "external_network_requests": 0,
            "credential_values_exposed": False,
            "summary": {PASS: 0, WAITING: 0, BLOCKED: 0, FAILED: 1},
            "gates": [
                _gate(
                    "phase5_runtime",
                    FAILED,
                    "Local Phase 5 runtime snapshot is unavailable or invalid.",
                    evidence={"error": f"{type(exc).__name__}: {exc}"[:240]},
                    action_required="Restore the local runtime before evaluating the matrix.",
                )
            ],
        }
        return result, 2

    db_path = Path(path)
    if not db_path.exists():
        result = {
            "ok": False,
            "overall_status": FAILED,
            "external_network_requests": 0,
            "credential_values_exposed": False,
            "summary": {PASS: 0, WAITING: 0, BLOCKED: 0, FAILED: 1},
            "gates": [
                _gate(
                    "database",
                    FAILED,
                    "Phase 5 SQLite database is missing.",
                    evidence={"path": str(db_path)},
                    action_required="Restore the expected local PAPER research database.",
                )
            ],
        }
        return result, 2

    try:
        conn = sqlite3.connect(
            f"file:{db_path.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=10,
        )
        conn.row_factory = sqlite3.Row
        result = evaluate_gate_matrix(snapshot=snapshot, conn=conn, env=os.environ)
    except Exception as exc:
        result = {
            "ok": False,
            "overall_status": FAILED,
            "external_network_requests": 0,
            "credential_values_exposed": False,
            "summary": {PASS: 0, WAITING: 0, BLOCKED: 0, FAILED: 1},
            "gates": [
                _gate(
                    "matrix_evaluation",
                    FAILED,
                    "Phase 5 gate matrix evaluation failed closed.",
                    evidence={"error": f"{type(exc).__name__}: {exc}"[:240]},
                    action_required="Inspect the read-only evaluator before relying on gate state.",
                )
            ],
        }
        return result, 2
    finally:
        if "conn" in locals():
            conn.close()

    # WAITING/BLOCKED are expected observable states, not process failures.
    return result, 0 if result.get("overall_status") != FAILED else 2


def main() -> int:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Read-only Phase 5 PASS/WAITING/BLOCKED/FAILED gate matrix")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--port", type=int, default=int(settings.service_port))
    parser.add_argument("--timeout", type=float, default=2.5)
    args = parser.parse_args()
    result, code = run_gate_matrix(path=Path(args.db), port=args.port, timeout_seconds=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
