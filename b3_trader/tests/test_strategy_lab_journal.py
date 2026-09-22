from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from b3_trader.strategy_lab import StrategyLabStore, STYLE_SPECS
from b3_trader.strategy_lab_market import read_strategy_lab_market
from b3_trader.strategy_lab_transport import detail_items
from b3_trader.strategy_lab_journal import reconcile_account
from b3_trader.strategy_lab_plan import project_plan
from b3_trader.strategy_lab_context import read_coin_context
from b3_trader.tests.test_strategy_lab import _memory
from b3_trader.multi_exchange_store import MultiExchangeStore


def fixture_db(path: Path, *, cycles: int = 2) -> None:
    mx = MultiExchangeStore(path)
    for i in range(cycles):
        _memory(mx, idx=i*3+1, price=100)
        _memory(mx, idx=i*3+2, price=95)
        _memory(mx, idx=i*3+3, price=125)
    _memory(mx, idx=cycles*3+1, price=100)
    mx.close()
    lab = StrategyLabStore(path)
    lab.process_exchange('bithumb', limit=10000)
    lab.close()


def test_read_only_complete_scoped_ledger_and_fee_reconciliation(tmp_path):
    db = tmp_path/'paper.db'; fixture_db(db, cycles=80)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    data = read_strategy_lab_market('bithumb', 'KRW-BTC', db)
    assert data['status'] == 'ok'
    assert len(data['experiments']) == 6
    a = next(e for e in data['experiments'] if e['style']=='aggressive')
    assert a['journal']['total'] > 80
    assert a['reconciliation']['matches'] is True
    assert a['reconciliation']['drawdown_reproduced'] is False
    assert a['volume'] > 0
    assert a['win_rate_pct'] == pytest.approx(a['wins']/a['closed_trades']*100)
    assert a['plan']['entries'][0]['price'] == pytest.approx(a['avg_price']*.975)
    assert a['plan']['exits'][0]['weight_pct'] == 100
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert not read_strategy_lab_market('upbit', 'KRW-BTC', db)['experiments']
    assert not read_strategy_lab_market('bithumb', 'KRW-B3', db)['experiments']


def test_missing_db_and_tables_are_unknown_not_zero(tmp_path):
    missing = tmp_path/'absent.db'
    assert read_strategy_lab_market('bithumb','KRW-B3',missing)['status']=='unavailable'
    assert not missing.exists()
    conn=sqlite3.connect(missing);conn.close()
    assert read_strategy_lab_market('bithumb','KRW-B3',missing)['status']=='unavailable'


def test_revision_changes_on_account_or_journal_and_corruption_fails_closed(tmp_path):
    db=tmp_path/'paper.db';fixture_db(db)
    before=read_strategy_lab_market('bithumb','KRW-BTC',db)['experiments'][0]
    with sqlite3.connect(db) as c:
        c.execute('UPDATE strategy_lab_accounts SET cash_krw=cash_krw+10 WHERE experiment_id=?',(before['experiment_id'],))
    after=read_strategy_lab_market('bithumb','KRW-BTC',db)['experiments'][0]
    assert after['revision'] != before['revision']
    assert after['reconciliation']['matches'] is False
    assert 'cash_krw' in after['reconciliation']['differences']


def test_transport_chunks_preserve_every_fill_and_are_stable(tmp_path):
    db=tmp_path/'paper.db';fixture_db(db,cycles=80)
    lab=read_strategy_lab_market('bithumb','KRW-BTC',db)
    item=dict(key='bithumb|KRW-BTC|adaptive',exchange='bithumb',market='KRW-BTC',strategy='adaptive',source_ts=1,detail={'strategy_lab':lab})
    items=detail_items(item,max_bytes=60000)
    assert len(items)>1
    assert items[-1]['strategy']=='adaptive'
    chunks={i['strategy']:i['detail'] for i in items[:-1]}
    for original,projected in zip(lab['experiments'],items[-1]['detail']['strategy_lab']['experiments']):
        journal=projected['journal']
        rows=journal.get('rows')
        if rows is None: rows=[r for ref in journal['chunks'] for r in chunks[ref['strategy']]['rows']]
        assert rows==original['journal']['rows']
        assert projected['revision']==original['revision']
    assert detail_items(item,max_bytes=60000)==items
    assert all(len(json.dumps(i,ensure_ascii=False).encode())<170000 for i in items)


