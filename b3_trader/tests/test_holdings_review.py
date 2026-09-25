import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from b3_trader.holdings_review import read_holdings, resolve_holdings_path
from b3_trader import strategy_journal_review as review


def journal(path, rows, *, legacy=False):
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE manual_holdings(market TEXT PRIMARY KEY,volume REAL,avg_price REAL,updated_ts REAL'+(')' if legacy else ',exchange TEXT)'))
        c.executemany('INSERT INTO manual_holdings VALUES('+','.join('?' for _ in range(4 if legacy else 5))+')',rows)


def prices():
    return [dict(exchange='bithumb',market='KRW-B3',price=120,signal_ts=999),
            dict(exchange='upbit',market='KRW-B3',price=9999,signal_ts=999),
            dict(exchange='bithumb',market='BTC-B3',price=.000001,signal_ts=999)]


def test_separate_journal_uses_exact_exchange_and_quote_and_does_not_mutate(tmp_path):
    path=tmp_path/'holdings.db'
    journal(path,[('KRW-B3',10,100,950,'bithumb'),('KRW-B3/BTC',2,.000002,950,'bithumb'),
                  ('KRW-DEXE',0,500,950,'bithumb'),('KRW-UNKNOWN',3,50,950,None)])
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    result=read_holdings(path,prices(),now=1000)
    rows={h['market']:h for h in result['holdings']}
    assert rows['KRW-B3']['current_price']==120
    assert rows['KRW-B3']['unrealized_pnl_quote']==200
    assert rows['KRW-B3/BTC']['value_quote']==.000002
    assert rows['KRW-B3/BTC']['planning_available'] is False
    assert rows['KRW-DEXE']['closed'] is True
    assert rows['KRW-UNKNOWN']['current_price'] is None
    assert rows['KRW-UNKNOWN']['planning_available'] is False
    assert result['holding_count']==3 and result['closed_count']==1
    assert rows['KRW-B3/BTC']['valuation_basis']=='krw_market'
    assert rows['KRW-B3/BTC']['value_krw']==240
    assert result['known_value_krw']==1440 and result['value_krw'] is None
    assert result['pnl_krw'] is None and result['valuation_complete'] is False
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


def test_missing_or_invalid_holdings_never_become_empty_zero_account(tmp_path):
    missing=tmp_path/'missing.db'
    assert read_holdings(missing,[])['status']=='db_missing'
    assert not missing.exists()
    empty=tmp_path/'empty.db';sqlite3.connect(empty).close()
    assert read_holdings(empty,[])['status']=='table_missing'
    assert read_holdings(None,[])['status']=='configuration_required'
    legacy=tmp_path/'legacy.db';journal(legacy,[('KRW-B3',10,100,950)],legacy=True)
    h=read_holdings(legacy,prices(),now=1000)['holdings'][0]
    assert h['exchange'] is None and h['current_price'] is None
    invalid=tmp_path/'invalid.db';journal(invalid,[('KRW-B3','',100,950,'bithumb')])
    result=read_holdings(invalid,prices(),now=1000)
    assert result['holdings'][0]['volume'] is None
    assert result['holdings'][0]['closed'] is False
    assert result['value_krw'] is None


def test_stale_future_missing_and_real_zero_pnl_remain_distinct(tmp_path):
    path=tmp_path/'holdings.db';journal(path,[('KRW-B3',10,120,950,'bithumb')])
    result=read_holdings(path,prices(),now=1000)
    assert result['pnl_krw']==0 and result['valuation_complete'] is True
    assert read_holdings(path,prices(),now=2400)['valuation_stale'] is True
    for rows in ([],[dict(exchange='upbit',market='KRW-B3',price=120,signal_ts=999)],
                 [dict(exchange='bithumb',market='KRW-B3',price=120,signal_ts=1001)]):
        h=read_holdings(path,rows,now=1000)['holdings'][0]
        assert h['current_price'] is None and h['unrealized_pnl_pct'] is None


