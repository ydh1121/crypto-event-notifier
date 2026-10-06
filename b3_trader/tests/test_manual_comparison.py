"""Cash evidence and cohort boundaries, using synthetic executions only."""
import copy

import pytest

from b3_trader.manual_trading import replay, compare_journals
from b3_trader.manual_planning_store import comparison_report
from b3_trader.tests.test_manual_planning import store, save, fill, SELECTION


def trade(i, ts, side, price, volume=1, fee=0):
    return dict(id=str(i), sequence=i, ts=ts, side=side, price=str(price), volume=str(volume), fee=str(fee))


def paper_account(trades):
    columns=['id','ts','side','price','volume','krw']
    return dict(revision='fixture-revision', reconciliation={'matches': True},
                journal=dict(columns=columns, rows=trades, total=len(trades)))


def test_weighted_costs_partial_sells_and_open_position_have_separate_totals():
    records=[trade(1,100,'buy',100,10,4), trade(2,110,'sell',120,3,1),
             trade(3,120,'sell',130,7,2), trade(4,130,'buy',200,10,0),
             trade(5,140,'sell',180,10,0), trade(6,150,'buy',500,2,2),
             trade(7,160,'sell',550,1,1)]
    before=copy.deepcopy(records)
    summary=replay(records);c=compare_journals(summary,None);m=c['manual']
    assert m['closed']==2 and m['wins']==1 and m['open']==1
    assert m['invested_krw']==3004 and m['proceeds_krw']==3067
    assert m['realized_pnl_krw']==63 and m['fees_krw']==7
    assert m['return_pct']==pytest.approx(63/3004*100)
    assert m['return_pct']!=m['mean_return_pct']
    assert m['worst_return_pct']==-10 and m['open_invested_krw']==1002
    assert summary['realized']==111  # 48 from the still-open position is not a closed result.
    assert summary['trades'][0]['gross_krw']==1000
    assert summary['trades'][0]['net']==1004
    assert c['manual_witnesses'][0]['remaining_cost_krw']==501
    assert records==before


def test_paper_cash_costs_are_used_once_and_future_averaging_cannot_leak():
    real=replay([trade(1,100,'buy',100,2,1),trade(2,200,'sell',120,2,1)])
    a=paper_account([[1,90,'buy',100,1,100.4],[2,110,'sell',120,1,119.6],
                     [3,120,'buy',100,1,100.4],[4,180,'sell',110,1,109.6],
                     [5,190,'buy',100,1,100.4],[6,201,'buy',80,1,80.4],
                     [7,210,'sell',130,2,259.2]])
    c=compare_journals(real,a);p=c['paper']
    assert c['status']=='ok' and c['paper_revision']=='fixture-revision'
    assert p['closed']==1 and p['open']==1 and c['paper_carried_positions']==1
    assert p['realized_pnl_krw']==pytest.approx(9.2)
    assert p['return_pct']==pytest.approx(9.2/100.4*100)
    assert p['fees_krw'] is None  # Net amounts do not imply a separately known paid fee.
    assert c['paper_witnesses'][0]['invested_krw']==100.4
    assert c['paper_witnesses'][0]['exit_ts'] is None


def test_cancellation_reopens_position_and_reduces_the_comparison_end():
    records=[trade(1,100,'buy',100),trade(2,200,'sell',120)]
    records[1]['voided']=True
    c=compare_journals(replay(records),paper_account([]))
    assert c['end']==100 and c['manual']['closed']==0 and c['manual']['open']==1
    assert c['manual']['return_pct'] is None and c['manual']['realized_pnl_krw'] is None
    assert c['manual_witnesses'][0]['exit_ts'] is None


def test_missing_zero_and_incomplete_ledgers_are_distinct():
    empty=compare_journals(replay([]),paper_account([]))
    assert empty['status']=='no_manual_trades' and empty['paper'] is None
    assert empty['manual']['wins'] is None
    real=replay([trade(1,100,'buy',100),trade(2,200,'sell',100)])
    a=paper_account([[1,100,'buy',100,1,100],[2,200,'sell',100,1,100]])
    c=compare_journals(real,a)
    assert c['manual']['return_pct']==0 and c['paper']['return_pct']==0
    assert c['paper']['wins']==0
    a['journal']['total']=3
    c=compare_journals(real,a)
    assert c['status']=='paper_incomplete' and c['paper'] is None
    a['journal']['total']=2;a['reconciliation']['matches']=False
    assert compare_journals(real,a)['paper'] is None


@pytest.mark.parametrize('clock',[99,float('nan'),float('inf')])
def test_invalid_paper_clock_cannot_create_a_comparison(clock):
    real=replay([trade(1,100,'buy',100),trade(2,200,'sell',100)])
    a=paper_account([[1,100,'buy',100,1,100],[2,clock,'sell',110,1,110]])
    assert compare_journals(real,a)['paper'] is None


def test_large_history_totals_survive_bounded_evidence():
    real=replay([trade(1,100,'buy',100),trade(2,1000,'sell',110)])
    rows=[]
    for i in range(30):rows.extend([[i*2+1,101+i*10,'buy',100,1,100],[i*2+2,102+i*10,'sell',101,1,101]])
    c=compare_journals(real,paper_account(rows))
    assert c['paper']['closed']==30 and c['paper']['realized_pnl_krw']==30
    assert len(c['paper_witnesses'])==20


def test_report_uses_existing_state_without_schema_or_holding_writes(store):
    before=store.path.read_bytes()
    report=comparison_report(store.path,SELECTION,None)
    assert report['active_records']==0 and report['plan_revision']==0
    assert store.path.read_bytes()==before
    save(store);fill(store)
    before=store.path.read_bytes();ui=store.read(SELECTION)
    report=comparison_report(store.path,SELECTION,None)
    assert report['comparison']==ui['comparison']
    assert report['active_records']==1 and report['comparison']['manual']['open']==1
    assert store.path.read_bytes()==before
