from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.market_flow_orderbook_stream_store import MarketFlowOrderbookStreamStore
from b3_trader.market_flow_stream_store import MarketFlowStreamStore
from b3_trader.market_ohlcv_store import MarketOhlcvStore
from b3_trader.market_price_flow_divergence import MarketPriceFlowDivergenceStore


FEATURE_TS = 1_800_000_000.0
WINDOW_SECONDS = 300.0
WINDOW_START = FEATURE_TS - WINDOW_SECONDS


def _prepare(path: Path) -> None:
    MarketFlowStreamStore(path).close()
    MarketFlowOrderbookStreamStore(path).close()
    MarketOhlcvStore(path).close()


def _insert_window_pair(
    path: Path,
    *,
    feature_ts: float = FEATURE_TS,
    delta_pct: float = -60.0,
    delta_quote: float = -60_000_000.0,
    buy_quote: float = 20_000_000.0,
    sell_quote: float = 80_000_000.0,
    bid_ratio: float = 1.5,
    ask_ratio: float = 0.8,
    bid_pairs: int = 20,
    ask_pairs: int = 20,
    flow_continuity: int = 1,
    orderbook_continuity: int = 1,
) -> None:
    start = feature_ts - WINDOW_SECONDS
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO research_market_flow_window_feature_mx(
                   exchange,market,window_label,window_seconds,feature_ts,window_start_ts,window_end_ts,
                   trade_count,buy_volume,sell_volume,buy_quote_volume,sell_quote_volume,delta_volume,
                   delta_quote,delta_pct,session_cvd_quote,cvd_anchor_ts,continuity_complete,
                   side_coverage_pct,source,received_at,feature_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "upbit","KRW-BTC","5m",WINDOW_SECONDS,feature_ts,start,feature_ts,
                100,1.0,2.0,buy_quote,sell_quote,-1.0,delta_quote,delta_pct,-10_000_000.0,
                start - 60.0,flow_continuity,100.0,"public_websocket_trade",feature_ts + 1.0,1,
            ),
        )
        conn.execute(
            """INSERT INTO research_market_orderbook_window_feature_mx(
                   exchange,market,window_label,window_seconds,feature_ts,window_start_ts,window_end_ts,
                   snapshot_count,spread_bps_avg,spread_bps_max,bid_depth_quote_avg,ask_depth_quote_avg,
                   imbalance_pct_avg,bid_refill_quote,bid_depletion_quote,ask_refill_quote,ask_depletion_quote,
                   bid_same_best_pairs,ask_same_best_pairs,bid_replenishment_ratio,ask_replenishment_ratio,
                   bid_refill_quote_per_second,ask_refill_quote_per_second,continuity_complete,
                   source,received_at,feature_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "upbit","KRW-BTC","5m",WINDOW_SECONDS,feature_ts,start,feature_ts,
                200,2.0,4.0,100_000_000.0,100_000_000.0,0.0,
                150_000_000.0,100_000_000.0,80_000_000.0,100_000_000.0,
                bid_pairs,ask_pairs,bid_ratio,ask_ratio,500_000.0,266_666.0,
                orderbook_continuity,"public_websocket_orderbook",feature_ts + 1.0,1,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_price(path: Path, *, open_price: float = 100.0, close_price: float = 99.9) -> None:
    store = MarketOhlcvStore(path)
    try:
        store.upsert_rows([
            {
                "exchange": "upbit",
                "market": "KRW-BTC",
                "timeframe": "5m",
                "candle_ts": WINDOW_START,
                "open": open_price,
                "high": max(open_price, close_price),
                "low": min(open_price, close_price),
                "close": close_price,
                "base_volume": 10.0,
                "quote_volume": 1_000_000_000.0,
                "is_closed": True,
                "source": "public_rest",
                "received_at": FEATURE_TS + 10.0,
                "schema_version": 1,
            }
        ])
    finally:
        store.close()


def test_passive_buy_absorption_candidate_requires_exact_closed_price_and_replenishment(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_window_pair(path)
    _insert_price(path, open_price=100.0, close_price=99.9)

    store = MarketPriceFlowDivergenceStore(path)
    try:
        result = store.compute_pending(now=FEATURE_TS + 20.0)
        audit = store.audit()
    finally:
        store.close()

    assert result["ready_written"] == 1
    assert result["passive_buy_absorption_candidates"] == 1
    assert audit["ready_rows"] == 1
    assert audit["alignment_violations"] == 0
    assert audit["continuity_violations"] == 0
    row = audit["latest_ready"][0]
    assert row["price_candle_ts"] == WINDOW_START
    assert round(float(row["price_return_bps"]), 6) == -10.0
    assert row["strong_sell_pressure"] == 1
    assert row["price_resilient_to_sell"] == 1
    assert row["passive_buy_absorption_candidate"] == 1
    assert row["passive_sell_absorption_candidate"] == 0
    assert row["evidence_label"] == "passive_buy_absorption_candidate"


def test_waiting_price_is_upgraded_when_exact_closed_candle_arrives(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_window_pair(path)

    store = MarketPriceFlowDivergenceStore(path)
    try:
        first = store.compute_pending(now=FEATURE_TS + 5.0)
        assert first["waiting_written"] == 1
        assert store.audit()["ready_rows"] == 0
        _insert_price(path, open_price=100.0, close_price=100.1)
        second = store.compute_pending(now=FEATURE_TS + 20.0)
        audit = store.audit()
    finally:
        store.close()

    assert second["ready_written"] == 1
    assert audit["ready_rows"] == 1
    assert audit["latest_ready"][0]["price_candle_ts"] == WINDOW_START


def test_non_timeframe_boundary_window_is_not_joined(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_window_pair(path, feature_ts=FEATURE_TS + 60.0)
    _insert_price(path)

    store = MarketPriceFlowDivergenceStore(path)
    try:
        result = store.compute_pending(now=FEATURE_TS + 120.0)
        audit = store.audit()
    finally:
        store.close()

    assert result["candidates_scanned"] == 0
    assert audit["row_count"] == 0


def test_incomplete_websocket_continuity_is_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_window_pair(path, flow_continuity=0)
    _insert_price(path)

    store = MarketPriceFlowDivergenceStore(path)
    try:
        result = store.compute_pending(now=FEATURE_TS + 20.0)
        audit = store.audit()
    finally:
        store.close()

    assert result["candidates_scanned"] == 0
    assert audit["ready_rows"] == 0


def test_positive_flow_with_small_price_response_and_ask_refill_is_sell_absorption_candidate(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_window_pair(
        path,
        delta_pct=50.0,
        delta_quote=50_000_000.0,
        buy_quote=75_000_000.0,
        sell_quote=25_000_000.0,
        bid_ratio=0.7,
        ask_ratio=1.25,
        bid_pairs=20,
        ask_pairs=20,
    )
    _insert_price(path, open_price=100.0, close_price=100.1)

    store = MarketPriceFlowDivergenceStore(path)
    try:
        store.compute_pending(now=FEATURE_TS + 20.0)
        row = store.audit()["latest_ready"][0]
    finally:
        store.close()

    assert row["strong_buy_pressure"] == 1
    assert row["price_resilient_to_buy"] == 1
    assert row["passive_sell_absorption_candidate"] == 1
    assert row["evidence_label"] == "passive_sell_absorption_candidate"
