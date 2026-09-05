from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.market_flow_orderbook_stream_store import MarketFlowOrderbookStreamStore
from b3_trader.market_flow_reaction import MarketFlowReactionStore
from b3_trader.market_flow_reliability import MarketFlowReliabilityStore


def _prepare(path: Path) -> None:
    MarketFlowReactionStore(path).close()
    MarketFlowOrderbookStreamStore(path).close()


def _insert_reaction(path: Path, signal_ts: float, end_ts: float) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO research_market_flow_reaction_mx(
                   exchange,market,signal_window_label,signal_feature_ts,signal_evidence_label,
                   signal_price,signal_delta_quote,flow_direction,hypothesis_direction,
                   horizon_label,horizon_seconds,reaction_start_ts,reaction_end_ts,
                   reaction_source_timeframe,reaction_source_interval_seconds,data_ready,status,
                   endpoint_candle_ts,endpoint_price,future_return_pct,flow_followthrough_return_pct,
                   hypothesis_directional_return_pct,source,received_at,feature_version,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "bithumb","KRW-BTC","1m",signal_ts,
                "passive_sell_absorption_candidate",100.0,1_000_000.0,1,-1,
                "15m",900.0,signal_ts,end_ts,"1m",60.0,1,"ready",
                end_ts - 60.0,99.9,-0.10,0.10,0.10,
                "price_flow_divergence+rest_ohlcv",end_ts + 1.0,1,1,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_book(path: Path, feature_ts: float, spread_bps: float) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO research_market_orderbook_window_feature_mx(
                   exchange,market,window_label,window_seconds,feature_ts,window_start_ts,window_end_ts,
                   snapshot_count,spread_bps_avg,spread_bps_max,bid_depth_quote_avg,ask_depth_quote_avg,
                   imbalance_pct_avg,bid_refill_quote,bid_depletion_quote,ask_refill_quote,ask_depletion_quote,
                   bid_same_best_pairs,ask_same_best_pairs,continuity_complete,received_at,feature_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "bithumb","KRW-BTC","1m",60.0,feature_ts,feature_ts - 60.0,feature_ts,
                60,spread_bps,spread_bps,10_000_000.0,10_000_000.0,0.0,
                0.0,0.0,0.0,0.0,10,10,1,feature_ts + 1.0,1,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_reliability_compute_auto_runs_cost_cluster_and_event_reliability(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    signal_ts = 1_800_000_000.0
    end_ts = signal_ts + 900.0
    stamp = 1_900_000_000.0
    _insert_reaction(path, signal_ts, end_ts)
    _insert_book(path, signal_ts, 2.0)
    _insert_book(path, end_ts, 2.0)

    store = MarketFlowReliabilityStore(path)
    try:
        result = store.compute(now=stamp)
    finally:
        store.close()

    assert result["ok"] is True
    assert result["cost_edge"]["ok"] is True
    assert result["cost_edge"]["reaction_rows"] == 1
    assert result["cost_edge"]["orderbook_friction_ready_rows"] == 1
    assert result["full_cost_edge"]["ok"] is True
    assert result["full_cost_edge"]["source_rows"] == 1
    assert result["full_cost_edge"]["full_cost_ready_rows"] == 0
    assert result["full_cost_notional_sensitivity"]["ok"] is True
    assert result["full_cost_notional_sensitivity"]["source_full_cost_rows"] == 0
    assert result["event_cluster"]["ok"] is True
    assert result["event_cluster"]["events_written"] == 1
    assert result["event_reliability"]["ok"] is True
    assert result["event_reliability"]["groups_written"] == 1
    assert result["event_reliability"]["promotion_ready_rows"] == 0
    assert result["full_cost_event_cluster"]["ok"] is True
    assert result["full_cost_event_cluster"]["events_written"] == 0
    assert result["full_cost_event_reliability"]["ok"] is True
    assert result["full_cost_event_reliability"]["groups_written"] == 0
    assert result["post_reliability_pipeline"]["order"] == [
        "cost_edge","full_cost_edge","full_cost_notional_sensitivity",
        "event_cluster","event_reliability",
        "full_cost_event_cluster","full_cost_event_reliability",
        "market_flow_absorption_consensus_v2_oos_comparator"
    ]
    assert result["post_reliability_pipeline"]["network_fetches"] is False
    assert result["post_reliability_pipeline"]["spread_only_event_pipeline"] is True
    assert result["post_reliability_pipeline"]["forward_only_full_transaction_cost_observation"] is True
    assert result["post_reliability_pipeline"]["paper_notional_sensitivity_observation"] is True
    assert result["post_reliability_pipeline"]["full_cost_event_validation_pipeline"] is True
    assert result["post_reliability_pipeline"]["full_cost_event_promotion_wired_to_score"] is False
    assert result["post_reliability_pipeline"]["event_promotion_wired_to_score"] is False
    assert result["post_reliability_pipeline"]["can_place_orders"] is False

    conn = sqlite3.connect(path)
    try:
        timestamps = [
            float(conn.execute(f"SELECT MAX(received_at) FROM {table}").fetchone()[0])
            for table in (
                "research_market_flow_reliability_mx",
                "research_market_flow_cost_edge_mx",
                "research_market_flow_full_cost_edge_mx",
                "research_market_flow_event_cluster_mx",
                "research_market_flow_event_reliability_mx",
            )
        ]
        full_cost_event_counts = [
            int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "research_market_flow_full_cost_event_cluster_mx",
                "research_market_flow_full_cost_event_reliability_mx",
            )
        ]
    finally:
        conn.close()

    assert timestamps == [stamp, stamp, stamp, stamp, stamp]
    assert full_cost_event_counts == [0, 0]
