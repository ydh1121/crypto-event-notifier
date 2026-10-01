from concurrent.futures import ThreadPoolExecutor
import sqlite3
import time
import uuid

import pytest

from b3_trader import holding_management as management
from b3_trader.holdings_review import read_holdings
from b3_trader.manual_trading import PlanningError
from b3_trader.tests.test_holding_registration import journal, serving

SCOPE = {'exchange':'bithumb','market':'KRW-B3','quote_currency':'KRW'}


def body(store, action='buy', scope=SCOPE, **extra):
    return {**scope,'action':action,'expected_revision':store.read(scope,'bithumb')['revision'],
            'request_id':str(uuid.uuid4()),'fill':{'ts':time.time()-10,'price':'.6','volume':'10','fee':'.1'},**extra}


def test_preview_buy_partial_full_sell_reopen_history_and_backup(journal):
    store=management.HoldingManagement(journal)
    original=journal.read_bytes();p=body(store)
    preview=store.change(p,'bithumb')
    assert preview['after']=={'volume':20,'avg_price':.705}
    assert journal.read_bytes()==original
    assert not (journal.parent/'holding-management-backups').exists()
    first=store.change(p,'bithumb',apply=True)
    assert first['after']==preview['after'] and first['realized_quote'] is None
    assert management.HoldingManagement(journal).change(p,'bithumb',apply=True)==first
    with pytest.raises(PlanningError,match='같은 요청'):
        store.change({**p,'fill':{**p['fill'],'volume':'11'}},'bithumb',apply=True)
    partial=body(store,'sell',fill={'ts':time.time()-5,'price':'1','volume':'5','fee':'.1'})
    result=store.change(partial,'bithumb',apply=True)
    assert result['after']=={'volume':15,'avg_price':.705}
    assert result['realized_quote']==pytest.approx(1.375)
    full=body(store,'sell',fill={'ts':time.time()-3,'price':'1','volume':'15','fee':'.3'})
    result=store.change(full,'bithumb',apply=True)
    assert result['after']=={'volume':0,'avg_price':0}
    assert result['realized_quote']==pytest.approx(4.125)
    holdings=read_holdings(journal,[],confirmed_exchange='bithumb')
    assert next(h for h in holdings['holdings'] if h['market']=='KRW-B3')['closed']
    assert len(store.read(SCOPE,'bithumb')['history'])==3
    store.change(body(store),'bithumb',apply=True)
    current=store.read(SCOPE,'bithumb')
    assert current['current']['volume']==10 and current['current']['avg_price']==.61
    assert len(current['history'])==4
    backup=next((journal.parent/'holding-management-backups').glob('*.sqlite3'))
    with sqlite3.connect(backup) as c:
        assert c.execute("SELECT volume,avg_price FROM manual_holdings WHERE market='KRW-B3'").fetchone()==(10,.8)
        assert c.execute('PRAGMA quick_check').fetchone()==('ok',)
    with sqlite3.connect(journal) as c:
        assert c.execute('SELECT COUNT(*) FROM manual_holdings').fetchone()==(3,)
        assert c.execute('SELECT * FROM averaging_plans').fetchall()==[('KRW-B3','[]',1)]
        assert c.execute("SELECT exchange FROM manual_holdings WHERE market='KRW-B3'").fetchone()==(None,)


def test_adjust_close_unknown_pnl_and_btc_quote_scope(journal):
    with sqlite3.connect(journal) as c:
        c.execute("INSERT INTO manual_holdings VALUES ('KRW-ETH/BTC',2,.03,'bithumb',1)")
    store=management.HoldingManagement(journal)
    btc={**SCOPE,'market':'KRW-ETH/BTC','quote_currency':'BTC'}
    fill={'ts':time.time()-1,'price':'.02','volume':'2','fee':'.0001'}
    store.change(body(store,scope=btc,fill=fill),'bithumb',apply=True)
    assert store.read(btc,'bithumb')['current']['avg_price']==pytest.approx(.025025)
    adjustment=body(store,'adjust',volume='4.5',avg_price='.7')
    result=store.change(adjustment,'bithumb',apply=True)
    assert result['after']=={'volume':4.5,'avg_price':.7} and result['realized_quote'] is None
    result=store.change(body(store,'close'),'bithumb',apply=True)
    assert result['after']=={'volume':0,'avg_price':0} and result['realized_quote'] is None
    assert len(store.read(SCOPE,'bithumb')['history'])==2
    assert len(store.read(btc,'bithumb')['history'])==1
    with pytest.raises(PlanningError):store.read({**btc,'quote_currency':'KRW'},'bithumb')
    with pytest.raises(PlanningError):store.read({**btc,'exchange':'upbit'})


