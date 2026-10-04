import hashlib
import json
import sqlite3
import threading

import pytest

from b3_trader import event_trade_samples as samples, market_flow_stream as stream, managed_backup
from b3_trader.event_price_archive import POINTS, TABLE as ARCHIVE, capture_market, read_price
from b3_trader.event_capture_review import read_event_capture, stream_subscription_evidence
from b3_trader.event_reaction_view import read_event_context
from b3_trader.intelligence_event_response import IntelligenceEventResponseCollector
from b3_trader.market_flow_stream_store import MarketFlowStreamStore
from b3_trader.tests.test_event_price_archive import database, trade
from b3_trader.tests.test_market_flow_subscription import inputs, catalogs
from b3_trader.market_flow_subscription import SubscriptionSelector, DEFAULT_MARKETS
from b3_trader.tests.test_market_flow_subscription_runtime import message


def sampler(store, markets=('KRW-ALT',), exchange='bithumb'):
    samples.ensure_schema(store.conn);store.conn.commit()
    return samples.EventTradeSampler(store.conn, exchange, markets)


def test_entire_catalog_is_price_only_not_an_expanded_orderbook_watchlist(tmp_path):
    inputs(tmp_path)
    names = tuple(f'KRW-ALT{i}' for i in range(500))
    selector = SubscriptionSelector(tmp_path,environment={},catalog=catalogs({'bithumb':names}))
    selected = selector.refresh(1000)
    assert selected['bithumb'] == DEFAULT_MARKETS
    assert len(selector.event_markets('bithumb')) == 502
    request = json.loads(stream._subscription('bithumb', selected['bithumb'], selector.event_markets('bithumb')))
    assert len(request[1]['codes']) == 502 and request[1]['isOnlyRealtime'] is True
    assert request[2]['codes'] == list(DEFAULT_MARKETS)
    assert selector.event_markets('upbit') == tuple(sorted(DEFAULT_MARKETS))
    def fail(exchange): raise TimeoutError()
    selector.catalog = fail;selector.refresh(1400)
    assert len(selector.event_markets('bithumb')) == 502  # Last validated catalog survives outage.


def test_unwatched_alt_through_real_worker_archive_collector_and_viewer(tmp_path, monkeypatch):
    db=tmp_path/'prices.db';store=database(db);ticks=MarketFlowStreamStore(db)
    markets=('KRW-ALT','KRW-BTC','KRW-ETH')
    worker=stream.StreamWorker('bithumb',DEFAULT_MARKETS,threading.Event(),{},threading.RLock(),99000,
                               event_markets=markets)
    worker.store=ticks;worker.event_sampler=sampler(store,markets)
    try:
        for point, offset in POINTS.items():
            stamp=100000+offset+(-1 if point=='baseline' else 1)
            monkeypatch.setattr(stream.time,'time',lambda s=stamp:s+1)
            for n,market in enumerate(markets):
                worker._on_message(None,message(market,stamp,100 if point=='baseline' else 110+n,point))
            worker._flush(force=True);worker.event_sampler.flush(stamp+2,force=True)
        assert ticks.conn.execute("SELECT COUNT(*) FROM research_market_trade_flow_mx WHERE market='KRW-ALT'").fetchone()[0] == 0
        # No all-market sessions, raw volumes, orderbooks, PAPER orders or accounts.
        assert ticks.conn.execute("SELECT COUNT(*) FROM research_market_flow_stream_session_mx WHERE market='KRW-ALT'").fetchone()[0] == 0
        assert store.conn.execute(f'SELECT COUNT(*) FROM {ARCHIVE}').fetchone()[0] == 15
        collector=IntelligenceEventResponseCollector(store.conn)
        assert collector.run_once(now=187300)['samples_inserted'] == 12
        view=read_event_context(store.conn,'bithumb','KRW-ALT',now=187300)[0]
        for label in ('15m','1h','4h','1d'):
            response=view['responses'][label]
            assert response['coin'] == pytest.approx(10)
            assert response['vs_btc_pp'] == pytest.approx(-1)
            assert response['vs_eth_pp'] == pytest.approx(-2)
        assert read_event_context(store.conn,'upbit','KRW-ALT',now=187300)[0]['responses']['15m']['coin'] is None
    finally: ticks.close();store.close()


