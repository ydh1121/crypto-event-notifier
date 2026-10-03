import hashlib
import json
import sqlite3

import pytest

from b3_trader import event_capture_review as review
from b3_trader import runtime_review
from b3_trader.tests.test_event_price_archive import database, trade
from b3_trader.event_price_archive import capture_market
from b3_trader.intelligence_event_response import IntelligenceEventResponseCollector


def read(path, now=101000):
    return review.read_event_capture(path, now=now)


def test_advancing_benchmarks_cannot_prove_b3_collection(tmp_path):
    path = tmp_path/'prices.db'
    store = database(path)
    store.insert_trades([trade('KRW-BTC',100500), trade('KRW-ETH',100500)])
    before = {'event_capture': read(path)}
    store.insert_trades([trade('KRW-BTC',100900), trade('KRW-ETH',100901)])
    after = {'event_capture': read(path)}
    result = review.compare_event_capture(before, after)
    assert result['bithumb|KRW-B3']['observation'] == 'unknown'
    assert result['bithumb|KRW-BTC']['observation'] == result['bithumb|KRW-ETH']['observation'] == 'advanced'
    assert before['event_capture']['markets']['KRW-B3']['raw']['row_count'] == 0
    assert after['event_capture']['coverage_is_continuous'] is None
    changes = runtime_review.compare_activity(before, after)
    advancing = [name for name, change in changes.items() if change['observation'] == 'advanced']
    assert 'event_price_stream:bithumb|KRW-BTC' in advancing
    assert 'event_price_stream:bithumb|KRW-B3' not in advancing
    store.close()


def test_old_release_is_separate_from_no_recent_eligible_event(tmp_path):
    path = tmp_path/'old.db'
    store = database(path)
    store.insert_trades([trade('KRW-B3',99999), trade('KRW-B3',100901)])
    capture_market(store.conn,'bithumb','KRW-B3',101000)
    store.conn.commit()
    result = read(path, now=400000)
    assert result['events']['eligible_events'] == 0
    assert result['events']['latest_source_ts'] == 100000
    event = result['anchor_checks'][0]
    assert event['in_collection_window'] is False
    assert event['markets']['KRW-B3']['points']['baseline']['archive']['price']['trade_ts'] == 99999
    assert result['markets']['KRW-B3']['raw']['latest_age_seconds'] == 299099
    store.close()


def test_retained_raw_archive_and_completed_response_are_distinct(tmp_path):
    path = tmp_path/'archive.db'
    store = database(path)
    collector = IntelligenceEventResponseCollector(store.conn, benchmarks=[('bithumb','KRW-B3')])
    store.insert_trades([trade('KRW-B3',99999), trade('KRW-B3',100901,110)])
    assert collector.run_once(now=101000)['samples_inserted'] == 1
    store.conn.execute('DELETE FROM research_market_trade_flow_mx');store.conn.commit()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = read(path)
    market = result['anchor_checks'][0]['markets']['KRW-B3']
    assert result['markets']['KRW-B3']['raw']['row_count'] == 0
    assert market['points']['baseline']['raw']['price'] is None
    assert market['points']['baseline']['archive']['price'] == {'trade_ts':99999,'price':100}
    assert market['responses']['recorded']['15m']['return_pct'] == pytest.approx(10)
    assert market['points']['1h'] == {'status':'not_due','target_ts':103600}
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    store.close()


def test_after_release_or_outside_tolerance_cannot_be_a_baseline(tmp_path):
    path = tmp_path/'late.db'
    store = database(path)
    store.insert_trades([trade('KRW-B3',99879), trade('KRW-B3',100001),
                         trade('KRW-B3',99999,exchange='upbit'), trade('KRW-ETH',99999)])
    event = read(path)['anchor_checks'][0]
    assert event['markets']['KRW-B3']['points']['baseline']['raw']['price'] is None
    assert event['markets']['KRW-ETH']['points']['baseline']['raw']['price']['trade_ts'] == 99999
    store.close()


