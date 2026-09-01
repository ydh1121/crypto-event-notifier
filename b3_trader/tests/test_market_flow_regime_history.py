from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.market_flow_family_dedup import MarketFlowFamilyDedupStore
from b3_trader.market_flow_regime_confidence import MarketFlowRegimeConfidenceStore
from b3_trader.market_flow_regime_history import (
    HISTORY_BUCKET_SECONDS,
    HISTORY_RETENTION_SECONDS,
    MarketFlowRegimeHistoryStore,
)

BASE = 1_800_000_000.0


def _prepare(path: Path) -> None:
    MarketFlowRegimeConfidenceStore(path).close()
    MarketFlowFamilyDedupStore(path).close()


def _write_current(
    path: Path,
    *,
    confidence: float = 35.0,
    representative_window: str = "1m",
    received_at: float = BASE + 10.0,
) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("DELETE FROM research_market_flow_regime_confidence_mx")
        conn.execute("DELETE FROM research_market_flow_family_dedup_mx")
        conn.execute(
            """INSERT INTO research_market_flow_regime_confidence_mx(
                   market,signal_window_label,signal_evidence_label,regime_label,horizon_label,
                   reliability_status,promotion_gate_status,
                   bithumb_sample_count,upbit_sample_count,pooled_sample_count,pooled_wilson_lower_pct,
                   base_sample_maturity_pct,directional_support_pct,
                   oos_bithumb_sample_count,oos_upbit_sample_count,oos_pooled_sample_count,
                   oos_pooled_wilson_lower_pct,oos_sample_maturity_pct,oos_directional_support_pct,
                   cross_exchange_direction_consistent,base_promotion_ready,final_candidate_ready,
                   evidence_confidence_pct,confidence_band,family_aggregation_blocked,
                   probability_interpretation,source,received_at,feature_version,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "KRW-ETH","1m","passive_sell_absorption_candidate","distribution_candidate","15m",
                "directional_watch",None,
                40,35,75,55.0,70.0,55.0,
                0,0,0,None,0.0,0.0,
                1,0,0,confidence,"directional_watch",1,0,
                "market_flow_reliability+market_flow_promotion_gate",received_at,1,1,
            ),
        )
        conn.execute(
            """INSERT INTO research_market_flow_family_dedup_mx(
                   market,regime_label,horizon_label,family_key,member_count,
                   representative_signal_window_label,representative_signal_evidence_label,
                   representative_confidence_pct,representative_confidence_band,
                   representative_pooled_sample_count,
                   representative_cross_exchange_direction_consistent,
                   representative_base_promotion_ready,representative_final_candidate_ready,
                   suppressed_member_count,suppressed_windows_json,
                   raw_confidence_sum_pct,effective_family_confidence_pct,inflation_avoided_pct,
                   correlation_policy,aggregation_method,empirical_correlation_estimated,
                   probability_interpretation,received_at,source,feature_version,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "KRW-ETH","distribution_candidate","15m","KRW-ETH|distribution_candidate|15m",2,
                representative_window,"passive_sell_absorption_candidate",
                confidence,"directional_watch",75,1,0,0,1,'["5m"]',
                confidence + 3.0,confidence,3.0,
                "same_market+same_regime+same_horizon+nested_signal_windows_conservative_full_suppression_v1",
                "representative_only_full_suppression",0,0,received_at,
                "market_flow_regime_confidence",1,1,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_same_bucket_recompute_upserts_instead_of_appending(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _write_current(path,confidence=35.0,received_at=BASE + 10.0)
    store = MarketFlowRegimeHistoryStore(path)
    try:
        first = store.capture(now=BASE + 100.0)
        assert first["confidence_rows_written"] == 1
        assert first["family_rows_written"] == 1

        _write_current(path,confidence=42.0,received_at=BASE + 200.0)
        second = store.capture(now=BASE + 200.0)
        assert second["snapshot_ts"] == first["snapshot_ts"]

        confidence_rows = store.conn.execute(
            "SELECT snapshot_ts,evidence_confidence_pct FROM research_market_flow_regime_confidence_history_mx"
        ).fetchall()
        family_rows = store.conn.execute(
            "SELECT snapshot_ts,effective_family_confidence_pct FROM research_market_flow_family_history_mx"
        ).fetchall()
        assert len(confidence_rows) == 1
        assert len(family_rows) == 1
        assert float(confidence_rows[0]["evidence_confidence_pct"]) == 42.0
        assert float(family_rows[0]["effective_family_confidence_pct"]) == 42.0
    finally:
        store.close()


def test_next_bucket_preserves_representative_change(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _write_current(path,confidence=35.0,representative_window="1m",received_at=BASE + 10.0)
    store = MarketFlowRegimeHistoryStore(path)
    try:
        store.capture(now=BASE + 100.0)
        _write_current(
            path,
            confidence=48.0,
            representative_window="5m",
            received_at=BASE + HISTORY_BUCKET_SECONDS + 10.0,
        )
        store.capture(now=BASE + HISTORY_BUCKET_SECONDS + 100.0)
        rows = store.conn.execute(
            """SELECT snapshot_ts,representative_signal_window_label,effective_family_confidence_pct
               FROM research_market_flow_family_history_mx ORDER BY snapshot_ts"""
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["representative_signal_window_label"] == "1m"
        assert rows[1]["representative_signal_window_label"] == "5m"
        assert float(rows[1]["effective_family_confidence_pct"]) == 48.0
    finally:
        store.close()


def test_retention_prunes_history_older_than_90_days(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _write_current(path,confidence=30.0,received_at=BASE)
    store = MarketFlowRegimeHistoryStore(path)
    try:
        store.capture(now=BASE)
        later = BASE + HISTORY_RETENTION_SECONDS + HISTORY_BUCKET_SECONDS
        _write_current(path,confidence=31.0,received_at=later)
        result = store.capture(now=later)
        assert result["confidence_rows_pruned"] >= 1
        assert result["family_rows_pruned"] >= 1
        audit = store.audit()
        assert audit["retention_contract_violations"] == 0
        assert audit["confidence_bucket_violations"] == 0
        assert audit["family_bucket_violations"] == 0
    finally:
        store.close()


def test_history_contract_is_shadow_only_and_not_probability(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _write_current(path)
    store = MarketFlowRegimeHistoryStore(path)
    try:
        store.capture(now=BASE + 100.0)
        audit = store.audit()
        assert audit["ok"] is True
        assert audit["confidence_row_count"] == 1
        assert audit["family_row_count"] == 1
        assert audit["probability_contract_violations"] == 0
        assert audit["paper_only"] is True
        assert audit["shadow_only"] is True
        assert audit["score_wired"] is False
        assert audit["can_place_orders"] is False
        assert audit["can_modify_strategy"] is False
        assert audit["raw_cloud_projection"] is False
    finally:
        store.close()


def test_legacy_history_oos_rows_backfill_gate_started_without_deleting_history(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    store = MarketFlowRegimeHistoryStore(path)
    try:
        store.conn.execute(
            """INSERT INTO research_market_flow_regime_confidence_history_mx(
                   snapshot_ts,market,signal_window_label,signal_evidence_label,regime_label,horizon_label,
                   reliability_status,promotion_gate_status,base_gate_started,
                   evidence_confidence_pct,confidence_band,source_received_at,recorded_at,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                BASE,"KRW-ETH","1m","passive_sell_absorption_candidate","distribution_candidate","15m",
                "mixed_cross_exchange","oos_mixed",0,55.0,"oos_mixed",BASE,BASE,1,
            ),
        )
        store.conn.execute(
            """INSERT INTO research_market_flow_family_history_mx(
                   snapshot_ts,market,regime_label,horizon_label,family_key,member_count,
                   representative_signal_window_label,representative_signal_evidence_label,
                   representative_confidence_pct,representative_confidence_band,
                   representative_base_gate_started,raw_confidence_sum_pct,
                   effective_family_confidence_pct,inflation_avoided_pct,
                   source_received_at,recorded_at,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                BASE,"KRW-ETH","distribution_candidate","15m","KRW-ETH|distribution_candidate|15m",1,
                "1m","passive_sell_absorption_candidate",55.0,"oos_mixed",0,55.0,55.0,0.0,BASE,BASE,1,
            ),
        )
        store.conn.commit()
    finally:
        store.close()

    migrated = MarketFlowRegimeHistoryStore(path)
    try:
        confidence = migrated.conn.execute(
            "SELECT base_gate_started,schema_version FROM research_market_flow_regime_confidence_history_mx"
        ).fetchone()
        family = migrated.conn.execute(
            "SELECT representative_base_gate_started,schema_version FROM research_market_flow_family_history_mx"
        ).fetchone()
        assert int(confidence["base_gate_started"]) == 1
        assert int(confidence["schema_version"]) == 2
        assert int(family["representative_base_gate_started"]) == 1
        assert int(family["schema_version"]) == 2
        audit = migrated.audit()
        assert audit["ok"] is True
        assert audit["base_gate_semantics_violations"] == 0
        assert audit["confidence_row_count"] == 1
        assert audit["family_row_count"] == 1
    finally:
        migrated.close()