def test_late_news_real_endpoint_provenance_survives_restart_and_expiry(tmp_path):
    db=tmp_path/'late.db';store=database(db)
    event=dict(store.conn.execute('SELECT * FROM research_intelligence_events').fetchone())
    store.conn.execute('DELETE FROM research_intelligence_events');store.conn.commit()
    s=sampler(store)
    for stamp,price in ((99990,100),(99999,101),(100005,102),(100901,111)):
        s.observe(trade('KRW-ALT',stamp,price),stamp+1);s.flush(stamp+2,force=True)
    store.conn.execute('INSERT INTO research_intelligence_events VALUES(?,?,?,?,?,?,?,?,?)',tuple(event.values()))
    store.conn.commit()
    collector=IntelligenceEventResponseCollector(store.conn)
    assert collector.run_once(now=101000)['samples_inserted'] == 1
    row=store.conn.execute('SELECT * FROM research_intelligence_event_responses').fetchone()
    attrs=json.loads(row['attributes_json'])
    assert attrs['baseline_observation_kind'] == 'minute_endpoints'
    assert attrs['baseline_semantics'] == 'nearest_stored_real_minute_endpoint_within_tolerance'
    # 99999 is an interior tick of that minute. The real stored first endpoint
    # 99990 is admissible; never falsely claim the complete stream's last tick.
    assert row['baseline_trade_ts'] == 99990
    store.close()
    store=database_reopen(db);s=samples.EventTradeSampler(store.conn,'bithumb',('KRW-ALT',))
    s.observe(trade('KRW-ALT',186401,120),186402);s.flush(186403,force=True)
    assert store.conn.execute(f'SELECT MIN(first_ts) FROM {samples.TABLE}').fetchone()[0] == 186401
    assert IntelligenceEventResponseCollector(store.conn).run_once(now=186500)['samples_inserted'] == 1
    daily=store.conn.execute("SELECT * FROM research_intelligence_event_responses WHERE horizon_label='1d'").fetchone()
    assert daily['baseline_trade_ts'] == 99990
    assert json.loads(daily['attributes_json'])['baseline_observation_kind'] == 'minute_endpoints'
    assert daily['return_pct'] == pytest.approx(20)
    visible=read_event_context(store.conn,'bithumb','KRW-ALT',now=186500)[0]['responses']['1d']['observations']['coin']
    assert visible['baseline_observation_kind'] == 'minute_endpoints'
    assert visible['target_observation_kind'] == 'trade'
    store.close()


def database_reopen(path):
    from types import SimpleNamespace
    conn=sqlite3.connect(path);conn.row_factory=sqlite3.Row
    return SimpleNamespace(conn=conn,close=conn.close)


def test_outage_future_tick_and_wrong_exchange_cannot_fill_baseline(tmp_path):
    store=database(tmp_path/'gap.db');s=sampler(store)
    assert not s.observe(trade('KRW-ALT',99999,exchange='upbit'),100000)
    assert not s.observe(trade('KRW-ALT',100001),100000)
    assert not s.observe(trade('KRW-ALT',99879),100000)
    assert not s.observe(trade('KRW-ALT',99999,float('nan')),100000)
    assert not s.observe(trade('KRW-OTHER',99999),100000)
    s.observe(trade('KRW-ALT',100001),100002);s.flush(100003,force=True)
    s.observe(trade('KRW-ALT',100901,110),100902);s.flush(100903,force=True)
    result=IntelligenceEventResponseCollector(store.conn).run_once(now=101000)
    assert result['samples_inserted'] == 0 and result['missing_baseline'] > 0
    store.close()


def test_same_time_events_and_multiple_ticks_preserve_exact_nearest_prices(tmp_path):
    store=database(tmp_path/'same.db')
    store.conn.execute("INSERT INTO research_intelligence_events SELECT 'second',event_type,source_id,title,source_ts,source_url,published_at,scheduled_at,received_at FROM research_intelligence_events")
    store.conn.commit();s=sampler(store)
    for stamp in (99901,99999,99980):
        assert s.observe(trade('KRW-ALT',stamp,stamp),100000)
    s.flush(100001,force=True)
    for event in store.conn.execute('SELECT * FROM research_intelligence_events'):
        assert read_price(store.conn,event,'bithumb','KRW-ALT','baseline',100001,120)['trade_ts'] == 99999
    # A reconnect and an older tick cannot replace the better stored price.
    s=samples.EventTradeSampler(store.conn,'bithumb',('KRW-ALT',))
    s.observe(trade('KRW-ALT',99950,99950),100002);s.flush(100003,force=True)
    assert store.conn.execute(f'SELECT MIN(trade_ts) FROM {ARCHIVE}').fetchone()[0] == 99999
    store.close()


def test_buffer_stabilizes_and_expiry_keeps_permanent_evidence(tmp_path):
    store=database(tmp_path/'bounded.db');s=sampler(store,('KRW-ALT','KRW-ALT2'))
    for minute in range(480):
        now=100000+minute*60
        for market in s.markets:
            for i in range(5): s.observe(trade(market,now+i,100+i),now+i+1)
        s.flush(now+6,force=True)
    count=store.conn.execute(f'SELECT COUNT(*) FROM {samples.TABLE}').fetchone()[0]
    assert count <= 362*2 and len(s.pending) == 0
    assert store.conn.execute(f'SELECT COUNT(*) FROM {ARCHIVE}').fetchone()[0] > 0
    assert store.conn.execute('SELECT COUNT(*) FROM research_market_trade_flow_mx').fetchone()[0] == 0
    store.close()


