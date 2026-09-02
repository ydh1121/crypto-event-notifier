from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

from b3_trader.market_flow_reaction import MarketFlowReactionStore
from b3_trader.market_flow_reaction_due import MarketFlowReactionDueStore
from b3_trader.market_flow_reliability import MarketFlowReliabilityStore
from b3_trader.market_ohlcv_store import MarketOhlcvStore
from b3_trader.market_price_flow_divergence import MarketPriceFlowDivergenceStore

SIGNAL_TS = 1_800_000_000.0


def _prepare(path: Path) -> None:
    MarketOhlcvStore(path).close()
    MarketPriceFlowDivergenceStore(path).close()


def _insert_signal(path: Path, feature_ts: float) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO research_market_price_flow_divergence_mx(
                   exchange,market,window_label,window_seconds,feature_ts,window_start_ts,window_end_ts,
                   data_ready,status,price_close,delta_quote,delta_pct,
                   price_efficiency_bps_per_100m_quote,evidence_label,received_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "upbit","KRW-BTC","5m",300.0,feature_ts,feature_ts-300.0,feature_ts,
                1,"ready",100.0,-50_000_000.0,-50.0,-2.0,
                "passive_buy_absorption_candidate",feature_ts+1.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_one_hour_path(path: Path) -> None:
    store = MarketOhlcvStore(path)
    try:
        rows = []
        for offset in range(60):
            open_price = 100.0 + 2.0 * (offset / 60.0)
            close_price = 100.0 + 2.0 * ((offset + 1) / 60.0)
            rows.append({
                "exchange":"upbit",
                "market":"KRW-BTC",
                "timeframe":"1m",
                "candle_ts":SIGNAL_TS + offset * 60,
                "open":open_price,
                "high":max(open_price,close_price),
                "low":min(open_price,close_price),
                "close":close_price,
                "base_volume":1.0,
                "quote_volume":1_000_000.0,
                "is_closed":True,
                "source":"public_rest",
                "received_at":SIGNAL_TS + 3601.0,
                "schema_version":1,
            })
        store.upsert_rows(rows)
    finally:
        store.close()


def test_due_drain_upgrades_matured_signal_outside_latest_scan(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_signal(path, SIGNAL_TS)

    reaction = MarketFlowReactionStore(path)
    try:
        first = reaction.compute_pending(now=SIGNAL_TS + 60.0, limit=1)
        assert first["waiting_written"] == 4
    finally:
        reaction.close()

    _insert_one_hour_path(path)
    _insert_signal(path, SIGNAL_TS + 300.0)

    reaction = MarketFlowReactionStore(path)
    try:
        reaction.compute_pending(now=SIGNAL_TS + 3601.0, limit=1)
        before = reaction.conn.execute(
            """SELECT data_ready,status FROM research_market_flow_reaction_mx
               WHERE exchange='upbit' AND market='KRW-BTC'
                 AND signal_window_label='5m' AND signal_feature_ts=?
                 AND horizon_label='1h'""",
            (SIGNAL_TS,),
        ).fetchone()
        assert before is not None
        assert int(before[0]) == 0
        assert str(before[1]) == "waiting_horizon"
    finally:
        reaction.close()

    due = MarketFlowReactionDueStore(path)
    try:
        result = due.compute(now=SIGNAL_TS + 3601.0)
        after = due.reactions.conn.execute(
            """SELECT data_ready,status,hypothesis_directional_return_pct
               FROM research_market_flow_reaction_mx
               WHERE exchange='upbit' AND market='KRW-BTC'
                 AND signal_window_label='5m' AND signal_feature_ts=?
                 AND horizon_label='1h'""",
            (SIGNAL_TS,),
        ).fetchone()
        audit = due.reactions.audit()
    finally:
        due.close()

    assert result["recoverable_due_rows"] >= 2
    assert result["ready_written"] >= 2
    assert result["network_fetches"] is False
    assert result["score_wired"] is False
    assert result["can_place_orders"] is False
    assert after is not None
    assert int(after[0]) == 1
    assert str(after[1]) == "ready"
    assert round(float(after[2]), 6) == 2.0
    assert audit["reaction_time_violations"] == 0
    assert audit["reaction_source_violations"] == 0


def test_reliability_wrapper_drains_due_reactions_before_core_aggregation() -> None:
    source = inspect.getsource(MarketFlowReliabilityStore.compute)
    assert "MarketFlowReactionDueStore" in source
    assert source.index("MarketFlowReactionDueStore") < source.index("super().compute")
