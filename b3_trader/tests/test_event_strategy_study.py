"""Temporary fixtures only: source prices → scoped study → reconciled PAPER → API."""
import hashlib
import json
import sqlite3
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen, Request

import pytest

from b3_trader.event_response_contract import HORIZONS, PROVIDER_ID
from b3_trader.event_strategy_study import read_event_study
from b3_trader.intelligence_event_response import IntelligenceEventResponseCollector
from b3_trader.strategy_lab_market import read_strategy_lab_market
from b3_trader.strategy_journal_review import handler
from b3_trader.tests.test_event_reaction_flow import setup, trade
from b3_trader.tests.test_strategy_lab_journal import fixture_db

SOURCE = 'us_bls_release_calendar'


def release(conn, key, stamp, kind='US_CPI', source=SOURCE):
    conn.execute('INSERT INTO research_intelligence_events(event_id,event_type,source_id,title,source_ts) VALUES(?,?,?,?,?)',
                 (key, kind, source, kind, stamp))
    conn.commit()


def sample(conn, key, stamp, gain, market='KRW-B3', horizon='15m', **overrides):
    event=conn.execute('SELECT * FROM research_intelligence_events WHERE event_id=?',(key,)).fetchone()
    seconds=dict(HORIZONS)[horizon]
    row=dict(event_id=key,event_type=event['event_type'],source_id=event['source_id'],exchange='bithumb',
             market=market,horizon_label=horizon,horizon_seconds=seconds,event_ts=stamp,
             baseline_trade_ts=stamp-1,baseline_price=100,target_ts=stamp+seconds,
             target_trade_ts=stamp+seconds+1,target_price=100+gain,return_pct=gain,
             provider_id=PROVIDER_ID,data_rights='fixture',observation_tolerance_seconds=120,captured_at=stamp+seconds+2)
    row.update(overrides)
    conn.execute(f"INSERT INTO research_intelligence_event_responses({','.join(row)}) VALUES({','.join('?' for _ in row)})",tuple(row.values()))
    conn.commit()


def study(conn, request=None, accounts=None, trades=None, now=300000):
    return read_event_study(conn,'bithumb','KRW-B3',accounts or [],trades or {},request or {},now=now)


def response_db(tmp_path):
    path=tmp_path/'study.db';conn=setup(path)
    IntelligenceEventResponseCollector(conn,benchmarks=[('bithumb','KRW-B3')])
    return path,conn


def test_collector_prices_to_study_missing_zero_pairs_and_scope(tmp_path):
    path,conn=response_db(tmp_path)
    release(conn,'one',100000)
    for symbol,price in [('KRW-B3',104),('KRW-BTC',101),('KRW-ETH',98)]:
        trade(conn,symbol,99999,100);trade(conn,symbol,100901,price)
    collector=IntelligenceEventResponseCollector(conn,benchmarks=[('bithumb',m) for m in ('KRW-B3','KRW-BTC','KRW-ETH')])
    assert collector.run_once(now=101000)['samples_inserted']==3
    release(conn,'zero',110000);sample(conn,'zero',110000,0)
    sample(conn,'zero',110000,50,'KRW-ETH',exchange='upbit')
    release(conn,'missing',120000);sample(conn,'missing',120000,1,'KRW-BTC')
    release(conn,'other-source',130000,source='us_bea_release_schedule');sample(conn,'other-source',130000,99)
    release(conn,'waiting',299500)
    conn.close();before=hashlib.sha256(path.read_bytes()).hexdigest()
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON');conn.execute('BEGIN')
        result=study(conn,{'source_id':SOURCE,'event_type':'US_CPI'})
    row=next(g for g in result['groups'] if g['source_id']==SOURCE)
    assert (row['events'],row['samples'],row['missing_events'],row['waiting_events'])==(4,2,1,1)
    assert row['mean_pct']==pytest.approx(2) and row['median_pct']==pytest.approx(2)
    assert row['positive_samples']==1
    assert row['vs_btc']['samples']==row['vs_eth']['samples']==1
    assert row['vs_btc']['mean_pct']==pytest.approx(3)
    assert row['vs_eth']['mean_pct']==pytest.approx(6)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('mutation', ['clock','return','anchor','future','source','provider'])
def test_invalid_revised_or_unavailable_prices_are_not_performance(tmp_path,mutation):
    _,conn=response_db(tmp_path);release(conn,'e',100000);sample(conn,'e',100000,4)
    if mutation=='clock':conn.execute('UPDATE research_intelligence_events SET source_ts=source_ts+10')
    if mutation=='return':conn.execute('UPDATE research_intelligence_event_responses SET return_pct=99')
    if mutation=='anchor':sample(conn,'e',100000,4,horizon='1h',baseline_trade_ts=99998)
    if mutation=='future':conn.execute('UPDATE research_intelligence_event_responses SET captured_at=400000')
    if mutation=='source':conn.execute("UPDATE research_intelligence_event_responses SET source_id='other'")
    if mutation=='provider':conn.execute("UPDATE research_intelligence_event_responses SET provider_id='other'")
    conn.commit();result=study(conn);row=result['groups'][0]
    assert row['samples']==0 and row['mean_pct'] is None and row['positive_samples'] is None
    assert row['missing_events']==1;conn.close()


