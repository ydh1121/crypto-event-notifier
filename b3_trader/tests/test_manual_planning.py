import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import closing

import pytest

from b3_trader.manual_planning_store import ManualPlanningStore
from b3_trader.manual_trading import PlanningError, replay, compare_journals


SELECTION = dict(exchange='bithumb', market='KRW-B3', experiment='bithumb|aggressive|v1')
ACCOUNT = dict(experiment_id=SELECTION['experiment'], style='aggressive', label='공격적', return_pct=3, closed_trades=3, wins=2)


def draft():
    return dict(volume='10', average='100', fee='0.04', slippage='0', budget='1000',
        holdingRevision='1|10|100', origin='manual', buys=[dict(price='80', amount='800')],
        sells=[dict(price='120', weight='30'), dict(price='130', weight='70')])


def request(**kwargs):
    return dict(request_id=str(uuid.uuid4()), **kwargs)


@pytest.fixture
def store(tmp_path):
    path = tmp_path/'journal.sqlite3'
    with sqlite3.connect(path) as c:
        c.executescript('CREATE TABLE manual_holdings(market TEXT PRIMARY KEY,volume REAL,avg_price REAL,exchange TEXT,updated_ts REAL); CREATE TABLE averaging_plans(market TEXT PRIMARY KEY,rows_json TEXT,updated_ts REAL);')
        c.executemany('INSERT INTO manual_holdings VALUES(?,?,?,?,?)', [('KRW-B3',10,100,None,1),('KRW-ZERO',0,20,'bithumb',2)])
        c.execute('INSERT INTO averaging_plans VALUES(?,?,?)', ('KRW-B3','[{"price":80,"amount_krw":800}]',1))
    return ManualPlanningStore(path)


def save(store, revision=0, value=None):
    return store.write(SELECTION,'save',request(expected_revision=revision,draft=value or draft()),ACCOUNT)


def fill(store, side='buy', volume='2', price='100', fee='1', ts=None, **kwargs):
    data=store.read(SELECTION)
    return store.write(SELECTION,'fill',request(expected_revision=data['ledger_revision'],plan_revision=data['plan_revision'],fill=dict(side=side,volume=volume,price=price,fee=fee,ts=ts or time.time()-1,**kwargs)),ACCOUNT)


