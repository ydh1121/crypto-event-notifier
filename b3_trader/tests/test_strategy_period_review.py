"""Period boundaries and fees matter; fixtures never represent real PC outcomes."""
import copy
import hashlib
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen, Request
from types import SimpleNamespace

import pytest

from b3_trader.strategy_period_review import period_review
from b3_trader.strategy_lab_journal import reconcile_account
from b3_trader.strategy_lab_market import read_strategy_lab_market
from b3_trader.strategy_journal_review import handler
from b3_trader.tests.test_strategy_lab_journal import fixture_db

DAY = 86400
NOW = 100*DAY
START = NOW-7*DAY


def buy(i, ts, amount=100.4):
    return dict(id=i, ts=ts, side='buy', price=10, volume=10, krw=amount, realized_pnl=0, return_pct=0)


def sell(i, ts, cost=100.4, proceeds=109.6, volume=10):
    return dict(id=i, ts=ts, side='sell', price=11, volume=volume, krw=proceeds,
                realized_pnl=proceeds-cost, return_pct=(proceeds-cost)/cost*100)


def account(trades, key='a'):
    values=reconcile_account({}, trades, 10000)['values']
    return dict(experiment_id=key, style='aggressive', label='공격적', revision='fixture',
                reconciliation=reconcile_account(values, trades, 10000))


def review(trades, request=None):
    return period_review('bithumb','KRW-B3',[account(trades)],{'a':trades},request or {'period':'7d'},now=NOW)


def test_same_entry_windows_fee_amounts_and_no_future_sale_or_add_in_previous_period():
    trades=[buy(1,START-DAY), buy(2,START+1), sell(3,START+2,cost=200.8,proceeds=219.2,volume=20),
            buy(4,START+3),sell(5,START+4),buy(6,NOW-1)]
    before=copy.deepcopy(trades);result=review(trades);row=result['strategies'][0]
    assert row['status']=='ok' and row['current']['closed']==1 and row['current']['open']==1
    assert row['current']['carried_positions']==1
    assert row['current']['invested_krw']==pytest.approx(100.4)
    assert row['current']['proceeds_krw']==pytest.approx(109.6)
    assert row['current']['realized_pnl_krw']==pytest.approx(9.2)
    assert row['current']['return_pct']==pytest.approx(9.2/100.4*100)
    # Later averaging and sale are invisible at the previous cutoff.
    assert row['previous']['closed']==0 and row['previous']['open']==1
    assert row['previous']['open_invested_krw']==pytest.approx(100.4)
    assert row['previous']['realized_pnl_krw'] is None
    assert [c['entry_trade_id'] for c in result['witnesses']]==[6,4]
    assert result['witnesses'][0]['realized_pnl_krw'] is None
    assert trades==before


def test_boundaries_and_zero_return_are_not_missing():
    trades=[buy(1,START-7*DAY),sell(2,START-1,proceeds=100.4),
            buy(3,START),sell(4,NOW,proceeds=100.4)]
    row=review(trades)['strategies'][0]
    for period in ('current','previous'):
        assert row[period]['closed']==1
        assert row[period]['return_pct']==0 and row[period]['wins']==0
    all_period=review(trades,{'period':'all'})
    assert all_period['strategies'][0]['current']['closed']==2
    assert all_period['strategies'][0]['previous'] is None and all_period['start'] is None


def test_completed_return_is_cost_weighted_and_not_account_return_or_simple_mean():
    trades=[buy(1,START),sell(2,START+1),buy(3,START+2,amount=200),sell(4,START+3,cost=200,proceeds=180)]
    row=review(trades)['strategies'][0]['current']
    assert row['return_pct']==pytest.approx((9.2-20)/300.4*100)
    assert row['worst_return_pct']==pytest.approx(-10) and row['wins']==1


@pytest.mark.parametrize('clock',[float('nan'),NOW+1,START-1])
def test_invalid_or_reversed_clock_fails_closed(clock):
    trades=[buy(1,START),sell(2,clock)]
    row=review(trades)['strategies'][0]
    assert row['status']=='unreconciled' and row['current'] is None and row['previous'] is None


def test_unreconciled_and_empty_are_distinct():
    trades=[buy(1,START),sell(2,START+1)];bad=account(trades);bad['reconciliation']['matches']=False
    result=period_review('bithumb','KRW-B3',[bad,account([],'empty')],{'a':trades},{},now=NOW)
    assert result['strategies'][0]['current'] is None
    empty=result['strategies'][1]['current']
    assert empty['closed']==0 and empty['open']==0 and empty['return_pct'] is None
    assert empty['realized_pnl_krw'] is None and not result['witnesses']


def test_bounded_witnesses_do_not_truncate_totals():
    trades=[]
    for i in range(30):trades += [buy(i*2+1,START+i*10),sell(i*2+2,START+i*10+1)]
    result=review(trades)
    assert result['strategies'][0]['current']['closed']==30
    assert result['witnesses_total']==30 and len(result['witnesses'])==20
    assert result['witnesses'][0]['entry_trade_id']==59


def test_readonly_sql_and_http_match_account_and_preserve_exchange_scope(tmp_path,monkeypatch):
    monkeypatch.setattr('b3_trader.strategy_lab_market.time',SimpleNamespace(time=lambda:1800100000))
    path=tmp_path/'paper.db';fixture_db(path,cycles=3)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    lab=read_strategy_lab_market('bithumb','KRW-BTC',path,period_request={'period':'all'})
    for a,r in zip(lab['experiments'],lab['period_review']['strategies']):
        assert r['account_revision']==a['revision']
        assert r['ledger_trade_count']==a['journal']['total']
        assert r['current']['closed']==a['closed_trades']
        if a['closed_trades']:
            assert r['current']['realized_pnl_krw']==pytest.approx(a['realized_pnl_krw'])
    server=ThreadingHTTPServer(('127.0.0.1',0),handler(path,fixture=True))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(base+'/api/strategy-period?exchange=bithumb&market=KRW-BTC&period=all') as response:
            body=json.load(response)['review']
        assert body['status']=='ok' and body['strategies']==lab['period_review']['strategies']
        with urlopen(base+'/api/strategy-period?exchange=upbit&market=KRW-BTC') as response:
            assert json.load(response)['review']['status']=='no_account'
        for query in ('market=KRW-BTC&period=bad','market=KRW-BTC&exchange=other','market=BTC-ETH'):
            with pytest.raises(HTTPError) as exc:urlopen(base+'/api/strategy-period?'+query)
            assert exc.value.code==422
        with pytest.raises(HTTPError) as exc:urlopen(Request(base+'/api/strategy-period?market=KRW-BTC',headers={'Origin':'https://example.com'}))
        assert exc.value.code==403
    finally:
        server.shutdown();server.server_close();thread.join()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