def test_plan_shares_rules_but_never_mutates_input():
    account=dict(volume=100,avg_price=100,cash_krw=9000000,buy_count=1,entry_ts=10,entry_bias=0,weight_multiplier=1,status='running')
    memory=dict(id=2,ts=1000,signal_ts=1000,price=114.01,regime_score=80,entry_score=80,opportunity_score=80,volatility_pct=1,pullback_pct=5)
    before=json.dumps([account,memory],sort_keys=True)
    p=project_plan(account,memory,STYLE_SPECS['aggressive'])
    assert p['action']=='sell'
    assert p['exits'][0]['price']==pytest.approx(114)
    assert p['entries'][0]['price']==pytest.approx(97.5)
    assert p['entries'][1]['basis']=='conditional_recalculation'
    assert json.dumps([account,memory],sort_keys=True)==before


def test_zero_trades_has_no_win_rate(tmp_path):
    db=tmp_path/'paper.db';mx=MultiExchangeStore(db);mx.close();lab=StrategyLabStore(db)
    a=lab._blank_account('bithumb|aggressive|v1','bithumb','KRW-B3')
    lab._upsert_account(a);lab.conn.commit();lab.close()
    item=read_strategy_lab_market('bithumb','KRW-B3',db)['experiments'][0]
    assert item['win_rate_pct'] is None
    assert item['reconciliation']['matches']
    assert item['source_ts'] is None


def test_aligned_relative_returns_never_substitute_missing_benchmark(tmp_path):
    db=tmp_path/'paper.db'
    # Minimal actual read schema; fixture only, never the runtime DB.
    conn=sqlite3.connect(db);conn.row_factory=sqlite3.Row
    conn.execute('CREATE TABLE research_market_ohlcv_mx(exchange,market,timeframe,candle_ts,close,is_closed)')
    conn.executemany('INSERT INTO research_market_ohlcv_mx VALUES(?,?,?,?,?,?)',[
        ('bithumb','KRW-B3','1h',0,100,1),('bithumb','KRW-B3','1h',3600,110,1),
        ('bithumb','KRW-BTC','1h',0,100,1),('bithumb','KRW-BTC','1h',3600,105,1),
        ('upbit','KRW-ETH','1h',0,100,1),('upbit','KRW-ETH','1h',3600,130,1)])
    result=read_coin_context(conn,{'research_market_ohlcv_mx'},'bithumb','KRW-B3')
    row=result['relative']['windows'][0]
    assert row['coin']==pytest.approx(10)
    assert row['btc']==pytest.approx(5)
    assert row['vs_btc_pp']==pytest.approx(5)
    assert row['eth'] is None and row['vs_eth_pp'] is None
    assert result['relative']['windows'][1]['coin'] is None
    conn.close()


def test_read_only_http_roundtrip_and_mutations_rejected(tmp_path):
    from http.server import ThreadingHTTPServer
    import threading
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    from b3_trader.strategy_journal_review import handler
    db=tmp_path/'paper.db';fixture_db(db)
    before=hashlib.sha256(db.read_bytes()).hexdigest()
    server=ThreadingHTTPServer(('127.0.0.1',0),handler(db))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        data=json.load(urlopen(base+'/api/market-detail?exchange=bithumb&market=KRW-BTC'))['detail']['data']['strategy_lab']
        a=next(e for e in data['experiments'] if e['style']=='aggressive')
        ids=[];offset=0
        while offset is not None:
            from urllib.parse import urlencode
            q=urlencode(dict(exchange='bithumb',market='KRW-BTC',experiment=a['experiment_id'],revision=a['revision'],offset=offset,limit=2))
            page=json.load(urlopen(base+'/api/market-detail?'+q))['journal']
            ids.extend(t['id'] for t in page['trades']);offset=page['next_offset']
        assert len(ids)==len(set(ids))==a['journal']['total']
        for request,status in [(Request(base+'/api/market-detail',method='POST'),405),
                               (Request(base+'/',headers={'Origin':'https://example.com'}),403),
                               (Request(base+'/',headers={'Host':'example.com'}),403),
                               (Request(base+'/.env'),404)]:
            with pytest.raises(HTTPError) as exc:urlopen(request)
            assert exc.value.code==status
        assert hashlib.sha256(db.read_bytes()).hexdigest()==before
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
