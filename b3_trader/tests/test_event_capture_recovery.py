"""Event prices survive write retries; response reads do not retain a writer."""
import sqlite3
import threading

import pytest

from b3_trader import event_trade_samples as samples, market_flow_stream as stream
from b3_trader import intelligence_event_response as responses, event_price_archive as archive
from b3_trader.event_price_archive import TABLE as ARCHIVE
from b3_trader.event_reaction_view import read_event_context
from b3_trader.market_flow_stream_store import MarketFlowStreamStore
from b3_trader.tests.test_event_price_archive import database, trade
from b3_trader.tests.test_market_flow_subscription_runtime import message


def test_alt_ticks_during_real_write_lock_reach_archive_response_and_view(tmp_path, monkeypatch):
    path = tmp_path / 'retry.db'
    owner = database(path)
    samples.ensure_schema(owner.conn)
    owner.conn.commit()
    ticks = MarketFlowStreamStore(path)
    ticks.conn.execute('PRAGMA busy_timeout=1')
    worker = stream.StreamWorker('bithumb', stream.DEFAULT_MARKETS, threading.Event(),
                                {}, threading.RLock(), 99000,
                                event_markets=('KRW-ALT', 'KRW-OTHER'))
    worker.store = ticks
    worker.event_sampler = samples.EventTradeSampler(ticks.conn, 'bithumb', worker.event_markets)
    def receive(stamp, price, market='KRW-ALT'):
        monkeypatch.setattr(stream.time, 'time', lambda: stamp + 0.1)
        worker._on_message(None, message(market, stamp, price, str(stamp)))
    try:
        receive(99999, 100)
        worker.event_sampler.flush(100000, force=True)
        owner.conn.execute('BEGIN IMMEDIATE')
        receive(100898, 999, 'KRW-OTHER')
        assert worker.state['event_capture_error'] == 'OperationalError'
        assert ticks.conn.in_transaction is False
        # The only two ALT trades at this target arrive during write backoff.
        receive(100901, 110)
        receive(100902, 115)
        owner.conn.rollback()
        receive(100929, 999, 'KRW-OTHER')
        collector = responses.IntelligenceEventResponseCollector(owner.conn)
        result = collector.run_once(now=101000)
        assert result['samples_inserted'] == 1
        assert worker.state['event_capture_error'] == ''
        saved = owner.conn.execute(f"SELECT * FROM {ARCHIVE} WHERE market='KRW-ALT' AND point='15m'").fetchone()
        assert saved['trade_ts'] == 100901 and saved['trade_price'] == 110
        visible = read_event_context(owner.conn, 'bithumb', 'KRW-ALT', now=101000)[0]['responses']['15m']
        assert visible['coin'] == pytest.approx(10)
        assert visible['observations']['coin']['target_observation_kind'] == 'trade'
        assert owner.conn.execute("SELECT COUNT(*) FROM research_market_trade_flow_mx WHERE market='KRW-ALT'").fetchone()[0] == 0
    finally:
        owner.conn.rollback()
        ticks.close()
        owner.close()


def test_event_registry_read_failure_preserves_ticks_and_cached_exact_boundary(tmp_path, monkeypatch):
    owner = database(tmp_path / 'read.db')
    samples.ensure_schema(owner.conn)
    owner.conn.commit()
    sampler = samples.EventTradeSampler(owner.conn, 'bithumb', ('KRW-ALT',))
    sampler.refresh(100895)
    original = sampler.refresh
    def unavailable(now):
        raise sqlite3.OperationalError('fixture event read unavailable')
    monkeypatch.setattr(sampler, 'refresh', unavailable)
    try:
        assert sampler.observe(trade('KRW-ALT', 100901, 110), 100902)
        sampler.flush(100903, force=True)
        assert sampler.registry_error == 'OperationalError'
        row = owner.conn.execute(f"SELECT * FROM {ARCHIVE} WHERE point='15m'").fetchone()
        assert row['trade_price'] == 110
        assert sampler.messages == 1
        monkeypatch.setattr(sampler, 'refresh', original)
        sampler.observe(trade('KRW-ALT', 100940, 120), 100941)
        assert sampler.registry_error == ''
    finally:
        owner.close()


