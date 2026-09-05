from __future__ import annotations

import json
import sqlite3

from b3_trader.intelligence_event_response import (
    DATA_RIGHTS as EVENT_RESPONSE_DATA_RIGHTS,
    HORIZONS,
    PROVIDER_ID as EVENT_RESPONSE_PROVIDER_ID,
    IntelligenceEventResponseCollector,
)
from b3_trader.intelligence_event_response_us_sensitivity import (
    IntelligenceEventResponseUsSensitivityStore,
)
from b3_trader.intelligence_shadow_promotion_readiness import (
    EXPECTED_REFERENCE_DATA_RIGHTS,
    EXPECTED_REFERENCE_PROVIDER_ID,
    REQUIRED_REFERENCE_SOURCES,
    STATUS_INSUFFICIENT,
    STATUS_READY,
    STATUS_WAITING,
    ShadowPromotionReadinessEvaluator,
)
from b3_trader.intelligence_us_market_reference import SERIES_BY_SOURCE


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _seed(
    conn: sqlite3.Connection,
    *,
    event_count: int,
    horizons: tuple[str, ...],
    sources: tuple[str, ...],
    latency_class: str = "realtime",
    session_state: str = "regular",
) -> None:
    IntelligenceEventResponseCollector(conn)
    store = IntelligenceEventResponseUsSensitivityStore(conn)
    horizon_seconds = dict(HORIZONS)
    attrs = json.dumps(
        {
            "score_authority": False,
            "point_in_time_backfill_used": False,
            "missing_values_coerced_to_zero": False,
        },
        sort_keys=True,
    )
    base = 1_780_000_000.0
    for index in range(event_count):
        event_id = f"event-{index:03d}"
        event_ts = base + index * 100_000.0
        for h_index, horizon in enumerate(horizons):
            seconds = float(horizon_seconds[horizon])
            target_ts = event_ts + seconds
            coin_return = (index - 9.5) * 0.017 + h_index * 0.003
            conn.execute(
                """INSERT INTO research_intelligence_event_responses(
                    event_id,event_type,source_id,exchange,market,horizon_label,horizon_seconds,
                    event_ts,baseline_trade_ts,baseline_price,target_ts,target_trade_ts,target_price,
                    return_pct,provider_id,data_rights,observation_tolerance_seconds,captured_at,
                    attributes_json,schema_version
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id,
                    "US_CPI",
                    "us_bls_release_calendar",
                    "bithumb",
                    "KRW-BTC",
                    horizon,
                    seconds,
                    event_ts,
                    event_ts - 1.0,
                    100.0,
                    target_ts,
                    target_ts + 1.0,
                    100.0 * (1.0 + coin_return / 100.0),
                    coin_return,
                    EVENT_RESPONSE_PROVIDER_ID,
                    EVENT_RESPONSE_DATA_RIGHTS,
                    120.0,
                    target_ts + 2.0,
                    attrs,
                    1,
                ),
            )
            response_id = f"response-{event_id}-{horizon}"
            for s_index, source in enumerate(sources):
                reference_return = (index - 9.5) * (0.009 + s_index * 0.001) + h_index * 0.002
                start_value = 1000.0 + s_index * 100.0 + index
                end_value = start_value * (1.0 + reference_return / 100.0)
                pair_id = f"pair-{event_id}-{horizon}-{source}"
                conn.execute(
                    """INSERT INTO research_intelligence_event_response_us_pairs(
                        pair_id,response_id,event_id,event_type,event_source_id,exchange,market,
                        horizon_label,horizon_seconds,event_ts,target_ts,coin_provider_id,
                        coin_return_pct,reference_source_id,reference_series,reference_provider_id,
                        reference_return_pct,reference_start_at,reference_end_at,reference_start_value,
                        reference_end_value,start_skew_seconds,end_skew_seconds,start_session_state,
                        end_session_state,start_latency_class,end_latency_class,start_delayed_seconds,
                        end_delayed_seconds,start_data_rights,end_data_rights,pair_version,first_seen_at,
                        updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        pair_id,
                        response_id,
                        event_id,
                        "US_CPI",
                        "us_bls_release_calendar",
                        "bithumb",
                        "KRW-BTC",
                        horizon,
                        seconds,
                        event_ts,
                        target_ts,
                        EVENT_RESPONSE_PROVIDER_ID,
                        coin_return,
                        source,
                        SERIES_BY_SOURCE[source],
                        EXPECTED_REFERENCE_PROVIDER_ID,
                        reference_return,
                        event_ts + 30.0,
                        target_ts + 30.0,
                        start_value,
                        end_value,
                        30.0,
                        30.0,
                        session_state,
                        session_state,
                        latency_class,
                        latency_class,
                        0.0,
                        0.0,
                        EXPECTED_REFERENCE_DATA_RIGHTS,
                        EXPECTED_REFERENCE_DATA_RIGHTS,
                        1,
                        target_ts + 40.0,
                        target_ts + 40.0,
                    ),
                )
    conn.commit()
    store.refresh_sensitivity(now=base + event_count * 100_000.0 + 100_000.0)


