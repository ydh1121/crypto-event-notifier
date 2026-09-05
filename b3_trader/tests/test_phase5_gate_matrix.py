from __future__ import annotations

import json
import sqlite3

from b3_trader.intelligence_bls_actual import BLS_AUTHORITY, BLS_DATA_RIGHTS, BLS_PROVIDER_ID, BLS_PUBLIC_API_URL
from b3_trader.intelligence_event_response import (
    DATA_RIGHTS as EVENT_RESPONSE_DATA_RIGHTS,
    PROVIDER_ID as EVENT_RESPONSE_PROVIDER_ID,
    IntelligenceEventResponseCollector,
)
from b3_trader.intelligence_event_response_us_sensitivity import IntelligenceEventResponseUsSensitivityStore
from b3_trader.intelligence_macro_release_values import MacroReleaseValueStore, normalize_macro_release_value
from b3_trader.intelligence_us_index_intraday import (
    TWELVE_DATA_DATA_RIGHTS,
    TWELVE_DATA_PROVIDER_ID,
    TWELVE_DATA_TIME_SERIES_URL,
)
from b3_trader.intelligence_us_market_reference import (
    SERIES_BY_SOURCE,
    UsMarketReferenceStore,
    normalize_us_market_reference_observation,
)
from b3_trader.phase5_gate_matrix import BLOCKED, FAILED, PASS, WAITING, evaluate_gate_matrix
from b3_trader.phase5_runtime_check import EXPECTED_SOURCE_IDS


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE research_intelligence_events(
            event_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            scheduled_at REAL NOT NULL
        )"""
    )
    MacroReleaseValueStore(conn)
    IntelligenceEventResponseCollector(conn)
    IntelligenceEventResponseUsSensitivityStore(conn)
    UsMarketReferenceStore(conn)
    return conn


def _snapshot(*, unsafe: bool = False) -> dict[str, object]:
    last_result = {
        "paper_only": True,
        "can_place_orders": False,
        "score_mutation": False,
        "network_enabled": True,
        "requested_sources": sorted(EXPECTED_SOURCE_IDS),
        "source_failures": 0,
        "events_received": 67,
        "events_inserted": 0,
        "events_updated": 67,
        "status": "ok",
        "macro_actual_capture": {"status": "ok"},
        "bea_actual_capture": {"status": "ok"},
        "consensus_capture": {"status": "credential_missing", "credential_status": "missing"},
        "event_response_capture": {"status": "ok"},
        "us_market_reference_capture": {"status": "credential_missing", "credential_status": "missing"},
        "event_response_us_sensitivity": {"status": "ok"},
    }
    if unsafe:
        last_result["can_place_orders"] = True
    return {
        "paper_only": True,
        "supervisor_running": True,
        "safety": {"can_place_orders": False},
        "components": [
            {
                "name": "phase5-intelligence-ingest",
                "enabled": True,
                "status": "healthy",
                "runs": 3,
                "last_success_at": 1_788_600_000.0,
                "last_result": last_result,
            }
        ],
    }


def _seed_bls_initial(conn: sqlite3.Connection) -> None:
    scheduled = 1_788_500_000.0
    known = scheduled + 600.0
    conn.execute(
        "INSERT INTO research_intelligence_events(event_id,source_id,event_type,scheduled_at) VALUES(?,?,?,?)",
        ("bls-employment-1", "us_bls_release_calendar", "US_EMPLOYMENT", scheduled),
    )
    values = []
    for metric_id, value, unit in (
        ("US_NONFARM_PAYROLL_CHANGE_K", 162.0, "THOUSANDS"),
        ("US_UNEMPLOYMENT_RATE_PCT", 4.1, "PERCENT"),
    ):
        values.append(
            normalize_macro_release_value(
                event_id="bls-employment-1",
                event_type="US_EMPLOYMENT",
                metric_id=metric_id,
                value_role="actual",
                numeric_value=value,
                unit=unit,
                reference_period="2026-08",
                provider_id=BLS_PROVIDER_ID,
                provider_url=BLS_PUBLIC_API_URL,
                authority=BLS_AUTHORITY,
                data_rights=BLS_DATA_RIGHTS,
                known_at=known,
                received_at=known,
                revision_no=0,
                revision_label="initial_api_capture",
                attributes={
                    "score_authority": False,
                    "capture_policy": "first_complete_official_api_observation_within_release_window",
                },
            )
        )
    MacroReleaseValueStore(conn).ingest(values, seen_at=known + 1.0)
    conn.commit()


def _status_map(result: dict[str, object]) -> dict[str, str]:
    return {str(gate["id"]): str(gate["status"]) for gate in result["gates"]}


def test_current_like_matrix_distinguishes_blocked_from_waiting() -> None:
    conn = _conn()
    _seed_bls_initial(conn)

    result = evaluate_gate_matrix(snapshot=_snapshot(), conn=conn, env={})
    statuses = _status_map(result)

    assert result["ok"] is True
    assert result["overall_status"] == BLOCKED
    assert result["external_network_requests"] == 0
    assert result["credential_values_exposed"] is False
    assert statuses == {
        "phase5_runtime": PASS,
        "bls_initial_actual": PASS,
        "bea_release_time_actual": WAITING,
        "consensus_provider": BLOCKED,
        "us_index_reference": BLOCKED,
        "us_reference_quality": WAITING,
        "event_response_samples": WAITING,
        "us_market_sensitivity": WAITING,
        "shadow_promotion_readiness": WAITING,
    }


def test_configured_external_providers_without_evidence_are_waiting() -> None:
    conn = _conn()
    _seed_bls_initial(conn)
    result = evaluate_gate_matrix(
        snapshot=_snapshot(),
        conn=conn,
        env={
            "TRADING_ECONOMICS_API_KEY": "te-secret-fixture",
            "TWELVE_DATA_API_KEY": "td-secret-fixture",
        },
    )
    statuses = _status_map(result)

    assert result["overall_status"] == WAITING
    assert statuses["consensus_provider"] == WAITING
    assert statuses["us_index_reference"] == WAITING
    payload = json.dumps(result, sort_keys=True)
    assert "te-secret-fixture" not in payload
    assert "td-secret-fixture" not in payload


def test_unresolved_reference_quality_is_blocked_even_when_three_series_exist() -> None:
    conn = _conn()
    _seed_bls_initial(conn)
    store = UsMarketReferenceStore(conn)
    observations = []
    for index, source_id in enumerate(SERIES_BY_SOURCE):
        observations.append(
            normalize_us_market_reference_observation(
                source_id=source_id,
                observed_at=1_788_600_000.0 + index * 60.0,
                received_at=1_788_600_020.0 + index * 60.0,
                value=1000.0 + index * 100.0,
                provider_id=TWELVE_DATA_PROVIDER_ID,
                provider_url=TWELVE_DATA_TIME_SERIES_URL,
                data_rights=TWELVE_DATA_DATA_RIGHTS,
                session_state="unknown",
                latency_class="unknown",
                attributes={
                    "score_authority": False,
                    "promotion_eligible": False,
                    "missing_values_coerced_to_zero": False,
                },
            )
        )
    store.ingest(observations, seen_at=1_788_601_000.0)

    result = evaluate_gate_matrix(
        snapshot=_snapshot(),
        conn=conn,
        env={
            "TRADING_ECONOMICS_API_KEY": "te-ready",
            "TWELVE_DATA_API_KEY": "td-ready",
        },
    )
    statuses = _status_map(result)

    assert statuses["us_index_reference"] == PASS
    assert statuses["us_reference_quality"] == BLOCKED
    assert result["overall_status"] == BLOCKED


def test_runtime_safety_violation_has_highest_priority() -> None:
    conn = _conn()
    _seed_bls_initial(conn)
    result = evaluate_gate_matrix(snapshot=_snapshot(unsafe=True), conn=conn, env={})
    statuses = _status_map(result)

    assert result["ok"] is False
    assert result["overall_status"] == FAILED
    assert statuses["phase5_runtime"] == FAILED


def test_invalid_event_response_fails_closed() -> None:
    conn = _conn()
    _seed_bls_initial(conn)
    attrs = json.dumps(
        {
            "score_authority": False,
            "point_in_time_backfill_used": False,
            "missing_values_coerced_to_zero": False,
        },
        sort_keys=True,
    )
    conn.execute(
        """INSERT INTO research_intelligence_event_responses(
            event_id,event_type,source_id,exchange,market,horizon_label,horizon_seconds,
            event_ts,baseline_trade_ts,baseline_price,target_ts,target_trade_ts,target_price,
            return_pct,provider_id,data_rights,observation_tolerance_seconds,captured_at,
            attributes_json,schema_version
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "event-invalid",
            "US_CPI",
            "us_bls_release_calendar",
            "bithumb",
            "KRW-BTC",
            "15m",
            900.0,
            1_788_550_000.0,
            1_788_549_999.0,
            100.0,
            1_788_550_900.0,
            1_788_550_899.0,
            101.0,
            1.0,
            EVENT_RESPONSE_PROVIDER_ID,
            EVENT_RESPONSE_DATA_RIGHTS,
            120.0,
            1_788_551_000.0,
            attrs,
            1,
        ),
    )
    conn.commit()

    result = evaluate_gate_matrix(snapshot=_snapshot(), conn=conn, env={})
    statuses = _status_map(result)

    assert statuses["event_response_samples"] == FAILED
    assert result["overall_status"] == FAILED
