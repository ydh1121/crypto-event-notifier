"""Real SQLite failures must not stop independent market/PAPER writers."""
import sqlite3
import json

import pytest

from b3_trader.market_flow_reaction import MarketFlowReactionStore
from b3_trader.market_flow_reliability_core import MarketFlowReliabilityStore
from b3_trader.market_flow_store import MarketFlowStore
from b3_trader.market_ohlcv_store import MarketOhlcvStore
from b3_trader.research_stage import ResearchStage
from b3_trader.runtime_review import read_research_stage
from b3_trader.tests.test_market_flow_reaction import (
    SIGNAL_TS, _insert_path, _insert_signal, _prepare,
)
from b3_trader.tests.test_market_flow_reliability import _insert_ready


def _writer(path):
    conn = sqlite3.connect(path, timeout=0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE writer_probe (id INTEGER PRIMARY KEY)")
    conn.commit()
    return conn


def _write(conn):
    with conn:
        conn.execute("INSERT INTO writer_probe DEFAULT VALUES")


@pytest.mark.parametrize("kind", ["candles", "trades"])
def test_partial_batch_failure_releases_writer_and_preserves_committed_data(tmp_path, kind):
    path = tmp_path / "market.db"
    other = _writer(path)
    if kind == "candles":
        store = MarketOhlcvStore(path)
        table = "research_market_ohlcv_mx"
        column = "candle_ts"
        rows = [dict(exchange="bithumb", market="KRW-B3", timeframe="1m",
                     candle_ts=i, open=1, high=1, low=1, close=1) for i in (1, 2)]
        save = store.upsert_rows
    else:
        store = MarketFlowStore(path)
        table = "research_market_trade_flow_mx"
        column = "trade_ts"
        rows = [dict(exchange="bithumb", market="KRW-B3", sequential_id=str(i),
                     trade_ts=i, trade_price=1, trade_volume=1, aggressor_side="BID") for i in (1, 2)]
        save = store.insert_trades
    try:
        save([{**rows[0], column: 0, "sequential_id": "old"}])
        store.conn.execute(f"""CREATE TRIGGER fail_second BEFORE INSERT ON {table}
            WHEN NEW.{column}=2 BEGIN SELECT RAISE(ABORT, 'injected write failure'); END""")
        store.conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="injected write failure"):
            save(rows)
        assert not store.conn.in_transaction
        _write(other)
        assert store.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1
        store.conn.execute("DROP TRIGGER fail_second")
        store.conn.commit()
        assert save(rows) == 2
    finally:
        store.close()
        other.close()


def _reaction_store(path):
    other = _writer(path)
    _prepare(path)
    _insert_signal(path)
    _insert_path(path, timeframe="1m", interval=60, bars=15, end_price=102.0)
    return MarketFlowReactionStore(path), other


def test_reaction_write_failure_rolls_back_whole_batch_then_recovers(tmp_path, monkeypatch):
    store, other = _reaction_store(tmp_path / "market.db")
    original = store._upsert
    calls = 0

    def fail_second(row):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError("injected batch failure")
        original(row)

    try:
        monkeypatch.setattr(store, "_upsert", fail_second)
        with pytest.raises(sqlite3.OperationalError, match="injected batch failure"):
            store.compute_pending(now=SIGNAL_TS + 901)
        assert not store.conn.in_transaction
        _write(other)
        assert store.audit()["row_count"] == 0
        monkeypatch.setattr(store, "_upsert", original)
        assert store.compute_pending(now=SIGNAL_TS + 901)["ready_written"] == 1
        assert store.audit()["row_count"] == 4
    finally:
        store.close()
        other.close()


def test_other_writer_can_run_between_reaction_price_calculations(tmp_path, monkeypatch):
    store, other = _reaction_store(tmp_path / "market.db")
    original = store._reaction_price

    def price(*args, **kwargs):
        _write(other)
        return original(*args, **kwargs)

    try:
        monkeypatch.setattr(store, "_reaction_price", price)
        result = store.compute_pending(now=SIGNAL_TS + 901)
        assert result["reactions_processed"] == 4
        assert other.execute("SELECT COUNT(*) FROM writer_probe").fetchone()[0] == 4
        assert not store.conn.in_transaction
    finally:
        store.close()
        other.close()