def test_empty_evidence_waits_without_granting_authority() -> None:
    conn = _conn()
    IntelligenceEventResponseUsSensitivityStore(conn)
    result = ShadowPromotionReadinessEvaluator(conn).run()
    assert result["ok"] is True
    assert result["status"] == STATUS_WAITING
    assert result["manual_review_ready"] is False
    assert result["promotion_eligible"] is False
    assert result["automatic_promotion"] is False
    assert result["score_authority"] is False
    assert result["score_mutation"] is False
    assert result["can_place_orders"] is False
    assert result["missing_values_coerced_to_zero"] is False


def test_partial_evidence_is_insufficient() -> None:
    conn = _conn()
    _seed(
        conn,
        event_count=5,
        horizons=("15m",),
        sources=(REQUIRED_REFERENCE_SOURCES[0],),
    )
    result = ShadowPromotionReadinessEvaluator(conn).run()
    assert result["status"] == STATUS_INSUFFICIENT
    assert result["manual_review_ready"] is False
    assert "required_cells_missing" in result["blockers"]
    assert "insufficient_samples_per_cell" in result["blockers"]


def test_complete_counts_with_unknown_quality_metadata_still_fail_closed() -> None:
    conn = _conn()
    _seed(
        conn,
        event_count=20,
        horizons=tuple(label for label, _ in HORIZONS),
        sources=REQUIRED_REFERENCE_SOURCES,
        latency_class="unknown",
        session_state="unknown",
    )
    result = ShadowPromotionReadinessEvaluator(conn).run()
    assert result["status"] == STATUS_INSUFFICIENT
    assert result["manual_review_ready"] is False
    assert "reference_quality_metadata_unresolved" in result["blockers"]


def test_complete_observed_evidence_only_marks_manual_review_ready() -> None:
    conn = _conn()
    _seed(
        conn,
        event_count=20,
        horizons=tuple(label for label, _ in HORIZONS),
        sources=REQUIRED_REFERENCE_SOURCES,
    )
    result = ShadowPromotionReadinessEvaluator(conn).run()
    assert result["status"] == STATUS_READY
    assert result["manual_review_ready"] is True
    assert result["candidates_ready"] == 1
    assert result["required_cells_per_candidate"] == 12
    assert result["promotion_eligible"] is False
    assert result["automatic_promotion"] is False
    assert result["score_authority"] is False
    assert result["score_mutation"] is False
    assert result["can_place_orders"] is False
    assert result["missing_values_coerced_to_zero"] is False


def test_bad_coin_data_rights_blocks_manual_review() -> None:
    conn = _conn()
    _seed(
        conn,
        event_count=20,
        horizons=tuple(label for label, _ in HORIZONS),
        sources=REQUIRED_REFERENCE_SOURCES,
    )
    conn.execute(
        "UPDATE research_intelligence_event_responses SET data_rights='unreviewed' WHERE event_id='event-000'"
    )
    conn.commit()
    result = ShadowPromotionReadinessEvaluator(conn).run()
    assert result["status"] == STATUS_INSUFFICIENT
    assert result["manual_review_ready"] is False
    assert "coin_data_rights_mismatch" in result["blockers"]
