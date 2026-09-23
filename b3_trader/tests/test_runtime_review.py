import hashlib
import json
import sqlite3
import threading

from b3_trader import runtime_review as review
from b3_trader.strategy_journal_review import finish_runtime_observation


def database(tmp_path):
    path = tmp_path/'b3_trader/data/auto_demo.sqlite3'
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE research_accounts_mx(updated_ts REAL)')
        db.execute('INSERT INTO research_accounts_mx VALUES(100)')
    return path


def test_dead_owner_does_not_inherit_saved_healthy_badge_or_leak_errors(tmp_path, monkeypatch):
    db = database(tmp_path)
    path = tmp_path/review.STATUS_FILES['research']
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'pid': 111, 'started_at': 90, 'updated_at': 100,
        'components': [{'name': 'market-ohlcv-history', 'status': 'healthy',
                        'last_error': 'database is locked token=do-not-export-this-secret'}]}))
    monkeypatch.setattr(review, '_processes', lambda _: {'status':'read','items':[]})
    original = hashlib.sha256(db.read_bytes()).hexdigest()
    result = review.read_runtime(db)
    owner = result['saved_statuses']['research']
    assert owner['process_observation'] == 'absent'
    assert owner['saved_owner_matches'] is False
    assert owner['components'][0]['error_kinds'] == ['database_locked']
    assert 'do-not-export' not in json.dumps(result)
    assert result['activity']['paper']['latest'] == 100
    assert result['activity']['events']['latest'] is None
    assert hashlib.sha256(db.read_bytes()).hexdigest() == original


def test_process_query_failure_and_other_checkout_are_unknown(tmp_path, monkeypatch):
    db = database(tmp_path)
    for processes in ({'status':'read_failed','items':[]}, {'status':'read','items':[
        {'role':'paper','pid':111,'scope':'unresolved_checkout','created_at':90}]}):
        monkeypatch.setattr(review, '_processes', lambda _, value=processes: value)
        result = review.read_runtime(db)
        assert result['saved_statuses']['paper']['process_observation'] == 'unknown'


def test_reused_pid_does_not_match_saved_owner(tmp_path, monkeypatch):
    db = database(tmp_path)
    (tmp_path/review.STATUS_FILES['paper']).write_text(json.dumps({'pid':111,'started_at':1}))
    monkeypatch.setattr(review, '_processes', lambda _: {'status':'read','items':[
        {'role':'paper','pid':111,'scope':'checkout','created_at':1000}]})
    owner = review.read_runtime(db)['saved_statuses']['paper']
    assert owner['process_observation'] == 'present' and owner['saved_owner_matches'] is False


def test_second_observation_uses_actual_db_progress_without_writing_it(tmp_path, monkeypatch):
    db = database(tmp_path)
    monkeypatch.setattr(review, '_processes', lambda _: {'status':'read','items':[]})
    report = {'runtime_review':{'status':'waiting','before':review.read_runtime(db)}}
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE research_accounts_mx SET updated_ts=200')
    original = hashlib.sha256(db.read_bytes()).hexdigest()
    result_path = tmp_path/'review.json'
    finish_runtime_observation(db, result_path, report, 0, threading.Event())
    result = json.loads(result_path.read_text())['runtime_review']
    assert result['status'] == 'complete'
    assert result['changes']['paper']['observation'] == 'advanced'
    assert result['changes']['events']['observation'] == 'unknown'
    assert hashlib.sha256(db.read_bytes()).hexdigest() == original


def test_unchanged_is_not_failure_and_cancel_does_not_claim_second_observation(tmp_path):
    before = {'activity':{'paper':{'status':'read','latest':100}}}
    assert review.compare_activity(before,before)['paper']['observation'] == 'unchanged'
    stop = threading.Event();stop.set()
    finish_runtime_observation(tmp_path/'absent.db',tmp_path/'absent.json',{},0,stop)
    assert not (tmp_path/'absent.db').exists() and not (tmp_path/'absent.json').exists()


def test_damaged_status_and_startup_error_logs_do_not_break_read_only_review(tmp_path, monkeypatch):
    db = database(tmp_path)
    (tmp_path/review.STATUS_FILES['host']).write_text('{broken')
    log = tmp_path/review.HOST_LOGS/'paper.log'
    log.parent.mkdir(parents=True)
    log.write_text('ModuleNotFoundError: missing library token=private-value')
    monkeypatch.setattr(review, '_processes', lambda _: {'status':'read','items':[]})
    result = review.read_runtime(db)
    assert result['saved_statuses']['host']['status'] == 'unreadable'
    assert result['process_logs']['paper']['recent_error_kinds'] == ['missing_module']
    assert 'private-value' not in json.dumps(result)


def test_actual_receipt_time_and_indexed_benchmark_scope(tmp_path):
    db = database(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE research_intelligence_events(observed_at REAL, received_at REAL)')
        conn.execute('INSERT INTO research_intelligence_events VALUES(0,300)')
        conn.execute('CREATE TABLE research_market_trade_flow_mx(exchange TEXT, market TEXT, trade_ts REAL, received_at REAL)')
        conn.execute('CREATE INDEX trade_time ON research_market_trade_flow_mx(exchange,market,trade_ts DESC)')
        conn.executemany('INSERT INTO research_market_trade_flow_mx VALUES(?,?,?,?)', [
            ('bithumb','KRW-BTC',100,200), ('upbit','KRW-ETH',120,220),
            ('bithumb','KRW-B3',1000,1100), ('bithumb','KRW-BTC',90,2000)])
    result = review.read_activity(db)
    assert result['events']['latest'] == 300 and result['events']['clock'] == 'received_at'
    flow = result['trade_flow']
    assert flow['latest'] == 120 and flow['clock'] == 'trade_ts'
    assert flow['streams']['upbit|KRW-BTC'] is None
    assert flow['streams']['bithumb|KRW-BTC'] == 100
    assert flow['scope'] != 'all_rows'
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE research_intelligence_events SET received_at=0')
    assert review.read_activity(db)['events']['latest'] is None


def test_recovery_helper_is_observed_as_host_owner(tmp_path, monkeypatch):
    db = database(tmp_path)
    (tmp_path/review.STATUS_FILES['host']).write_text(json.dumps({'pid':111,'started_at':100,'profile':'collection_recovery'}))
    monkeypatch.setattr(review, '_processes', lambda _: {'status':'read','items':[
        {'role':'recovery','pid':111,'scope':'checkout','created_at':100}]})
    owner = review.read_runtime(db)['saved_statuses']['host']
    assert owner['saved_owner_matches'] is True
    assert owner['saved']['profile'] == 'collection_recovery'
