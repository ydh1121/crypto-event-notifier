from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.market_flow_reaction import MarketFlowReactionStore
from b3_trader.market_ohlcv_store import MarketOhlcvStore
from b3_trader.market_price_flow_divergence import MarketPriceFlowDivergenceStore

SIGNAL_TS = 1_800_000_000.0


def _prepare(path: Path) -> None:
    MarketOhlcvStore(path).close()
    MarketPriceFlowDivergenceStore(path).close()


def _insert_signal(path: Path, *, label: str = "passive_buy_absorption_candidate", price: float = 100.0,
                   delta_quote: float = -50_000_000.0, delta_pct: float = -50.0,
                   feature_ts: float = SIGNAL_TS, window_label: str = "5m") -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO research_market_price_flow_divergence_mx(
                   exchange,market,window_label,window_seconds,feature_ts,window_start_ts,window_end_ts,
                   data_ready,status,price_close,delta_quote,delta_pct,
                   price_efficiency_bps_per_100m_quote,evidence_label,received_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("upbit","KRW-BTC",window_label,300.0,feature_ts,feature_ts-300.0,feature_ts,
             1,"ready",price,delta_quote,delta_pct,-2.0,label,feature_ts+1.0),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_path(path: Path, *, timeframe: str, interval: int, bars: int,
                 start_ts: float = SIGNAL_TS, start_price: float = 100.0, end_price: float = 102.0) -> None:
    store = MarketOhlcvStore(path)
    try:
        rows = []
        for offset in range(bars):
            open_price = start_price + (end_price-start_price) * (offset/bars)
            close_price = start_price + (end_price-start_price) * ((offset+1)/bars)
            rows.append({
                "exchange":"upbit","market":"KRW-BTC","timeframe":timeframe,
                "candle_ts":start_ts+offset*interval,"open":open_price,
                "high":max(open_price,close_price),"low":min(open_price,close_price),"close":close_price,
                "base_volume":1.0,"quote_volume":1_000_000.0,"is_closed":True,
                "source":"public_rest","received_at":start_ts+bars*interval+1.0,"schema_version":1,
            })
        store.upsert_rows(rows)
    finally:
        store.close()


def _ready(path: Path, horizon: str) -> dict:
    store = MarketFlowReactionStore(path)
    try:
        return [row for row in store.audit()["latest_ready"] if row["horizon_label"] == horizon][0]
    finally:
        store.close()


def test_passive_buy_absorption_records_positive_hypothesis_return(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path); _insert_signal(path); _insert_path(path,timeframe="1m",interval=60,bars=15,end_price=102.0)
    store = MarketFlowReactionStore(path)
    try:
        result = store.compute_pending(now=SIGNAL_TS+901.0); audit = store.audit()
    finally:
        store.close()
    row = [value for value in audit["latest_ready"] if value["horizon_label"] == "15m"][0]
    assert result["ready_written"] >= 1
    assert round(float(row["future_return_pct"]),6) == 2.0
    assert row["flow_direction"] == -1 and row["hypothesis_direction"] == 1
    assert round(float(row["flow_followthrough_return_pct"]),6) == -2.0
    assert round(float(row["hypothesis_directional_return_pct"]),6) == 2.0
    assert audit["reaction_time_violations"] == 0
    assert audit["reaction_source_violations"] == 0
    assert audit["hypothesis_direction_violations"] == 0


def test_passive_sell_absorption_rewards_negative_future_return(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_signal(path,label="passive_sell_absorption_candidate",delta_quote=60_000_000.0,delta_pct=60.0)
    _insert_path(path,timeframe="1m",interval=60,bars=15,end_price=98.0)
    store = MarketFlowReactionStore(path)
    try:
        store.compute_pending(now=SIGNAL_TS+901.0); row = [v for v in store.audit()["latest_ready"] if v["horizon_label"]=="15m"][0]
    finally:
        store.close()
    assert round(float(row["future_return_pct"]),6) == -2.0
    assert row["flow_direction"] == 1 and row["hypothesis_direction"] == -1
    assert round(float(row["hypothesis_directional_return_pct"]),6) == 2.0


def test_reaction_waits_then_upgrades_after_exact_future_path_arrives(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path); _insert_signal(path)
    store = MarketFlowReactionStore(path)
    try:
        first = store.compute_pending(now=SIGNAL_TS+901.0)
        assert first["waiting_written"] >= 1 and store.audit()["ready_rows"] == 0
        _insert_path(path,timeframe="1m",interval=60,bars=15,end_price=101.0)
        second = store.compute_pending(now=SIGNAL_TS+902.0); audit = store.audit()
    finally:
        store.close()
    assert second["ready_written"] >= 1 and audit["ready_rows"] >= 1


def test_missing_minute_in_forward_path_is_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path); _insert_signal(path); _insert_path(path,timeframe="1m",interval=60,bars=15,end_price=101.0)
    conn = sqlite3.connect(path)
    try:
        conn.execute("DELETE FROM research_market_ohlcv_mx WHERE exchange='upbit' AND market='KRW-BTC' AND timeframe='1m' AND candle_ts=?",(SIGNAL_TS+300.0,)); conn.commit()
    finally:
        conn.close()
    store = MarketFlowReactionStore(path)
    try:
        result = store.compute_pending(now=SIGNAL_TS+901.0); audit = store.audit()
    finally:
        store.close()
    assert result["ready_written"] == 0 and audit["ready_rows"] == 0 and audit["waiting_rows"] >= 1


def test_one_day_reaction_uses_exact_contiguous_5m_path(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path); _insert_signal(path); _insert_path(path,timeframe="5m",interval=300,bars=288,end_price=103.0)
    store = MarketFlowReactionStore(path)
    try:
        store.compute_pending(now=SIGNAL_TS+86401.0); rows = [v for v in store.audit()["latest_ready"] if v["horizon_label"]=="1d"]
    finally:
        store.close()
    assert rows and rows[0]["reaction_source_timeframe"] == "5m"
    assert round(float(rows[0]["future_return_pct"]),6) == 3.0


def test_unaligned_one_day_signal_is_skipped_not_approximated(tmp_path: Path) -> None:
    path = tmp_path / "market.db"; feature_ts = SIGNAL_TS+60.0
    _prepare(path); _insert_signal(path,feature_ts=feature_ts,window_label="1m")
    store = MarketFlowReactionStore(path)
    try:
        result = store.compute_pending(now=feature_ts+86401.0)
        one_day = store.conn.execute("SELECT COUNT(*) FROM research_market_flow_reaction_mx WHERE horizon_label='1d'").fetchone()[0]
    finally:
        store.close()
    assert result["exact_alignment_skipped"] >= 1 and one_day == 0


def test_reaction_stats_separate_followthrough_from_absorption_hypothesis(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path); _insert_signal(path); _insert_path(path,timeframe="1m",interval=60,bars=15,end_price=102.0)
    store = MarketFlowReactionStore(path)
    try:
        store.compute_pending(now=SIGNAL_TS+901.0); stats = [v for v in store.audit()["stats"] if v["horizon_label"]=="15m"]
    finally:
        store.close()
    assert stats
    row = stats[0]
    assert row["sample_count"] == 1 and row["hypothesis_sample_count"] == 1
    assert round(float(row["mean_flow_followthrough_return_pct"]),6) == -2.0
    assert round(float(row["mean_hypothesis_directional_return_pct"]),6) == 2.0
    assert float(row["hypothesis_hit_rate_pct"]) == 100.0


def test_pre_horizon_waiting_rows_are_deferred_until_target_time(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path); _insert_signal(path)
    store = MarketFlowReactionStore(path)
    try:
        first = store.compute_pending(now=SIGNAL_TS+60.0)
        second = store.compute_pending(now=SIGNAL_TS+120.0)
    finally:
        store.close()
    assert first["reactions_processed"] == 4
    assert first["waiting_written"] == 4
    assert second["reactions_processed"] == 0
    assert second["deferred_existing_pre_horizon"] == 4


def test_old_missing_paths_become_terminal_and_do_not_starve_future_cycles(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path); _insert_signal(path)
    store = MarketFlowReactionStore(path)
    try:
        first = store.compute_pending(now=SIGNAL_TS+24_001.0)
        second = store.compute_pending(now=SIGNAL_TS+24_002.0)
        audit = store.audit()
    finally:
        store.close()
    assert first["terminal_expired_missing_path"] >= 3
    assert audit["expired_missing_path_rows"] >= 3
    assert second["reactions_processed"] == 0
    assert second["deferred_existing_pre_horizon"] >= 1