def test_failed_stats_refresh_keeps_prior_stats_and_saved_reactions(tmp_path):
    store, other = _reaction_store(tmp_path / "market.db")
    try:
        store.compute_pending(now=SIGNAL_TS + 901)
        before = [tuple(row) for row in store.conn.execute("SELECT * FROM research_market_flow_reaction_stats_mx")]
        store.conn.execute("""CREATE TRIGGER fail_stats BEFORE INSERT ON research_market_flow_reaction_stats_mx
            BEGIN SELECT RAISE(ABORT, 'injected stats failure'); END""")
        store.conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="injected stats failure"):
            store.compute_pending(now=SIGNAL_TS + 902)
        assert not store.conn.in_transaction
        _write(other)
        assert [tuple(row) for row in store.conn.execute("SELECT * FROM research_market_flow_reaction_stats_mx")] == before
        assert store.audit()["ready_rows"] == 1
    finally:
        store.close()
        other.close()


def test_reliability_calculations_do_not_hold_writer(tmp_path, monkeypatch):
    path = tmp_path / "market.db"
    other = _writer(path)
    MarketFlowReactionStore(path).close()
    _insert_ready(path, exchange="bithumb", count=3)
    store = MarketFlowReliabilityStore(path)
    original = store._venue_stats

    def stats(values):
        _write(other)
        return original(values)

    try:
        monkeypatch.setattr(store, "_venue_stats", stats)
        store.compute(now=1_900_000_000)
        assert other.execute("SELECT COUNT(*) FROM writer_probe").fetchone()[0] == 3
        assert not store.conn.in_transaction
    finally:
        store.close()
        other.close()


def test_failed_reliability_replace_preserves_prior_summary_and_unlocks(tmp_path):
    path = tmp_path / "market.db"
    other = _writer(path)
    MarketFlowReactionStore(path).close()
    _insert_ready(path, exchange="bithumb", count=3)
    store = MarketFlowReliabilityStore(path)
    try:
        store.compute(now=1_900_000_000)
        before = [tuple(row) for row in store.conn.execute("SELECT * FROM research_market_flow_reliability_mx")]
        store.conn.execute("""CREATE TRIGGER fail_summary BEFORE INSERT ON research_market_flow_reliability_mx
            BEGIN SELECT RAISE(ABORT, 'injected summary failure'); END""")
        store.conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="injected summary failure"):
            store.compute(now=1_900_000_001)
        assert not store.conn.in_transaction
        _write(other)
        assert [tuple(row) for row in store.conn.execute("SELECT * FROM research_market_flow_reliability_mx")] == before
    finally:
        store.close()
        other.close()


@pytest.mark.parametrize("raises", [False, True])
def test_stage_releases_abandoned_write_before_next_owner_runs(tmp_path, raises):
    path = tmp_path / "market.db"
    other = _writer(path)
    conn = sqlite3.connect(path)
    status = tmp_path / "b3_trader/data/research-platform/market-ohlcv-progress.json"
    stages = ResearchStage(status, {"reaction": conn})

    def broken():
        conn.execute("INSERT INTO writer_probe DEFAULT VALUES")
        if raises:
            raise sqlite3.OperationalError("sensitive SQL text must not be exported")
        return {"ok": True}

    def next_stage():
        _write(other)
        return {"ok": True}

    try:
        with pytest.raises((sqlite3.OperationalError, RuntimeError)):
            stages.run("flow_reaction", broken)
        assert not conn.in_transaction
        assert other.execute("SELECT COUNT(*) FROM writer_probe").fetchone()[0] == 0
        assert stages.run("flow_reliability", next_stage) == {"ok": True}
        read = read_research_stage(tmp_path)
        assert read["status"] == "read" and read["stage_status"] == "completed"
        assert read["last_failure"]["stage"] == "flow_reaction"
        assert read["last_failure"]["transactions_before_rollback"] == ["reaction"]
        assert read["last_failure"]["open_transactions"] == []
        assert "sensitive" not in json.dumps(read)
        assert read["pid"] > 0
    finally:
        conn.close()
        other.close()


def test_stage_keeps_sqlite_busy_code_without_mutating_another_writer(tmp_path):
    path = tmp_path / "market.db"
    other = _writer(path)
    conn = sqlite3.connect(path, timeout=0)
    stages = ResearchStage(tmp_path / "b3_trader/data/research-platform/market-ohlcv-progress.json",
                           {"ohlcv": conn})
    try:
        other.execute("INSERT INTO writer_probe DEFAULT VALUES")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            stages.run("ohlcv:bithumb:KRW-B3", lambda: _write(conn))
        assert other.in_transaction
        assert not conn.in_transaction
        failure = read_research_stage(tmp_path)["last_failure"]
        assert failure["sqlite_errorcode"] == sqlite3.SQLITE_BUSY
        assert failure["open_transactions"] == []
    finally:
        other.rollback()
        conn.close()
        other.close()
