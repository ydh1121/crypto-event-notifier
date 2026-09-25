import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import sqlite3
import threading
import time
from urllib.parse import urlencode

from b3_trader.strategy_journal_review import handler, read_detail
from b3_trader.tests.test_strategy_lab_journal import fixture_db
from b3_trader.tests.test_manual_planning import draft, request


def test_real_http_plan_restart_fills_and_scoped_paper_comparison(tmp_path):
    paper,actual=tmp_path/'paper.db',tmp_path/'holdings.db'
    fixture_db(paper)
    with sqlite3.connect(actual) as c:
        c.execute('CREATE TABLE manual_holdings(market TEXT PRIMARY KEY,volume REAL,avg_price REAL,exchange TEXT,updated_ts REAL)')
        c.execute("INSERT INTO manual_holdings VALUES ('KRW-BTC',10,100,NULL,1)")
    original=hashlib.sha256(paper.read_bytes()).hexdigest()
    a=next(a for a in read_detail(paper,'bithumb','KRW-BTC')['data']['strategy_lab']['experiments'] if a['style']=='aggressive')
    scope=dict(exchange='bithumb',market='KRW-BTC',experiment=a['experiment_id'])

    def serve():
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(paper,holdings_path=actual,confirmed_exchange='bithumb',enable_planning=True))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        return server,thread
    server,thread=serve()
    def call(method='GET',body=None,headers=None,query=None,path='/api/manual-planning'):
        connection=HTTPConnection('127.0.0.1',server.server_port,timeout=10)
        defaults={'Origin':f'http://127.0.0.1:{server.server_port}','Content-Type':'application/json'}
        if headers:defaults.update(headers)
        connection.request(method,path+('?' + urlencode(query or scope) if method=='GET' else ''),json.dumps(body) if body is not None else None,defaults)
        response=connection.getresponse();status=response.status;result=json.loads(response.read());connection.close()
        return status,result
    try:
        before=actual.read_bytes()
        status,result=call();assert status==200 and result['plan'] is None
        assert actual.read_bytes()==before
        body={**scope,**request(expected_revision=0,draft=draft()),'action':'save'}
        assert call('POST',body)[0]==403
        token={'X-Planning-Token':result['csrf_token']}
        assert call('POST',body,{**token,'Origin':'https://evil.example'})[0]==403
        assert call('POST',body,{**token,'Sec-Fetch-Site':'cross-site'})[0]==403
        assert call('POST',body,{**token,'Host':'other.example'})[0]==403
        assert call('POST',body,{**token,'Content-Type':'text/plain'})[0]==422
        assert call('POST',{**body,'exchange':'upbit'},token)[0]==422
        assert call('POST',{**body,'experiment':'fake'},token)[0]==422
        status,result=call('POST',body,token);assert status==200 and result['plan_revision']==1
        server.shutdown();server.server_close();thread.join()
        server,thread=serve()
        status,result=call();assert status==200 and result['plan']['draft']==draft()
        token={'X-Planning-Token':result['csrf_token']}
        for side,price,ts in [('buy','100',time.time()-2),('sell','120',time.time()-1)]:
            status,result=call('POST',{**scope,'action':'fill',**request(expected_revision=result['ledger_revision'],plan_revision=1,
                fill=dict(side=side,price=price,volume='2',fee='1',ts=ts))},token)
            assert status==200,result
        assert result['summary']['realized']==38
        assert result['comparison']['manual']['closed']==1
        assert result['comparison']['paper'] is not None
        assert result['comparison']['paper']['closed']==0
        # A real closeout never makes the saved plan/ledger inaccessible.
        with sqlite3.connect(actual) as c:
            c.execute('UPDATE manual_holdings SET volume=0,updated_ts=2')
        status,reopened=call();assert status==200
        assert reopened['plan_revision']==1 and reopened['summary']['realized']==38
        assert len(reopened['records'])==2
        # Correcting a record in the archive retains the original canceled row.
        status,corrected=call('POST',{**scope,'action':'void',**request(expected_revision=reopened['ledger_revision'],
            target=reopened['records'][-1]['id'])},token)
        assert status==200 and corrected['records'][-1]['voided'] is True
        assert corrected['summary']['volume']==2
        assert call('DELETE')[0]==405
        with sqlite3.connect(actual) as c:
            assert c.execute('SELECT volume,avg_price,exchange FROM manual_holdings').fetchone()==(0,100,None)
        assert hashlib.sha256(paper.read_bytes()).hexdigest()==original
    finally:
        server.shutdown();server.server_close();thread.join()


def test_same_file_as_paper_cannot_become_manual_writer(tmp_path):
    import pytest
    with pytest.raises(ValueError):handler(tmp_path/'same.db',holdings_path=tmp_path/'same.db',enable_planning=True)