@pytest.mark.parametrize('change',[
    {'action':'delete'},{'exchange':'upbit'},{'quote_currency':'BTC'},
    {'expected_revision':''},{'expected_revision':'f'*64},{'market':'KRW-MISSING'},
    {'action':'adjust','volume':'','avg_price':'1'}, {'action':'adjust','volume':'1','avg_price':'0'},
    {'action':'adjust','volume':True,'avg_price':'1'},
    {'fill':{'ts':time.time(),'price':'.6','volume':'10','fee':''}},
    {'fill':{'ts':time.time(),'price':'.6','volume':'nan','fee':0}},
    {'fill':{'ts':time.time()+10000,'price':'.6','volume':'1','fee':0}},
    {'action':'sell','fill':{'ts':time.time(),'price':'.6','volume':'10.0000001','fee':0}},
])
def test_invalid_change_is_readonly_without_backup(journal,change):
    store=management.HoldingManagement(journal);p={**body(store),**change};before=journal.read_bytes()
    with pytest.raises(PlanningError):store.change(p,'bithumb',apply=True)
    assert journal.read_bytes()==before
    assert not (journal.parent/'holding-management-backups').exists()


def test_backup_failure_concurrency_and_explicit_zero(journal,monkeypatch):
    store=management.HoldingManagement(journal);p=body(store);before=journal.read_bytes()
    def fail(*args):raise OSError('backup')
    with monkeypatch.context() as m:
        m.setattr(management,'backup_journal',fail)
        with pytest.raises(OSError):store.change(p,'bithumb',apply=True)
    assert journal.read_bytes()==before
    def save(_):
        try:management.HoldingManagement(journal).change({**p,'request_id':str(uuid.uuid4())},'bithumb',apply=True);return 200
        except PlanningError as e:return e.status
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(save,range(2)))==[200,409]
    p=body(store,'adjust',volume='0',avg_price='0')
    assert store.change(p,'bithumb',apply=True)['after']=={'volume':0,'avg_price':0}


def test_http_mutation_requires_local_token_readonly_preview_and_paper_unchanged(journal,tmp_path):
    paper=tmp_path/'paper.db'
    with sqlite3.connect(paper) as c:
        c.execute('CREATE TABLE research_signals_mx(exchange TEXT,market TEXT,price REAL,ts REAL,strategy TEXT)')
    original=paper.read_bytes();before=journal.read_bytes()
    with serving(paper,journal,True) as call:
        url='/api/holding-management'
        status,data=call(path=url+'?exchange=bithumb&market=KRW-B3&quote_currency=KRW')
        assert status==200 and data['current']['volume']==10
        p={**body(management.HoldingManagement(journal)),'mode':'preview'}
        header={'X-Planning-Token':data['csrf_token']}
        assert call('POST',p,path=url)[0]==403
        for extra in [{'Origin':'https://other.example'},{'Host':'other.example'},{'Sec-Fetch-Site':'cross-site'}]:
            assert call('POST',p,{**header,**extra},path=url)[0]==403
        assert call('POST',p,header,path=url)[0]==200
        assert journal.read_bytes()==before
        status,saved=call('POST',{**p,'mode':'apply'},header,path=url)
        assert status==200 and saved['result']['after']['volume']==20
        row=next(h for h in saved['holdings']['holdings'] if h['market']=='KRW-B3')
        assert row['volume']==20 and row['avg_price']==.705 and row['revision']!=data['revision']
        assert call('POST',{**p,'mode':'apply'},header,path=url)[0]==200
    with serving(paper,journal,False) as call:
        assert call('POST',p,header,path=url)[0]==405
    assert paper.read_bytes()==original


def test_existing_receipt_amounts_derived_readonly_and_retry_keeps_id(journal):
    import json
    store = management.HoldingManagement(journal)
    p = body(store)
    result = store.change(p, 'bithumb', apply=True)
    assert result['amounts'] == {'gross': 6, 'fee': .1, 'net': 6.1}
    # Emulate a receipt saved by the delivered previous build: no derived money.
    del result['amounts']
    with sqlite3.connect(journal) as conn:
        conn.execute('UPDATE holding_mutation_receipts SET result_json=? WHERE mutation_id=?',
                     (json.dumps(result), result['mutation_id']))
    before = journal.read_bytes()
    read = store.read(SCOPE, 'bithumb')['history'][0]
    assert read['amounts']['net'] == 6.1
    assert store.change(p, 'bithumb', apply=True) == read
    assert journal.read_bytes() == before
    sell = store.change(body(store, 'sell', fill={'ts': time.time()-1, 'price': '1.2', 'volume': '5', 'fee': '.1'}), 'bithumb')
    assert sell['amounts'] == {'gross': 6, 'fee': .1, 'net': 5.9}
    assert sell['realized_quote'] == pytest.approx(2.375)
    adjust = store.change(body(store, 'adjust', volume='2', avg_price='1'), 'bithumb')
    assert adjust['amounts'] is None
