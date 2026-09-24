"""Stored partial prices reach the coin view without writing/fabricating returns."""
import hashlib
import http.client
import json
import sqlite3
import threading
import time

import pytest

from b3_trader import event_price_archive as archive
from b3_trader.event_reaction_view import read_event_context
from b3_trader.strategy_lab_context import read_coin_context
from b3_trader.strategy_lab_market import read_strategy_lab_market
from b3_trader.strategy_lab_transport import detail_items
from b3_trader.strategy_journal_review import ThreadingHTTPServer, handler
from b3_trader.tests.test_strategy_lab_journal import fixture_db
from b3_trader.intelligence_event_response import IntelligenceEventResponseCollector
from b3_trader.tests.test_event_reaction_flow import setup, trade
from b3_trader.tests.test_intelligence_event_response import _insert_event


def initialize(path):
    conn=setup(path)
    _insert_event(path,event_id='release',event_ts=100000)
    collector=IntelligenceEventResponseCollector(conn,benchmarks=[('bithumb',m) for m in ('KRW-B3','KRW-BTC','KRW-ETH')])
    return conn,collector


def test_before_first_reaction_preserved_prices_reach_read_only_coin_projection(tmp_path,monkeypatch):
    path=tmp_path/'early.db';conn,collector=initialize(path)
    for market,price in [('KRW-B3',100),('KRW-BTC',1000),('KRW-ETH',500)]:
        trade(conn,market,99999,price)
    assert collector.run_once(now=100001)['prices_archived']==3
    conn.close();before=hashlib.sha256(path.read_bytes()).hexdigest()
    conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    monkeypatch.setattr('b3_trader.event_reaction_view.time.time',lambda:100002)
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    shown=read_coin_context(conn,tables,'bithumb','KRW-B3')['events'][0]
    assert shown['market']=='KRW-B3' and shown['captured_at'] is None
    for name,price in [('coin',100),('btc',1000),('eth',500)]:
        for horizon,_ in archive.HORIZONS:
            assert shown['responses'][horizon][name] is None
            progress=shown['price_progress'][name][horizon]
            assert progress['status']=='before_horizon' and progress['target'] is None
            assert progress['baseline']=={'price':price,'trade_ts':99999,'origin':'archive'}
    conn.close();assert hashlib.sha256(path.read_bytes()).hexdigest()==before


def test_archived_prices_stay_uncomputed_until_collector_persists_response(tmp_path):
    path=tmp_path/'later.db';conn,collector=initialize(path)
    for n,market in enumerate(('KRW-B3','KRW-BTC','KRW-ETH')):
        trade(conn,market,99999,100)
        trade(conn,market,100901,100+n)
        archive.capture_market(conn,'bithumb',market,100902)
    conn.commit()
    shown=read_event_context(conn,'bithumb','KRW-B3',now=100903)[0]
    assert shown['price_progress']['coin']['15m']['status']=='awaiting_capture'
    assert shown['price_progress']['coin']['15m']['target']['price']==100
    assert shown['responses']['15m']['coin'] is None
    assert conn.execute('SELECT COUNT(*) FROM research_intelligence_event_responses').fetchone()[0]==0
    assert collector.run_once(now=100904)['samples_inserted']==3
    shown=read_event_context(conn,'bithumb','KRW-B3',now=100905)[0]
    assert shown['price_progress']['coin']['15m']['status']=='recorded'
    assert shown['responses']['15m']['observations']['coin']['baseline_price']==100
    assert shown['responses']['15m']['coin']==0
    assert shown['responses']['15m']['vs_btc_pp']==pytest.approx(-1)
    assert shown['responses']['15m']['vs_eth_pp']==pytest.approx(-2)
    conn.close()


def test_benchmark_only_event_never_borrows_another_coin_or_exchange_price(tmp_path):
    path=tmp_path/'scope.db';conn,collector=initialize(path)
    trade(conn,'KRW-BTC',99999,1000);trade(conn,'KRW-BTC',100901,1010)
    trade(conn,'KRW-B3',99999,100,exchange='upbit')
    trade(conn,'USDT-B3',99999,200)
    for ex,market in [('bithumb','KRW-BTC'),('upbit','KRW-B3'),('bithumb','USDT-B3')]:
        archive.capture_market(conn,ex,market,100902)
    conn.commit();collector.run_once(now=100903)
    e=read_event_context(conn,'bithumb','KRW-B3',now=100904)[0]
    assert e['responses']['15m']['btc']==pytest.approx(1)
    assert e['responses']['15m']['coin'] is None and e['responses']['15m']['vs_btc_pp'] is None
    assert e['price_progress']['coin']['15m']['baseline'] is None
    assert e['price_progress']['coin']['15m']['status']=='missing_baseline'
    other=read_event_context(conn,'upbit','KRW-B3',now=100904)[0]
    assert other['price_progress']['coin']['15m']['baseline']['price']==100
    assert other['price_progress']['btc']['15m']['baseline'] is None
    conn.close()


