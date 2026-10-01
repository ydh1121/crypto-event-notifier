from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import sqlite3
import threading
import uuid

import pytest

from b3_trader import holding_registration as registration
from b3_trader.holdings_review import read_holdings
from b3_trader.manual_trading import PlanningError
from b3_trader.strategy_journal_review import handler


def payload(**changes):
    return {'exchange':'bithumb','symbol':'XRP','quote_currency':'KRW','volume':'20.25','avg_price':'1200.5',
            'request_id':str(uuid.uuid4()),**changes}


@pytest.fixture
def journal(tmp_path):
    path=tmp_path/'holdings.db'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE manual_holdings(market TEXT PRIMARY KEY,volume REAL,avg_price REAL,exchange TEXT,updated_ts REAL)')
        c.executemany('INSERT INTO manual_holdings VALUES (?,?,?,?,?)',[
            ('KRW-B3',10,.8,None,1),('KRW-CLOSED',0,0,'bithumb',2),('KRW-OTHER',2,3,'upbit',4)])
        c.execute('CREATE TABLE averaging_plans(market TEXT PRIMARY KEY,rows_json TEXT,updated_ts REAL)')
        c.execute("INSERT INTO averaging_plans VALUES ('KRW-B3','[]',1)")
    return path


def test_add_backup_restart_retry_and_btc_identity_preserve_existing_records(journal):
    before=journal.read_bytes()
    body=payload(symbol=' xrp ')
    saved=registration.HoldingRegistration(journal).add(body,'bithumb')
    assert saved['key']=='bithumb|KRW-XRP|KRW'
    backups=list((journal.parent/'managed-backups').glob('journal-*/data.sqlite3'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as c:
        assert c.execute('SELECT COUNT(*) FROM manual_holdings').fetchone()[0]==3
        assert c.execute('PRAGMA quick_check').fetchone()==('ok',)
    restart=registration.HoldingRegistration(journal)
    assert restart.add(body,'bithumb')==saved
    assert len(list((journal.parent/'managed-backups').glob('journal-*/data.sqlite3')))==1
    with pytest.raises(PlanningError,match='같은 요청'):
        restart.add({**body,'volume':'21'},'bithumb')
    restart.add(payload(symbol='ETH',quote_currency='BTC',volume='2',avg_price='.03'),'bithumb')
    rows=read_holdings(journal,[{'exchange':'bithumb','market':'KRW-ETH','price':4_000_000,'signal_ts':9}],now=10,confirmed_exchange='bithumb')['holdings']
    eth=next(h for h in rows if h['symbol']=='ETH')
    assert eth['market']=='KRW-ETH/BTC' and eth['api_market']=='BTC-ETH'
    assert eth['avg_price']==.03 and eth['value_krw']==8_000_000
    with sqlite3.connect(journal) as c:
        assert c.execute("SELECT volume,avg_price,exchange,updated_ts FROM manual_holdings WHERE market='KRW-B3'").fetchone()==(10,.8,None,1)
        assert c.execute("SELECT * FROM averaging_plans").fetchall()==[('KRW-B3','[]',1)]
        assert c.execute('SELECT COUNT(*) FROM holding_mutation_receipts').fetchone()[0]==2
    assert journal.read_bytes()!=before


@pytest.mark.parametrize('changes',[
    {'volume':''},{'volume':0},{'volume':True},{'volume':-1},{'volume':'nan'},
    {'avg_price':''},{'avg_price':0},{'avg_price':None},{'avg_price':'inf'},
    {'volume':'1e308','avg_price':'1e308'},{'symbol':'<script>'},{'symbol':'BTC','quote_currency':'BTC'},
    {'quote_currency':'USD'},{'exchange':'upbit'},{'request_id':'bad'},
    {'symbol':'B3'},{'symbol':'CLOSED'},{'symbol':'OTHER'},
])
def test_invalid_or_existing_holdings_never_overwrite_or_add_schema(journal,changes):
    before=hashlib.sha256(journal.read_bytes()).hexdigest()
    with pytest.raises(PlanningError):registration.HoldingRegistration(journal).add(payload(**changes),'bithumb')
    assert hashlib.sha256(journal.read_bytes()).hexdigest()==before
    assert not (journal.parent/'managed-backups').exists()


def test_backup_failure_and_missing_journal_do_not_write(journal,tmp_path,monkeypatch):
    before=journal.read_bytes()
    def fail(*args):raise OSError('backup unavailable')
    monkeypatch.setattr(registration,'backup_journal',fail)
    with pytest.raises(OSError):registration.HoldingRegistration(journal).add(payload())
    assert journal.read_bytes()==before
    missing=tmp_path/'absent.db'
    with pytest.raises(PlanningError):registration.HoldingRegistration(missing).add(payload())
    assert not missing.exists()


def test_concurrent_registrations_insert_one_row_and_one_receipt(journal):
    def add(_):
        try:
            registration.HoldingRegistration(journal).add(payload(),'bithumb')
            return 200
        except PlanningError as e:return e.status
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(add,range(2)))==[200,409]
    with sqlite3.connect(journal) as c:
        assert c.execute("SELECT COUNT(*) FROM manual_holdings WHERE market='KRW-XRP'").fetchone()==(1,)
        assert c.execute('SELECT COUNT(*) FROM holding_mutation_receipts').fetchone()==(1,)


def test_missing_exchange_column_added_after_backup(tmp_path):
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE manual_holdings(market TEXT PRIMARY KEY,volume REAL,avg_price REAL,updated_ts REAL)')
        c.execute("INSERT INTO manual_holdings VALUES ('KRW-B3',1,2,3)")
    registration.HoldingRegistration(path).add(payload(),'bithumb')
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT volume,avg_price,exchange,updated_ts FROM manual_holdings WHERE market='KRW-B3'").fetchone()==(1,2,None,3)
    with sqlite3.connect(next((path.parent/'managed-backups').glob('journal-*/data.sqlite3'))) as c:
        assert 'exchange' not in {r[1] for r in c.execute('PRAGMA table_info(manual_holdings)')}


@contextmanager
def serving(paper,journal,enabled):
    server=ThreadingHTTPServer(('127.0.0.1',0),handler(paper,holdings_path=journal,confirmed_exchange='bithumb',enable_planning=enabled))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def call(method='GET',body=None,headers=None,path='/api/holding-registration'):
        c=HTTPConnection('127.0.0.1',server.server_port,timeout=10)
        options={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{server.server_port}',**(headers or {})}
        c.request(method,path,json.dumps(body) if body is not None else None,options)
        r=c.getresponse();value=(r.status,json.loads(r.read()));c.close();return value
    try:yield call
    finally:server.shutdown();server.server_close();thread.join()


def test_http_add_empty_portfolio_reopen_and_read_only_security(tmp_path):
    paper,journal=tmp_path/'paper.db',tmp_path/'holdings.db'
    with sqlite3.connect(paper) as c:
        c.execute('CREATE TABLE research_signals_mx(exchange TEXT,market TEXT,price REAL,ts REAL,strategy TEXT)')
        c.execute("INSERT INTO research_signals_mx VALUES ('bithumb','KRW-XRP',1300,10,'adaptive')")
    with sqlite3.connect(journal) as c:c.execute('CREATE TABLE manual_holdings(market TEXT PRIMARY KEY,volume REAL,avg_price REAL,exchange TEXT,updated_ts REAL)')
    original=hashlib.sha256(paper.read_bytes()).hexdigest();body=payload()
    with serving(paper,journal,True) as call:
        status,state=call(path='/api/review-state');assert status==200 and state['local_holdings']['holding_count']==0
        before=journal.read_bytes();status,token=call();assert status==200
        assert journal.read_bytes()==before
        header={'X-Planning-Token':token['csrf_token']}
        assert call('POST',body)[0]==403
        for extra in [{'Origin':'https://other.example'},{'Host':'other.example'},{'Sec-Fetch-Site':'cross-site'}]:
            assert call('POST',body,{**header,**extra})[0]==403
        assert call('POST',body,{**header,'Content-Type':'text/plain'})[0]==422
        status,saved=call('POST',body,header)
        assert status==200 and saved['holding_key']=='bithumb|KRW-XRP|KRW'
        h=saved['holdings']['holdings'][0]
        assert h['volume']==20.25 and h['avg_price']==1200.5 and h['current_price']==1300
        assert saved['holdings']['holding_count']==1
    with serving(paper,journal,True) as call:
        status,state=call(path='/api/review-state');assert status==200 and state['local_holdings']['holding_count']==1
        _,token=call();header={'X-Planning-Token':token['csrf_token']}
        assert call('POST',body,header)[0]==200
        assert call('POST',payload(),header)[0]==409
    with serving(paper,journal,False) as call:
        assert call('POST',payload())[0]==405
        assert call()[0]==404
    assert hashlib.sha256(paper.read_bytes()).hexdigest()==original
