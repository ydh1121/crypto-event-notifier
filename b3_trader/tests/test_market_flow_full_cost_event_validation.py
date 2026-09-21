from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.market_flow_full_cost_edge import MarketFlowFullCostEdgeStore
from b3_trader.market_flow_full_cost_event_cluster import (
    CLUSTER_POLICY,
    REPRESENTATIVE_POLICY,
    MarketFlowFullCostEventClusterStore,
)
from b3_trader.market_flow_full_cost_event_reliability import MarketFlowFullCostEventReliabilityStore


def _insert_full_cost_row(
    path: Path,
    *,
    exchange: str,
    signal_ts: float,
    end_ts: float,
    adjusted: float,
    window: str = "1m",
    market: str = "KRW-BTC",
    evidence: str = "passive_sell_absorption_candidate",
    ready: bool = True,
) -> None:
    store = MarketFlowFullCostEdgeStore(path)
    try:
        store.conn.execute(
            """INSERT INTO research_market_flow_full_cost_edge_mx(
                   exchange,market,signal_window_label,signal_feature_ts,signal_evidence_label,
                   horizon_label,reaction_end_ts,hypothesis_direction,gross_hypothesis_return_pct,
                   reference_notional_krw,entry_ladder_source_ts,exit_ladder_source_ts,
                   entry_ladder_age_seconds,exit_ladder_age_seconds,entry_spread_bps,exit_spread_bps,
                   roundtrip_spread_cost_bps,entry_slippage_bps,exit_slippage_bps,
                   entry_fee_bps,exit_fee_bps,total_transaction_cost_bps,
                   full_cost_adjusted_return_pct,fee_profile,fee_model_ready,ladder_slippage_ready,
                   full_cost_edge_ready,cost_status,source,received_at,feature_version,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                exchange,market,window,signal_ts,evidence,"15m",end_ts,-1,adjusted + 0.20,
                5000.0,signal_ts - 1.0,end_ts - 1.0,1.0,1.0,1.0,1.0,1.0,
                0.0,0.0,5.0,5.0,20.0,adjusted,"standard",
                1 if ready else 0,1 if ready else 0,1 if ready else 0,
                "full_cost_ready" if ready else "waiting_prior_only_ladder",
                "test",end_ts + 1.0,1,1,
            ),
        )
        store.conn.commit()
    finally:
        store.close()


def test_full_cost_cluster_reduces_overlap_without_performance_selection(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    anchor = 1_800_000_000.0
    end = anchor + 900.0
    _insert_full_cost_row(path,exchange="upbit",signal_ts=anchor,end_ts=end,adjusted=0.10,window="1m")
    _insert_full_cost_row(path,exchange="upbit",signal_ts=anchor + 60,end_ts=end + 60,adjusted=5.00,window="5m")
    _insert_full_cost_row(path,exchange="bithumb",signal_ts=anchor + 30,end_ts=end + 30,adjusted=0.20,window="1m")
    _insert_full_cost_row(path,exchange="upbit",signal_ts=end,end_ts=end + 900,adjusted=0.30,window="1m")
    _insert_full_cost_row(path,exchange="upbit",signal_ts=end + 1800,end_ts=end + 2700,adjusted=9.0,ready=False)

    store = MarketFlowFullCostEventClusterStore(path)
    try:
        result = store.compute(now=1_900_000_000.0)
        audit = store.audit()
    finally:
        store.close()

    assert result["source_full_cost_ready_members"] == 4
    assert result["events_written"] == 2
    assert result["suppressed_overlap_members"] == 1
    assert result["cross_exchange_events"] == 1
    assert audit["ok"] is True
    assert audit["full_cost_source_contract_violations"] == 0

    conn = sqlite3.connect(path)
    try:
        first_event = conn.execute(
            """SELECT event_id,mean_full_cost_adjusted_return_pct
               FROM research_market_flow_full_cost_event_cluster_mx
               ORDER BY event_anchor_signal_ts LIMIT 1"""
        ).fetchone()
        reps = conn.execute(
            """SELECT exchange,signal_feature_ts,full_cost_adjusted_return_pct
               FROM research_market_flow_full_cost_event_cluster_member_mx
               WHERE event_id=? AND representative_for_exchange=1 ORDER BY exchange""",
            (first_event[0],),
        ).fetchall()
    finally:
        conn.close()

    assert reps == [("bithumb", anchor + 30, 0.20), ("upbit", anchor, 0.10)]
    assert abs(first_event[1] - 0.15) < 1e-9


def _insert_cluster_event(path: Path, *, index: int, bithumb_return: float, upbit_return: float) -> None:
    cluster = MarketFlowFullCostEventClusterStore(path)
    cluster.close()
    anchor = 1_810_000_000.0 + index * 1_000.0
    event_id = f"KRW-BTC|distribution_candidate|15m|full-cost|{anchor:.6f}"
    mean_return = (bithumb_return + upbit_return) / 2.0
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO research_market_flow_full_cost_event_cluster_mx(
                   event_id,market,regime_label,horizon_label,event_anchor_signal_ts,event_anchor_end_ts,
                   member_count,representative_count,exchange_count,cross_exchange_confirmed,
                   exchanges_json,signal_windows_json,fee_profiles_json,
                   mean_gross_hypothesis_return_pct,mean_total_transaction_cost_bps,
                   mean_full_cost_adjusted_return_pct,full_cost_adjusted_positive,
                   reference_notional_krw,cluster_policy,representative_policy,
                   independence_claim,pseudo_replication_reduced,source,received_at,feature_version,schema_version
               ) VALUES(?,'KRW-BTC','distribution_candidate','15m',?,?,?,?,1,1,
                        '["bithumb","upbit"]','["1m"]','["bithumb:standard","upbit:standard"]',
                        ?,20.0,?,?,5000,?,?,0,1,'market_flow_full_cost_edge',?,1,1)""",
            (
                event_id,anchor,anchor + 900.0,2,2,mean_return + 0.20,mean_return,
                1 if mean_return > 0 else 0,CLUSTER_POLICY,REPRESENTATIVE_POLICY,anchor + 901.0,
            ),
        )
        for exchange, value in (("bithumb", bithumb_return), ("upbit", upbit_return)):
            conn.execute(
                """INSERT INTO research_market_flow_full_cost_event_cluster_member_mx(
                       event_id,market,regime_label,horizon_label,exchange,signal_window_label,
                       signal_feature_ts,signal_evidence_label,reaction_end_ts,
                       gross_hypothesis_return_pct,total_transaction_cost_bps,
                       full_cost_adjusted_return_pct,reference_notional_krw,fee_profile,
                       representative_for_exchange,suppressed_overlap_member,
                       cluster_policy,representative_policy,source,received_at,feature_version,schema_version
                   ) VALUES(?,'KRW-BTC','distribution_candidate','15m',?,'1m',?,
                            'passive_sell_absorption_candidate',?,?,20.0,?,5000,'standard',1,0,?,?,
                            'market_flow_full_cost_edge',?,1,1)""",
                (event_id,exchange,anchor,anchor + 900.0,value + 0.20,value,CLUSTER_POLICY,REPRESENTATIVE_POLICY,anchor + 901.0),
            )
        conn.commit()
    finally:
        conn.close()