def test_reaction_calculation_releases_writer_between_market_reads(tmp_path, monkeypatch):
    path = tmp_path / 'response.db'
    owner = database(path)
    owner.conn.execute('CREATE TABLE probe(value INTEGER)')
    owner.conn.commit()
    for market in ('KRW-ALT', 'KRW-BTC'):
        owner.insert_trades([trade(market, 99999, 100), trade(market, 100901, 110),
                             trade(market, 103601, 120)])
    collector = responses.IntelligenceEventResponseCollector(owner.conn,
        benchmarks=[('bithumb', 'KRW-ALT'), ('bithumb', 'KRW-BTC')])
    second = sqlite3.connect(path, timeout=0.001)
    original = responses.read_price
    reads = []
    def checked(*args, **kwargs):
        assert owner.conn.in_transaction is False
        with second:
            second.execute('INSERT INTO probe VALUES(1)')
        reads.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(responses, 'read_price', checked)
    try:
        assert collector.run_once(now=103700)['samples_inserted'] == 4
        assert len(reads) >= 4
        assert owner.conn.in_transaction is False
        assert collector.run_once(now=103701)['samples_inserted'] == 0
    finally:
        second.close()
        owner.close()


def test_failed_response_batch_rolls_back_and_retry_keeps_original_prices(tmp_path):
    owner = database(tmp_path / 'atomic.db')
    for market in ('KRW-ALT', 'KRW-BTC'):
        owner.insert_trades([trade(market, 99999, 100), trade(market, 100901, 110)])
    collector = responses.IntelligenceEventResponseCollector(owner.conn,
        benchmarks=[('bithumb', 'KRW-ALT'), ('bithumb', 'KRW-BTC')])
    owner.conn.execute("""CREATE TRIGGER reject_second BEFORE INSERT ON research_intelligence_event_responses
        WHEN NEW.market='KRW-BTC' BEGIN SELECT RAISE(FAIL,'fixture'); END""")
    owner.conn.commit()
    try:
        with pytest.raises(sqlite3.Error):
            collector.run_once(now=101000)
        assert owner.conn.in_transaction is False
        assert owner.conn.execute('SELECT COUNT(*) FROM research_intelligence_event_responses').fetchone()[0] == 0
        owner.conn.execute('DROP TRIGGER reject_second')
        owner.conn.commit()
        assert collector.run_once(now=101001)['samples_inserted'] == 2
        assert collector.run_once(now=101002)['samples_inserted'] == 0
    finally:
        owner.close()


def test_archive_batches_allow_other_writers_during_price_reads(tmp_path, monkeypatch):
    path = tmp_path / 'archive.db'
    owner = database(path)
    owner.conn.execute('CREATE TABLE probe(value INTEGER)')
    owner.conn.commit()
    markets = [('bithumb', f'KRW-ALT{i:02}') for i in range(17)]
    for _, market in markets:
        owner.insert_trades([trade(market, 99999), trade(market, 100901, 110)])
    second = sqlite3.connect(path, timeout=0.001)
    original = archive.prepare_market_prices
    def checked(*args, **kwargs):
        assert owner.conn.in_transaction is False
        with second:
            second.execute('INSERT INTO probe VALUES(1)')
        return original(*args, **kwargs)
    monkeypatch.setattr(archive, 'prepare_market_prices', checked)
    try:
        events = archive.eligible_events(owner.conn, 101000)
        assert archive.capture_markets(owner.conn, markets, 101000, events=events) == 34
        assert owner.conn.execute('SELECT COUNT(*) FROM probe').fetchone()[0] == 17
        assert archive.capture_markets(owner.conn, markets, 101001, events=events) == 0
        assert owner.conn.in_transaction is False
    finally:
        second.close()
        owner.close()