def test_read_is_immutable_and_first_save_backs_up_without_replacing_legacy(store):
    before=hashlib.sha256(store.path.read_bytes()).hexdigest()
    assert store.read(SELECTION)['plan'] is None
    assert hashlib.sha256(store.path.read_bytes()).hexdigest()==before
    assert not (store.path.parent/'manual-planning-backups').exists()
    data=save(store)
    assert data['plan']['draft']==draft()
    assert ManualPlanningStore(store.path).read(SELECTION)['plan']==data['plan']
    backups=list((store.path.parent/'manual-planning-backups').glob('*.sqlite3'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as b, sqlite3.connect(store.path) as c:
        assert b.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        for table in ('manual_holdings','averaging_plans'):
            assert b.execute('SELECT * FROM '+table).fetchall()==c.execute('SELECT * FROM '+table).fetchall()
        assert b.execute("SELECT name FROM sqlite_master WHERE name LIKE 'manual_strategy_%'").fetchall()==[]
    save(store,1)
    assert len(list((store.path.parent/'manual-planning-backups').glob('*.sqlite3')))==1


def test_missing_db_and_backup_failure_never_create_or_mutate_source(store,tmp_path,monkeypatch):
    with pytest.raises(PlanningError):ManualPlanningStore(tmp_path/'missing').read(SELECTION)
    assert not (tmp_path/'missing').exists()
    before=store.path.read_bytes()
    def blocked():raise OSError('disk full')
    monkeypatch.setattr(store,'prepare',blocked)
    with pytest.raises(OSError):save(store)
    assert store.path.read_bytes()==before


def test_scope_and_optimistic_conflicts_preserve_other_plan_versions(store):
    save(store)
    other=ManualPlanningStore(store.path)
    updated=draft();updated['sells'][0]['price']='125'
    save(store,1,updated)
    with pytest.raises(PlanningError) as e:save(other,1)
    assert e.value.status==409
    assert other.read(SELECTION)['plan']['draft']['sells'][0]['price']=='125'
    assert other.read({**SELECTION,'exchange':'upbit'})['plan'] is None
    assert other.read({**SELECTION,'experiment':'bithumb|balanced|v1'})['plan'] is None
    with pytest.raises(PlanningError):other.read({**SELECTION,'market':'KRW-ETH/BTC'})


def test_idempotent_retries_and_request_content_mismatch(store):
    p=request(expected_revision=0,draft=draft())
    assert store.write(SELECTION,'save',p,ACCOUNT)['plan_revision']==1
    assert store.write(SELECTION,'save',p,ACCOUNT)['plan_revision']==1
    p['draft']['average']='999'
    with pytest.raises(PlanningError):store.write(SELECTION,'save',p,ACCOUNT)
    fill(store)
    d=store.read(SELECTION)
    p=request(expected_revision=d['ledger_revision'],plan_revision=d['plan_revision'],fill=dict(side='sell',volume='2',price='120',fee='1',ts=time.time()))
    once=store.write(SELECTION,'fill',p,ACCOUNT)
    twice=store.write(SELECTION,'fill',p,ACCOUNT)
    assert once['ledger_revision']==twice['ledger_revision']
    assert twice['summary']['realized']==38 and twice['summary']['volume']==0


def test_partial_sells_actual_fees_and_cancellation_keep_audit_trail(store):
    save(store);fill(store,volume='10',fee='4',ts=time.time()-10)
    one=fill(store,side='sell',volume='3',price='120',fee='1',ts=time.time()-5)
    assert one['summary']['volume']==7
    assert one['summary']['realized']==pytest.approx(57.8)
    assert one['comparison']['manual']['closed']==0
    with pytest.raises(PlanningError):fill(store,side='sell',volume='8')
    with pytest.raises(PlanningError):store.write(SELECTION,'void',request(expected_revision=one['ledger_revision'],target=one['records'][0]['id']),ACCOUNT)
    two=fill(store,side='sell',volume='7',price='130',fee='2')
    assert two['summary']['volume']==0 and two['summary']['realized']==263
    assert two['comparison']['manual']['closed']==1
    assert two['comparison']['manual']['mean_return_pct']==pytest.approx(263/1004*100)
    after=store.write(SELECTION,'void',request(expected_revision=two['ledger_revision'],target=two['records'][-1]['id']),ACCOUNT)
    assert after['summary']['volume']==7
    assert after['records'][-1]['voided'] is True and len(after['records'])==3
    assert ManualPlanningStore(store.path).read(SELECTION)['records']==after['records']


@pytest.mark.parametrize('field,value',[('price','NaN'),('volume',''),('fee',''),('volume',True),('fee','201'),('ts',1),('ts',1e20)])
def test_invalid_execution_never_writes(store,field,value):
    save(store)
    item=dict(side='buy',price='100',volume='2',fee='1',ts=time.time()-1);item[field]=value
    before=store.path.read_bytes()
    with pytest.raises(PlanningError):store.write(SELECTION,'fill',request(expected_revision=0,plan_revision=1,fill=item),ACCOUNT)
    assert store.path.read_bytes()==before


def test_saved_plan_reference_is_versioned_and_cannot_look_backwards(store):
    data=save(store)
    with pytest.raises(PlanningError):fill(store,stage='buy:0',ts=data['plan']['saved_at']-1)
    data=fill(store,stage='buy:0',ts=data['plan']['saved_at']+.001)
    assert data['records'][0]['reference_price']=='80'
    newer=draft();newer['buys'][0]['price']='70';save(store,1,newer)
    data=store.read(SELECTION)
    assert data['records'][0]['reference_price']=='80' and data['records'][0]['plan_revision']==1
    with pytest.raises(PlanningError) as e:
        store.write(SELECTION,'fill',request(expected_revision=data['ledger_revision'],plan_revision=1,
            fill=dict(side='buy',price='90',volume='1',fee='0',ts=time.time())),ACCOUNT)
    assert e.value.status==409


def test_comparison_counts_only_full_cycles_within_same_window():
    real=replay([dict(side='buy',ts=100,price='100',volume='2',fee='1',sequence=1),dict(side='sell',ts=200,price='120',volume='2',fee='1',sequence=2)])
    columns=['id','side','ts','price','volume','krw']
    rows=[[1,'buy',90,100,1,100],[2,'sell',110,120,1,120],
          [3,'buy',120,100,1,100],[4,'sell',180,110,1,110],
          [5,'buy',190,100,1,100],[6,'sell',210,200,1,200]]
    a=dict(reconciliation={'matches':True},journal=dict(total=6,columns=columns,rows=rows))
    comparison=compare_journals(real,a)
    assert comparison['start']==100 and comparison['end']==200
    assert comparison['paper']==dict(closed=1,wins=1,mean_return_pct=10)
    a['reconciliation']['matches']=False
    assert compare_journals(real,a)['paper'] is None
