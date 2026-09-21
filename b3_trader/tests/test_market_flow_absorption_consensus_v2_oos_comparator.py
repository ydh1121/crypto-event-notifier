from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.market_flow_absorption_consensus_v2_oos_comparator import (
    REFERENCE_NOTIONAL_KRW,
    MarketFlowAbsorptionConsensusV2OosComparatorStore,
)


def _sources(path: Path, *, v2_forward_activation: float = 500.0) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE research_market_flow_absorption_consensus_v2_forward_control_mx(
            singleton INTEGER PRIMARY KEY,
            activation_ts REAL NOT NULL
        );
        CREATE TABLE research_market_flow_full_cost_notional_sensitivity_mx(
            exchange TEXT NOT NULL,
            market TEXT NOT NULL,
            signal_window_label TEXT NOT NULL,
            signal_feature_ts REAL NOT NULL,
            signal_evidence_label TEXT NOT NULL,
            horizon_label TEXT NOT NULL,
            reaction_end_ts REAL NOT NULL,
            gross_hypothesis_return_pct REAL NOT NULL,
            total_transaction_cost_bps REAL,
            full_cost_adjusted_return_pct REAL,
            reference_notional_krw REAL NOT NULL,
            full_cost_ready INTEGER NOT NULL
        );
        CREATE TABLE research_market_flow_absorption_consensus_v2_event_mx(
            market TEXT NOT NULL,
            regime_label TEXT NOT NULL,
            horizon_label TEXT NOT NULL,
            consensus_received_at REAL NOT NULL,
            mean_full_cost_adjusted_return_pct REAL,
            positive_event INTEGER,
            both_exchange_positive INTEGER,
            suppressed_overlap INTEGER NOT NULL,
            cross_exchange_full_cost_ready INTEGER NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO research_market_flow_absorption_consensus_v2_forward_control_mx VALUES(1,?)",
        (v2_forward_activation,),
    )
    conn.commit()
    conn.close()


def _v1_pair(
    path: Path,
    *,
    signal_ts: float,
    reaction_end_ts: float,
    notional: float = REFERENCE_NOTIONAL_KRW,
    bithumb_return: float = 0.20,
    upbit_return: float = 0.10,
) -> None:
    conn = sqlite3.connect(path)
    for exchange, adjusted in (("bithumb", bithumb_return), ("upbit", upbit_return)):
        conn.execute(
            """INSERT INTO research_market_flow_full_cost_notional_sensitivity_mx(
                   exchange,market,signal_window_label,signal_feature_ts,signal_evidence_label,
                   horizon_label,reaction_end_ts,gross_hypothesis_return_pct,
                   total_transaction_cost_bps,full_cost_adjusted_return_pct,
                   reference_notional_krw,full_cost_ready
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)""",
            (
                exchange,
                "KRW-BTC",
                "5m",
                signal_ts,
                "passive_buy_absorption_candidate",
                "15m",
                reaction_end_ts,
                0.30,
                10.0,
                adjusted,
                notional,
            ),
        )
    conn.commit()
    conn.close()


def _v2_event(path: Path, *, received_at: float, adjusted: float = 0.25) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """INSERT INTO research_market_flow_absorption_consensus_v2_event_mx(
               market,regime_label,horizon_label,consensus_received_at,
               mean_full_cost_adjusted_return_pct,positive_event,both_exchange_positive,
               suppressed_overlap,cross_exchange_full_cost_ready
           ) VALUES('KRW-BTC','accumulation_candidate','15m',?,?,?,?,0,1)""",
        (received_at, adjusted, 1 if adjusted > 0 else 0, 1 if adjusted > 0 else 0),
    )
    conn.commit()
    conn.close()


def test_comparator_uses_its_own_forward_activation(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _sources(path)
    _v1_pair(path, signal_ts=900.0, reaction_end_ts=1800.0)
    _v2_event(path, received_at=950.0)

    store = MarketFlowAbsorptionConsensusV2OosComparatorStore(path)
    try:
        first = store.compute(now=1000.0)
        first_audit = store.audit()
    finally:
        store.close()

    assert first["activation_status"] == "activated"
    assert first["activation_ts"] == 1000.0
    assert first["v1_cross_exchange_events"] == 0
    assert first["v2_cross_exchange_events"] == 0
    assert first["v1_750k_ready_members_before_comparator_activation_context"] == 2
    assert first["v2_ready_events_before_comparator_activation_context"] == 1
    assert first_audit["ok"] is True

    _v1_pair(path, signal_ts=1100.0, reaction_end_ts=2000.0)
    _v2_event(path, received_at=1150.0)

    store = MarketFlowAbsorptionConsensusV2OosComparatorStore(path)
    try:
        second = store.compute(now=2100.0)
        rows = [
            dict(row)
            for row in store.conn.execute(
                """SELECT * FROM research_market_flow_absorption_consensus_v2_oos_comparison_mx
                   ORDER BY scope_label"""
            ).fetchall()
        ]
        audit = store.audit()
    finally:
        store.close()

    assert second["activation_status"] == "existing"
    assert second["activation_ts"] == 1000.0
    assert second["v1_cross_exchange_events"] == 1
    assert second["v2_cross_exchange_events"] == 1
    assert second["comparison_rows"] == 2
    assert {row["scope_label"] for row in rows} == {"market", "pooled"}
    assert all(row["v1_event_count"] == 1 for row in rows)
    assert all(row["v2_event_count"] == 1 for row in rows)
    assert all(row["observation_comparable"] == 0 for row in rows)
    assert all(row["winner_selection_enabled"] == 0 for row in rows)
    assert audit["ok"] is True


def test_v1_comparison_is_exact_750k_and_outcome_blind_overlap_clustered(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _sources(path)

    store = MarketFlowAbsorptionConsensusV2OosComparatorStore(path)
    try:
        store.compute(now=1000.0)
    finally:
        store.close()

    _v1_pair(path, signal_ts=1100.0, reaction_end_ts=2000.0)
    _v1_pair(path, signal_ts=1150.0, reaction_end_ts=2050.0)
    _v1_pair(path, signal_ts=1300.0, reaction_end_ts=2200.0, notional=500_000.0)
    _v2_event(path, received_at=1200.0)

    store = MarketFlowAbsorptionConsensusV2OosComparatorStore(path)
    try:
        result = store.compute(now=2300.0)
        market_row = dict(
            store.conn.execute(
                """SELECT * FROM research_market_flow_absorption_consensus_v2_oos_comparison_mx
                   WHERE scope_label='market'"""
            ).fetchone()
        )
        audit = store.audit()
    finally:
        store.close()

    assert result["v1_cross_exchange_events"] == 1
    assert result["v2_cross_exchange_events"] == 1
    assert market_row["reference_notional_krw"] == 750000.0
    assert market_row["v1_event_count"] == 1
    assert audit["notional_mismatch_rows"] == 0
    assert audit["winner_selection_violation_rows"] == 0
    assert audit["ok"] is True