def test_settings_path_resolution_never_uses_paper_as_holdings(tmp_path,monkeypatch):
    monkeypatch.delenv('B3_JOURNAL_DB',raising=False)
    checkout=tmp_path/'project';(checkout/'b3_trader/data').mkdir(parents=True)
    paper=checkout/'b3_trader/data/auto_demo.sqlite3'
    path,source=resolve_holdings_path(paper)
    assert path==checkout/'b3_trader/data/crypto_trader.sqlite3' and source=='default'
    (checkout/'.env').write_text('UNRELATED_SECRET=do-not-read-out\nB3_JOURNAL_DB="custom journal.db" # path\n')
    assert resolve_holdings_path(paper)==(checkout/'custom journal.db','project_setting')
    monkeypatch.setenv('B3_JOURNAL_DB','runtime.db')
    assert resolve_holdings_path(paper)==(checkout/'runtime.db','environment')
    assert resolve_holdings_path(paper,tmp_path/'override.db')==(tmp_path/'override.db','explicit')
    monkeypatch.delenv('B3_JOURNAL_DB')
    (checkout/'.env').write_text('B3_JOURNAL_DB=${OTHER}/journal.db\n')
    assert resolve_holdings_path(paper)==(None,'configuration_required')
    assert resolve_holdings_path(tmp_path/'unknown.db')==(None,'configuration_required')
    assert not path.exists()


def test_read_only_http_joins_separate_journal_rejects_cross_site_and_mutations(tmp_path):
    paper=tmp_path/'paper.db';actual=tmp_path/'actual.db'
    with sqlite3.connect(paper) as c:
        c.execute('CREATE TABLE research_signals_mx(exchange TEXT,market TEXT,strategy TEXT,price REAL,ts REAL)')
        c.execute("INSERT INTO research_signals_mx VALUES('bithumb','KRW-B3','adaptive',120,999)")
    journal(actual,[('KRW-B3',10,100,950,'bithumb')])
    hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (paper,actual)}
    server=review.ThreadingHTTPServer(('127.0.0.1',0),review.handler(paper,holdings_path=actual))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}/'
    try:
        with urlopen(url+'api/review-state') as response:
            data=json.load(response)
        h=data['local_holdings']['holdings'][0]
        assert h['volume']==10 and h['avg_price']==100 and h['current_price']==120
        assert data['local_holdings']['status']=='read'
        assert data['private_visible'] is False
        for request,status in [(Request(url+'api/review-state',headers={'Origin':'https://example.com'}),403),
                               (Request(url+'api/review-state',data=b'{}',method='POST'),405)]:
            with pytest.raises(HTTPError) as exc:urlopen(request)
            assert exc.value.code==status
        with urlopen(url) as response:assert '실전 계획' in response.read().decode()
    finally:
        server.shutdown();thread.join(2);server.server_close()
    for p,digest in hashes.items():assert hashlib.sha256(p.read_bytes()).hexdigest()==digest


@pytest.mark.parametrize('suffix',['','-wal','-shm'])
def test_report_cannot_overwrite_holdings_database_or_sidecars(tmp_path,monkeypatch,suffix):
    paper=tmp_path/'paper.db';paper.touch()
    actual=tmp_path/'actual.db';journal(actual,[])
    monkeypatch.setattr(sys,'argv',['review','--db',str(paper),'--holdings-db',str(actual),'--report',str(actual)+suffix,'--report-only'])
    with pytest.raises(SystemExit):review.main()
    assert actual.stat().st_size>0


def test_holdings_path_cannot_alias_paper(tmp_path,monkeypatch):
    path=tmp_path/'paper.db';path.touch()
    monkeypatch.setattr(sys,'argv',['review','--db',str(path),'--holdings-db',str(path)])
    with pytest.raises(SystemExit):review.main()


def test_owner_confirmed_exchange_applies_only_to_holdings_projection_without_changing_journal(tmp_path):
    path=tmp_path/'holdings.db'
    journal(path,[('KRW-B3',10,100,950,'upbit'),('KRW-UP',2,50,950,None),('KRW-DEXE',0,5,950,None)])
    quotes=prices()+[dict(exchange='bithumb',market='KRW-UP',price=60,signal_ts=999)]
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    original=read_holdings(path,quotes,now=1000)
    assert original['holdings'][0]['exchange']=='upbit'
    confirmed=read_holdings(path,quotes,now=1000,confirmed_exchange='bithumb')
    active=[h for h in confirmed['holdings'] if not h['closed']]
    assert all(h['exchange']=='bithumb' and h['exchange_source']=='owner_confirmed' for h in active)
    assert confirmed['priced_count']==2 and confirmed['value_krw']==1320
    assert confirmed['closed_count']==1
    assert confirmed['holdings'][0]['stored_exchange']=='upbit'
    assert all(h['planning_available'] for h in active)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    assert read_holdings(path,quotes,now=1000)==original
