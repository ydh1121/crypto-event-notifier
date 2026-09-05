from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from b3_trader.market_flow_cost_edge import MarketFlowCostEdgeStore
from b3_trader.market_flow_orderbook_stream_store import MarketFlowOrderbookStreamStore
from b3_trader.market_flow_reaction import MarketFlowReactionStore


def _prepare(path: Path) -> None:
    MarketFlowReactionStore(path).close()
    MarketFlowOrderbookStreamStore(path).close()


def _insert_reaction(
    path: Path,
    *,
    signal_ts: float = 1_800_000_000.0,
    end_ts: float = 1_800_000_900.0,
    direction: int = 1,
    gross_return_pct: float = 0.10,
) -> None:
    evidence = "passive_buy_absorption_candidate" if direction > 0 else "passive_sell_absorption_candidate"
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
                "bithumb","KRW-ETH","1m",signal_ts,evidence,100.0,
                -1_000_000.0 if direction > 0 else 1_000_000.0,
                -1 if direction > 0 else 1,direction,
                "15m",900.0,signal_ts,end_ts,"1m",60.0,1,"ready",
                end_ts - 60.0,100.0,gross_return_pct * direction,
                -gross_return_pct,gross_return_pct,
                "price_flow_divergence+rest_ohlcv",end_ts + 1.0,1,1,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_book(
    path: Path,
    *,
    feature_ts: float,
    spread_bps: float,
    bid_depth: float,
    ask_depth: float,
    continuous: int = 1,
) -> None:
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
                "bithumb","KRW-ETH","1m",60.0,feature_ts,feature_ts - 60.0,feature_ts,
                50,spread_bps,spread_bps,bid_depth,ask_depth,0.0,
                0.0,0.0,0.0,0.0,10,10,continuous,feature_ts + 1.0,1,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_exact_continuous_books_compute_spread_penalty_only(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    signal_ts = 1_800_000_000.0
    end_ts = signal_ts + 900.0
    _insert_reaction(path,signal_ts=signal_ts,end_ts=end_ts,direction=1,gross_return_pct=0.10)
    _insert_book(path,feature_ts=signal_ts,spread_bps=4.0,bid_depth=4_000_000.0,ask_depth=2_000_000.0)
    _insert_book(path,feature_ts=end_ts,spread_bps=6.0,bid_depth=5_000_000.0,ask_depth=3_000_000.0)

    store = MarketFlowCostEdgeStore(path)
    try:
        result = store.compute(now=end_ts + 10.0)
        audit = store.audit()
    finally:
        store.close()

    assert result["orderbook_friction_ready_rows"] == 1
    assert audit["ok"] is True
    row = audit["rows"][0]
    assert row["orderbook_friction_ready"] == 1
    assert row["roundtrip_spread_cost_bps"] == pytest.approx(5.0)
    assert row["spread_adjusted_hypothesis_return_pct"] == pytest.approx(0.05)
    assert row["entry_relevant_top5_depth_quote"] == pytest.approx(2_000_000.0)
    assert row["exit_relevant_top5_depth_quote"] == pytest.approx(5_000_000.0)
    assert row["fee_model_ready"] == 0
    assert row["slippage_model_ready"] == 0
    assert row["full_cost_edge_ready"] == 0
    assert row["full_cost_adjusted_return_pct"] is None


def test_missing_or_noncontinuous_book_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    signal_ts = 1_800_000_000.0
    end_ts = signal_ts + 900.0
    _insert_reaction(path,signal_ts=signal_ts,end_ts=end_ts,direction=-1,gross_return_pct=0.20)
    _insert_book(path,feature_ts=signal_ts,spread_bps=3.0,bid_depth=2_000_000.0,ask_depth=2_000_000.0)

    store = MarketFlowCostEdgeStore(path)
    try:
        result = store.compute(now=end_ts + 10.0)
        audit = store.audit()
    finally:
        store.close()

    assert result["orderbook_friction_ready_rows"] == 0
    row = audit["rows"][0]
    assert row["orderbook_friction_ready"] == 0
    assert row["roundtrip_spread_cost_bps"] is None
    assert row["spread_adjusted_hypothesis_return_pct"] is None
    assert row["cost_status"] == "waiting_exact_continuous_orderbook_windows"


def test_full_cost_never_promotes_without_fee_and_historical_slippage_models(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    signal_ts = 1_800_000_000.0
    end_ts = signal_ts + 900.0
    _insert_reaction(path,signal_ts=signal_ts,end_ts=end_ts,direction=1,gross_return_pct=0.30)
    _insert_book(path,feature_ts=signal_ts,spread_bps=2.0,bid_depth=8_000_000.0,ask_depth=8_000_000.0)
    _insert_book(path,feature_ts=end_ts,spread_bps=2.0,bid_depth=8_000_000.0,ask_depth=8_000_000.0)

    store = MarketFlowCostEdgeStore(path)
    try:
        store.compute(now=end_ts + 10.0)
        audit = store.audit()
    finally:
        store.close()

    assert audit["full_cost_ready_rows"] == 0
    assert audit["incomplete_cost_contract_violations"] == 0
    assert audit["spread_contract_violations"] == 0
    assert audit["stats"][0]["full_cost_ready_count"] == 0
