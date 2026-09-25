import hashlib
import json
import sqlite3
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from b3_trader.holding_quotes import HoldingQuotes, parse_tickers, public_markets, request_tickers
from b3_trader.holdings_review import read_holdings
from b3_trader import strategy_journal_review as review


def holdings_db(path):
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE manual_holdings(market TEXT,volume REAL,avg_price REAL,updated_ts REAL,exchange TEXT)')
        c.executemany('INSERT INTO manual_holdings VALUES(?,?,?,?,?)', [
            ('KRW-B3',10,100,950,'bithumb'),('KRW-ETH/BTC',2,.03,950,'bithumb'),
            ('KRW-UP',3,50,950,None),('KRW-DEXE',0,500,950,'bithumb')])


def test_native_quote_converts_only_exact_exchange_and_keeps_pnl_in_btc(tmp_path):
    path=tmp_path/'actual.db';holdings_db(path)
    prices=[dict(exchange='bithumb',market='KRW-B3',price=120,signal_ts=999),
            dict(exchange='bithumb',market='BTC-ETH',price=.04,signal_ts=999),
            dict(exchange='upbit',market='KRW-BTC',price=200000000,signal_ts=999)]
    data=read_holdings(path,prices,now=1000)
    eth=next(h for h in data['holdings'] if h['symbol']=='ETH')
    assert eth['current_price']==.04 and eth['value_quote']==.08
    assert eth['unrealized_pnl_quote']==pytest.approx(.02)
    assert eth['value_krw'] is None and data['priced_count']==1
    prices.append(dict(exchange='bithumb',market='KRW-BTC',price=100000000,signal_ts=998))
    data=read_holdings(path,prices,now=1000)
    eth=next(h for h in data['holdings'] if h['symbol']=='ETH')
    assert eth['value_krw']==8000000 and eth['conversion_ts']==998
    assert data['known_value_krw']==8001200 and data['priced_count']==2
    assert data['value_krw'] is None and data['pnl_krw'] is None
    assert read_holdings(path,prices,now=2400)['valuation_stale'] is True
    prices.append(dict(exchange='bithumb',market='BTC-ETH',price=999,signal_ts=1001))
    assert next(h for h in read_holdings(path,prices,now=1000)['holdings'] if h['symbol']=='ETH')['current_price']==.04
    with sqlite3.connect(path) as c:c.execute("DELETE FROM manual_holdings WHERE exchange IS NULL")
    complete=read_holdings(path,prices,now=1000)
    assert complete['valuation_complete'] and complete['value_krw']==8001200
    assert complete['pnl_krw'] is None  # no acquisition-time BTC/KRW rate


def test_public_requests_contain_only_known_active_market_codes(tmp_path):
    path=tmp_path/'actual.db';holdings_db(path)
    assert public_markets(read_holdings(path,[])['holdings'])=={'bithumb':['BTC-ETH','KRW-B3','KRW-BTC']}
    assert public_markets([{'exchange':'bithumb','valid':True,'api_market':'https://bad.invalid'}])=={}
    with pytest.raises(ValueError):request_tickers('unknown',['KRW-BTC'])
    with pytest.raises(ValueError):request_tickers('bithumb',['KRW-BTC&secret=x'])


def test_bad_duplicate_future_or_other_market_rows_never_become_prices():
    row=dict(market='BTC-ETH',trade_price=.04,trade_timestamp=999000)
    assert parse_tickers('bithumb',['BTC-ETH'],[row],1000)[0]['signal_ts']==999
    for value in (0,-1,'NaN',True,None):
        assert parse_tickers('bithumb',['BTC-ETH'],[{**row,'trade_price':value}],1000)==[]
    for payload in ([row,row],[{**row,'trade_timestamp':1001000}],[{**row,'market':'KRW-ETH'}]):
        assert parse_tickers('bithumb',['BTC-ETH'],payload,1000)==[]


def test_clicks_are_throttled_and_failure_retains_original_clock():
    calls=[]
    def fetch(exchange,markets):
        calls.append((exchange,markets))
        if len(calls)>1:raise OSError('offline')
        return [dict(market='BTC-ETH',trade_price=.04,trade_timestamp=999000)]
    cache=HoldingQuotes(fetch)
    h=[dict(valid=True,exchange='bithumb',api_market='BTC-ETH')]
    cache.refresh(h);cache.refresh(h)
    assert len(calls)==1 and cache.snapshot()[1]['status']=='partial'
    saved=cache.snapshot()[0];cache.last_attempt=-1e20;cache.refresh(h)
    assert cache.snapshot()[0]==saved and cache.snapshot()[1]['received']==0


def test_http_price_action_updates_valuation_without_db_mutation_or_background_network(tmp_path):
    paper,actual=tmp_path/'paper.db',tmp_path/'actual.db';holdings_db(actual)
    now=time.time()
    with sqlite3.connect(paper) as c:
        c.execute('CREATE TABLE research_signals_mx(exchange TEXT,market TEXT,strategy TEXT,price REAL,ts REAL)')
        c.execute("INSERT INTO research_signals_mx VALUES('bithumb','KRW-B3','adaptive',120,?)",(now-10,))
    calls=[]
    def fetch(exchange,markets):
        calls.append((exchange,markets))
        return [dict(market=m,trade_price={'KRW-B3':125,'KRW-BTC':100000000,'BTC-ETH':.04}[m],trade_timestamp=(now-1)*1000) for m in markets]
    cache=HoldingQuotes(fetch);hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (paper,actual)}
    server=review.ThreadingHTTPServer(('127.0.0.1',0),review.handler(paper,holdings_path=actual,quotes=cache))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(url+'/api/review-state') as r:assert json.load(r)['local_holdings']['priced_count']==1
        assert not calls
        for headers in ({'Origin':'https://example.com'},{'Host':'example.com'},{'Sec-Fetch-Site':'cross-site'}):
            with pytest.raises(HTTPError) as exc:urlopen(Request(url+'/api/holding-quotes',headers=headers))
            assert exc.value.code==403
        assert not calls
        with urlopen(url+'/api/holding-quotes') as r:assert json.load(r)['status']=='complete'
        with urlopen(url+'/api/review-state') as r:data=json.load(r)['local_holdings']
        assert data['priced_count']==2 and data['known_value_krw']==8001250
        assert len(calls)==1
        for p,digest in hashes.items():assert hashlib.sha256(p.read_bytes()).hexdigest()==digest
    finally:
        server.shutdown();thread.join(2);server.server_close()