def test_future_and_imprecise_clocks_do_not_become_past_reactions(tmp_path):
    path = tmp_path/'clocks.db'
    store = database(path)
    store.conn.execute("UPDATE research_intelligence_events SET event_type='FOMC_MEETING'")
    store.conn.execute("""INSERT INTO research_intelligence_events VALUES
        ('scheduled','US_EMPLOYMENT','us_bls_release_calendar','Fixture',200000,'',0,200000,100000)""")
    store.conn.commit()
    result = read(path)
    assert result['events']['eligible_events'] == 0
    assert result['events']['excluded_imprecise_events'] == 1
    assert result['events']['next_scheduled']['source_ts'] == 200000
    assert result['anchor_checks'][0]['precise_clock'] is False
    assert result['anchor_checks'][0]['markets'] == {}
    store.close()


def test_capped_selection_is_not_a_total_count(tmp_path):
    path = tmp_path/'events.db'
    store = database(path)
    store.conn.executemany("""INSERT INTO research_intelligence_events VALUES
        (?,'US_EMPLOYMENT','us_bls_release_calendar','Fixture',100000,'',100000,100000,100000)""",
        [(f'event-{i}',) for i in range(100)])
    store.conn.commit()
    result = read(path)
    assert result['events']['eligible_events'] == 80
    assert result['events']['selection_limit_reached'] is True
    assert len(result['anchor_checks']) == 4
    store.close()


def test_empty_missing_and_old_schema_are_not_confused(tmp_path):
    path = tmp_path/'missing.db'
    assert read(path)['status'] == 'unavailable'
    assert not path.exists()
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE research_market_trade_flow_mx(exchange TEXT,market TEXT,trade_ts REAL)')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = read(path)
    assert result['events']['status'] == 'unavailable'
    assert 'eligible_events' not in result['events']
    assert all(m['raw']['status'] == 'unavailable' for m in result['markets'].values())
    assert all(m['websocket_session']['status'] == 'unavailable' for m in result['markets'].values())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_query_timeout_is_unknown_and_never_creates_or_changes_data(tmp_path, monkeypatch):
    path = tmp_path/'budget.db'
    store = database(path);store.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(review,'TOTAL_SECONDS',0)
    result = read(path)
    assert result['events']['status'] == 'query_timeout'
    assert all(m['raw']['status'] == 'query_timeout' for m in result['markets'].values())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_slow_row_count_preserves_ticks_event_anchors_and_actual_progress(tmp_path, monkeypatch):
    path = tmp_path/'count-timeout.db'
    store = database(path)
    store.insert_trades([trade('KRW-B3',99999), trade('KRW-B3',100901,110)])
    collector = IntelligenceEventResponseCollector(store.conn, benchmarks=[('bithumb','KRW-B3')])
    assert collector.run_once(now=101000)['samples_inserted'] == 1
    def slow_count(*_):
        raise sqlite3.OperationalError('interrupted')
    monkeypatch.setattr(review, '_raw_count', slow_count)
    before = read(path)
    raw = before['markets']['KRW-B3']['raw']
    assert raw['status'] == 'read' and raw['last']['trade_ts'] == 100901
    assert raw['count_status'] == 'query_timeout' and raw['row_count'] is None
    assert raw['row_count_capped'] is None
    assert before['anchor_checks'][0]['markets']['KRW-B3']['responses']['recorded']['15m']['return_pct'] == pytest.approx(10)
    store.insert_trades([trade('KRW-B3',100950,111)])
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    after = read(path)
    changes = review.compare_event_capture({'event_capture':before}, {'event_capture':after})
    assert changes['bithumb|KRW-B3']['observation'] == 'advanced'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original
    store.close()