def test_nearest_event_once_ties_preexisting_positions_open_and_unreconciled(tmp_path):
    _,conn=response_db(tmp_path)
    for key,ts,kind in [('cpi',100000,'US_CPI'),('closer',100300,'US_EMPLOYMENT'),
                        ('cpi2',110000,'US_CPI'),('tie',110000,'US_PPI'),('cpi3',120000,'US_CPI')]:
        release(conn,key,ts,kind)
    sample(conn,'cpi',100000,2)
    def buy(i,ts,cost=100):return dict(id=i,ts=ts,side='buy',price=10,krw=cost)
    def sell(i,ts,pnl=10):return dict(id=i,ts=ts,side='sell',price=12,krw=220,realized_pnl=pnl,return_pct=5)
    trades=[buy(1,99900),buy(2,100001),sell(3,100010), # Already held before CPI: exclude.
            buy(4,100100),buy(5,100150),sell(6,100200), # One first entry, not two.
            buy(7,100400),sell(8,100600), # Nearest different type: not CPI.
            buy(9,110100),sell(10,110500), # Same-time releases: ambiguous.
            buy(11,120100)] # Open: not realized performance zero.
    accounts=[dict(experiment_id='a',style='aggressive',label='공격적',reconciliation={'matches':True}),
              dict(experiment_id='b',style='balanced',label='균형',reconciliation={'matches':False})]
    result=study(conn,{'source_id':SOURCE,'event_type':'US_CPI'},accounts,{'a':trades,'b':trades})
    row=result['strategies'][0]
    assert (row['closed'],row['open'],row['wins'],row['ambiguous_excluded'])==(1,1,1,1)
    assert (row['realized_pnl_krw'],row['invested_krw'],row['return_pct'])==(10,200,5)
    assert row['reaction_matched_closed']==1
    assert [(w['entry_trade_id'],w['exit_trade_id']) for w in result['witnesses']]==[(11,None),(4,6)]
    assert result['witnesses'][0]['realized_pnl_krw'] is None
    assert result['strategies'][1]['closed'] is None
    conn.close()


def test_bounded_query_never_turns_a_cutoff_tie_into_unique_event(tmp_path,monkeypatch):
    _,conn=response_db(tmp_path)
    monkeypatch.setattr('b3_trader.event_strategy_study.MAX_EVENTS',2)
    release(conn,'new',120000);release(conn,'tie-a',110000);release(conn,'tie-b',110000)
    row=study(conn)
    assert row['truncated'] and row['groups'][0]['events']==1
    assert row['earliest_event_ts']==120000
    conn.close()


def test_actual_ledger_fee_totals_and_http_read_only(tmp_path,monkeypatch):
    path,conn=response_db(tmp_path);conn.close();fixture_db(path,cycles=2)
    with sqlite3.connect(path) as conn:
        conn.row_factory=sqlite3.Row
        for table in ('strategy_lab_accounts','strategy_lab_learning','strategy_lab_trades','research_market_memory_mx'):
            conn.execute(f"UPDATE {table} SET market='KRW-B3'")
        # A recent fixture clock, independent of wall time; real strategy decisions/amounts retained.
        conn.execute('UPDATE strategy_lab_trades SET ts=100000+(ts-1800000000)')
        release(conn,'cpi',100000);sample(conn,'cpi',100000,4)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr('b3_trader.strategy_lab_market.time.time',lambda:300000)
    data=read_strategy_lab_market('bithumb','KRW-B3',path,event_study_request={})
    a=next(a for a in data['experiments'] if a['style']=='aggressive')
    result=data['event_study'];out=next(r for r in result['strategies'] if r['style']=='aggressive')
    assert a['reconciliation']['matches'] and out['closed']==a['closed_trades']==2
    assert out['realized_pnl_krw']==pytest.approx(a['realized_pnl_krw'])
    assert sum(w['proceeds_krw']-w['invested_krw'] for w in result['witnesses'] if w['exit_ts'])==pytest.approx(out['realized_pnl_krw'])
    assert sum(w['invested_krw'] for w in result['witnesses'] if w['exit_ts'])==pytest.approx(out['invested_krw'])
    server=ThreadingHTTPServer(('127.0.0.1',0),handler(path));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        api=json.load(urlopen(base+'/api/event-study?exchange=bithumb&market=KRW-B3'))['study']
        assert api==result
        detail=json.load(urlopen(base+'/api/market-detail?exchange=bithumb&market=KRW-B3'))['detail']['data']['strategy_lab']
        assert detail['event_study_available'] and 'event_study' not in detail
        for suffix,status in [('horizon=bad',422),('category=bad',422),('exchange=bad',422),('market=BTC-B3',422)]:
            with pytest.raises(HTTPError) as exc:urlopen(base+'/api/event-study?market=KRW-B3&'+suffix if not suffix.startswith('market') else base+'/api/event-study?'+suffix)
            assert exc.value.code==status
        with pytest.raises(HTTPError) as exc:urlopen(Request(base+'/api/event-study',method='POST'))
        assert exc.value.code==405
        other=json.load(urlopen(base+'/api/event-study?exchange=upbit&market=KRW-B3'))['study']
        assert other['strategies']==[] and other['groups'][0]['samples']==0
    finally:server.shutdown();server.server_close();thread.join(2)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('bad_ts',[0,99999,400000,float('inf')])
def test_bad_ledger_clocks_excluded_not_zero(tmp_path,bad_ts):
    _,conn=response_db(tmp_path);release(conn,'e',100000)
    account=dict(experiment_id='a',style='aggressive',reconciliation={'matches':True})
    trades=[dict(id=1,ts=100100,side='buy',price=100,krw=100),dict(id=2,ts=bad_ts,side='buy',price=100,krw=100)]
    row=study(conn,accounts=[account],trades={'a':trades})['strategies'][0]
    assert row['status']=='unreconciled' and row['closed'] is None and row['return_pct'] is None
    conn.close()