def test_late_or_future_price_does_not_become_an_eligible_baseline_or_target(tmp_path):
    path=tmp_path/'clocks.db';conn,collector=initialize(path)
    trade(conn,'KRW-B3',99500,100);trade(conn,'KRW-B3',100901,104)
    archive.capture_market(conn,'bithumb','KRW-B3',100902);conn.commit()
    e=read_event_context(conn,'bithumb','KRW-B3',now=100903)[0]
    assert e['price_progress']['coin']['15m']['baseline'] is None
    assert e['price_progress']['coin']['15m']['target']['price']==104
    assert e['responses']['15m']['coin'] is None
    conn.execute(f"UPDATE {archive.TABLE} SET archived_at=100910 WHERE point='15m'");conn.commit()
    e=read_event_context(conn,'bithumb','KRW-B3',now=100909)[0]
    assert e['price_progress']['coin']['15m']['target'] is None
    conn.close()


def test_completed_response_keeps_its_actual_prices_after_archive_improves(tmp_path):
    path=tmp_path/'priority.db';conn,collector=initialize(path)
    trade(conn,'KRW-B3',99990,100);trade(conn,'KRW-B3',100901,105)
    collector.run_once(now=100902)
    trade(conn,'KRW-B3',99999,102)
    archive.capture_market(conn,'bithumb','KRW-B3',100903);conn.commit()
    e=read_event_context(conn,'bithumb','KRW-B3',now=100904)[0]
    assert e['responses']['15m']['coin']==pytest.approx(5)
    assert e['responses']['15m']['observations']['coin']['baseline_price']==100
    assert e['price_progress']['coin']['1h']['baseline']['price']==100
    conn.execute(f'DROP TABLE {archive.TABLE}');conn.commit()
    legacy=read_event_context(conn,'bithumb','KRW-B3',now=100904)[0]
    assert legacy['responses']==e['responses']
    conn.close()


def test_read_only_http_exposes_partial_prices_and_full_recent_history_fits_transport(tmp_path):
    path=tmp_path/'workspace.db';conn,collector=initialize(path)
    fixture_db(path)
    # All mutations below are confined to this synthetic temporary DB.
    conn.execute('DELETE FROM research_intelligence_events');conn.commit()
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        if table.startswith('strategy_lab') and 'market' in {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}:
            conn.execute(f'UPDATE "{table}" SET market=? WHERE market=?',('KRW-B3','KRW-BTC'))
    conn.commit()
    now=time.time();stamp=now-5
    _insert_event(path,event_id='pending',event_ts=stamp)
    trade(conn,'KRW-B3',stamp-1,100)
    collector.run_once(now=now)
    server=ThreadingHTTPServer(('127.0.0.1',0),handler(path,fixture=True))
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        client=http.client.HTTPConnection('127.0.0.1',server.server_port)
        client.request('GET','/api/market-detail?exchange=bithumb&market=KRW-B3')
        response=client.getresponse();payload=json.loads(response.read());assert response.status==200
        e=payload['detail']['data']['strategy_lab']['events'][0]
        assert e['event_id']=='pending' and e['price_progress']['coin']['15m']['baseline']['price']==100
        assert e['responses']['15m']['coin'] is None
        client.request('POST','/api/market-detail',body='{}')
        response=client.getresponse();response.read();assert response.status==405
        client.close()
    finally:
        server.shutdown();server.server_close();worker.join()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    # Fill the recent-history window with completed coin/BTC/ETH observations.
    for n in range(20):
        stamp=now-86500-n*20000
        _insert_event(path,event_id=f'past-{n:02d}',event_ts=stamp)
        for market in ('KRW-B3','KRW-BTC','KRW-ETH'):
            trade(conn,market,stamp-1,100)
            for _,seconds in archive.HORIZONS:
                trade(conn,market,stamp+seconds+1,105)
    collector=IntelligenceEventResponseCollector(conn,benchmarks=collector.benchmarks,event_lookback_seconds=7*86400)
    collector.run_once(now=now)
    conn.close()
    lab=read_strategy_lab_market('bithumb','KRW-B3',path)
    assert lab['status']=='ok' and len(lab['events'])==20
    assert sum(e['responses']['1d']['coin'] is not None for e in lab['events'])==19
    item=dict(key='bithumb|KRW-B3|adaptive',exchange='bithumb',market='KRW-B3',strategy='adaptive',detail={'strategy_lab':lab})
    items=detail_items(item)
    assert all(len(json.dumps({'details':[i]},ensure_ascii=False,separators=(',',':')).encode())<=165000 for i in items)
    assert items[-1]['detail']['strategy_lab']['events']==lab['events']