def test_actual_saved_subscription_is_sanitized_not_guessed_from_defaults(tmp_path, monkeypatch):
    path = tmp_path/'b3_trader/data/auto_demo.sqlite3'
    path.parent.mkdir(parents=True)
    store = database(path);store.close()
    status = tmp_path/runtime_review.STATUS_FILES['market_flow']
    status.parent.mkdir(parents=True)
    status.write_text(json.dumps({'pid':42,'started_at':1000,'running':True,
        'markets':['KRW-B3','KRW-BTC','KRW-ETH','private-list-value'],
        'exchanges':{'bithumb':{'connected':True,'last_trade_ts':100005,
                              'last_error':'private-error','endpoint':'private-endpoint'}}}))
    # A saved subscription file whose process has died is not a live subscription.
    monkeypatch.setattr(runtime_review,'_processes',lambda _: {'status':'read','items':[]})
    result = runtime_review.read_runtime(path)
    saved = result['saved_statuses']['market_flow']
    assert saved['process_observation'] == 'absent' and saved['saved_owner_matches'] is False
    assert saved['subscription']['membership']['KRW-B3'] is True
    assert saved['subscription']['scope'] == 'saved_configuration'
    assert saved['subscription']['market_count'] == 4
    assert 'private-' not in json.dumps(result)
    assert review.stream_subscription_evidence({'markets':['KRW-BTC','KRW-ETH']})['membership']['KRW-B3'] is False
    assert review.stream_subscription_evidence({})['membership']['KRW-B3'] is None


def test_subscription_does_not_borrow_global_union_or_pending_list():
    value={'markets':['KRW-BTC','KRW-ETH','KRW-B3'],
           'markets_by_exchange':{'bithumb':['KRW-BTC','KRW-ETH','KRW-B3']},
           'exchanges':{'bithumb':{'markets':['KRW-BTC','KRW-ETH']}}}
    assert review.stream_subscription_evidence(value)['membership']['KRW-B3'] is False
    value['exchanges']['bithumb']['markets']=None
    assert review.stream_subscription_evidence(value)['membership']['KRW-B3'] is None


def test_retention_count_can_be_bounded_without_claiming_continuity(tmp_path, monkeypatch):
    path = tmp_path/'count.db'
    store = database(path)
    store.insert_trades([trade('KRW-B3',t) for t in (99000,99500,100001)])
    monkeypatch.setattr(review,'ROW_COUNT_LIMIT',2)
    result = read(path)['markets']['KRW-B3']['raw']
    assert result['row_count'] == 2 and result['row_count_capped'] is True
    assert result['first']['trade_ts'] == 99000 and result['last']['trade_ts'] == 100001
    store.close()


def test_rest_coverage_and_disconnected_websocket_are_separate_evidence(tmp_path):
    from b3_trader.market_flow_stream_store import MarketFlowStreamStore
    path = tmp_path/'routes.db'
    store = database(path)
    store.insert_trades([trade('KRW-B3',99999)])
    store.upsert_cursor('bithumb','KRW-B3',dict(coverage_start_ts=99000,
        covered_through_ts=100000,last_seen_trade_ts=99999,last_cycle_complete=True,
        last_pages=2,last_rows=20,updated_at=100010))
    stream = MarketFlowStreamStore(path)
    stream.mark_connected('bithumb',['KRW-BTC'],process_started_at=99000,connected_since=99001,reconnects=1)
    stream.mark_disconnected('bithumb',['KRW-BTC'],disconnected_at=100000)
    stream.close();store.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = read(path)['markets']
    b3 = result['KRW-B3']
    assert b3['rest_cursor']['last_cycle_complete'] is True
    assert b3['rest_cursor']['last_rows'] == 20
    assert b3['rest_cursor']['covered_through_ts'] == 100000
    assert b3['websocket_session']['present'] is False
    assert result['KRW-BTC']['websocket_session']['connected'] is False
    assert result['KRW-BTC']['websocket_session']['last_disconnect_at'] == 100000
    assert result['KRW-BTC']['websocket_session']['last_trade_ts'] is None
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