def test_failed_flush_keeps_ticks_for_retry_and_rolls_back(tmp_path):
    store=database(tmp_path/'retry.db');s=sampler(store)
    s.observe(trade('KRW-ALT',99999),100000)
    store.conn.execute(f"CREATE TRIGGER reject_sample BEFORE INSERT ON {samples.TABLE} BEGIN SELECT RAISE(FAIL,'fixture'); END")
    store.conn.commit()
    with pytest.raises(sqlite3.Error): s.flush(100001,force=True)
    assert s.pending and s.exact
    assert store.conn.execute(f'SELECT COUNT(*) FROM {samples.TABLE}').fetchone()[0] == 0
    store.conn.execute('DROP TRIGGER reject_sample');store.conn.commit();s.flush(100002,force=True)
    assert not s.pending and not s.exact
    assert store.conn.execute(f'SELECT COUNT(*) FROM {ARCHIVE}').fetchone()[0] == 1
    store.close()


def test_schema_waits_for_verified_backup_and_restart_does_not_copy_again(tmp_path,monkeypatch):
    db=tmp_path/'prepare.db';store=database(db);store.close();before=hashlib.sha256(db.read_bytes()).hexdigest()
    def fail(*args,**kwargs): raise ValueError('fixture backup unavailable')
    monkeypatch.setattr(managed_backup,'ensure_backup',fail)
    with pytest.raises(ValueError): samples.prepare_database(db)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    calls=[]
    monkeypatch.setattr(managed_backup,'ensure_backup',lambda *args,**kwargs:calls.append((args,kwargs)))
    samples.prepare_database(db);samples.prepare_database(db)
    assert len(calls) == 1 and calls[0][1]['role'] == 'paper'


def test_check_reports_actual_alt_prices_separate_from_configured_subscription(tmp_path):
    db=tmp_path/'report.db';store=database(db);s=sampler(store,('KRW-ALT','KRW-BTC','KRW-ETH'))
    for market in ('KRW-ALT','KRW-BTC'): s.observe(trade(market,99999),100000)
    s.flush(100001,force=True);store.close()
    before=hashlib.sha256(db.read_bytes()).hexdigest()
    result=read_event_capture(db,now=100002)['universe_samples']
    assert result['scope'] == 'last_120s'
    assert result['exchanges'][0]['window_markets'] == 2
    assert result['exchanges'][0]['last_120s']['alt_markets'] == 1
    assert result['continuous_coverage_proven'] is False
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    saved=stream_subscription_evidence({'exchanges':{'bithumb':{'markets':['KRW-BTC'],
        'event_markets':list(s.markets),'connected':True,'event_capture':s.evidence(100002)}}})
    assert saved['event_price_collection']['bithumb']['subscribed_markets'] == 3
    assert saved['event_price_collection']['bithumb']['observed_markets'] == 2


def test_sample_write_failure_does_not_drop_existing_flow_or_claim_success(tmp_path,monkeypatch):
    db=tmp_path/'isolated.db';store=database(db);ticks=MarketFlowStreamStore(db)
    state={};worker=stream.StreamWorker('bithumb',DEFAULT_MARKETS,threading.Event(),state,threading.RLock(),99000,
                                       event_markets=DEFAULT_MARKETS)
    worker.store=ticks;worker.event_sampler=sampler(store,DEFAULT_MARKETS)
    monkeypatch.setattr(stream.time,'time',lambda:100000)
    def fail(*args,**kwargs): raise sqlite3.OperationalError('fixture write unavailable')
    monkeypatch.setattr(worker.event_sampler,'flush',fail)
    worker._on_message(None,message('KRW-BTC',99999,100,'tick'))
    assert state['event_capture_error'] == 'OperationalError'
    assert ticks.conn.execute('SELECT COUNT(*) FROM research_market_trade_flow_mx').fetchone()[0] == 1
    service=stream.MarketFlowStreamService(markets=DEFAULT_MARKETS)
    service.states['bithumb']=state
    assert service._status_payload(running=True)['ok'] is False
    ticks.close();store.close()


def test_subscription_rejection_is_visible_and_reconnects():
    from types import SimpleNamespace
    state={};closed=[]
    worker=stream.StreamWorker('upbit',DEFAULT_MARKETS,threading.Event(),state,threading.RLock(),99000)
    worker._on_message(SimpleNamespace(close=lambda:closed.append(True)),json.dumps({'error':{'name':'INVALID_PARAM'}}))
    assert closed == [True] and state['event_capture_error'] == 'SubscriptionRejected'