def test_full_cost_reliability_fails_closed_without_cross_exchange(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    anchor = 1_820_000_000.0
    for index in range(30):
        signal = anchor + index * 1_000.0
        _insert_full_cost_row(path,exchange="upbit",signal_ts=signal,end_ts=signal + 900.0,adjusted=0.20)

    cluster = MarketFlowFullCostEventClusterStore(path)
    try:
        cluster.compute(now=1_900_000_000.0)
    finally:
        cluster.close()

    reliability = MarketFlowFullCostEventReliabilityStore(path)
    try:
        result = reliability.compute(now=1_900_000_000.0)
        audit = reliability.audit()
    finally:
        reliability.close()

    assert result["source_event_count"] == 30
    assert result["observation_ready_rows"] == 0
    row = audit["rows"][0]
    assert row["event_hit_rate_pct"] == 100.0
    assert row["cross_exchange_event_count"] == 0
    assert row["observation_ready"] == 0
    assert row["promotion_ready"] == 0
    assert row["status"] == "collecting_full_cost"


def test_full_cost_reliability_promotion_requires_cross_exchange_wilson_support(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    for index in range(60):
        _insert_cluster_event(path,index=index,bithumb_return=0.10,upbit_return=0.12)

    store = MarketFlowFullCostEventReliabilityStore(path)
    try:
        result = store.compute(now=1_900_000_000.0)
        audit = store.audit()
    finally:
        store.close()

    assert result["promotion_ready_rows"] == 1
    row = audit["rows"][0]
    assert row["event_count"] == 60
    assert row["cross_exchange_event_count"] == 60
    assert row["event_wilson_lower_pct"] > 50.0
    assert row["cross_exchange_positive_wilson_lower_pct"] > 50.0
    assert row["promotion_ready"] == 1
    assert row["status"] == "validated_full_cost_candidate"
    assert audit["promotion_contract_violations"] == 0
