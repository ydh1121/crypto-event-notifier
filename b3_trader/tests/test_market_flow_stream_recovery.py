"""Venue failure recovery: real SQLite contention and independent worker health."""
import json
import sqlite3
import threading
from types import SimpleNamespace

import pytest

from b3_trader import market_flow_stream as stream
from b3_trader.event_capture_review import stream_subscription_evidence
from b3_trader.market_flow_stream_store import MarketFlowStreamStore
from b3_trader.tests.test_market_flow_subscription_runtime import message


class FastStop:
    def __init__(self, on_wait=lambda: None):
        self.stopped = False
        self.waits = []
        self.on_wait = on_wait

    def is_set(self):
        return self.stopped

    def set(self):
        self.stopped = True

    def wait(self, delay):
        self.waits.append(delay)
        self.on_wait()
        if len(self.waits) > 8:
            self.set()
        return self.stopped


def no_aux_stores(monkeypatch):
    for name in ('MarketFlowOrderbookStreamStore', 'MarketOrderbookLadderStore'):
        monkeypatch.setattr(stream, name, lambda: SimpleNamespace(close=lambda: None))


def worker(stop=None):
    return stream.StreamWorker('upbit', stream.DEFAULT_MARKETS, stop or FastStop(), {}, threading.RLock(), 1000)


def test_close_with_real_sqlite_lock_retries_and_keeps_buffer_before_new_session(tmp_path, monkeypatch):
    db = tmp_path/'stream.sqlite3'
    connections = []
    def store():
        value = MarketFlowStreamStore(db)
        value.conn.execute('PRAGMA busy_timeout=1')
        connections.append(value.conn)
        return value
    monkeypatch.setattr(stream, 'MarketFlowStreamStore', store)
    no_aux_stores(monkeypatch)
    locks = []
    def release():
        for conn in locks:
            conn.rollback()
    stop = FastStop(release)
    target = worker(stop)
    sockets = []
    class Socket:
        def __init__(self, url, **callbacks):
            self.callbacks = callbacks
            self.on_error = callbacks['on_error']
            sockets.append(self)
        def close(self):
            pass
        def send(self, payload):
            assert json.loads(payload)[1]['codes'] == list(stream.DEFAULT_MARKETS)
        def run_forever(self, **kwargs):
            self.callbacks['on_open'](self)
            if len(sockets) == 1:
                target.last_flush_at = stream.time.time()
                self.callbacks['on_message'](self, message('KRW-BTC',1001,100,'buffered'))
                assert len(target.buffer) == 1
                lock = sqlite3.connect(db)
                lock.execute('BEGIN IMMEDIATE')
                locks.append(lock)
            else:
                assert target.store.conn.execute('SELECT COUNT(*) FROM research_market_trade_flow_mx').fetchone()[0] == 1
                assert target.store.session('upbit','KRW-BTC')['session_cvd_quote'] == 0
                stop.set()
            # Match the library callback contract: callback exceptions go to
            # on_error; finally must still keep the reconnect owner alive.
            try:
                self.callbacks['on_close'](self,1000,'fixture')
            except Exception as exc:
                self.on_error(self,exc)
    monkeypatch.setattr(stream.websocket, 'WebSocketApp', Socket)
    try:
        target.run()
        assert len(sockets) == 2 and stop.waits == [1]
        assert target.state['worker_failures'] == 1
        assert target.state['last_failure_kind'] == 'OperationalError'
        assert target.state['connected'] is False and not target.buffer
        with sqlite3.connect(db) as conn:
            assert conn.execute('SELECT COUNT(*) FROM research_market_trade_flow_mx').fetchone()[0] == 1
        for conn in connections:
            with pytest.raises(sqlite3.ProgrammingError):
                conn.execute('SELECT 1')
    finally:
        for conn in locks:
            conn.rollback(); conn.close()


def test_initialization_failure_retries_with_bounded_backoff_and_stops(monkeypatch):
    stop = FastStop()
    target = worker(stop)
    def unavailable():
        raise sqlite3.OperationalError('database is locked')
    monkeypatch.setattr(stream, 'MarketFlowStreamStore', unavailable)
    target.run()
    assert stop.waits == [1,2,4,8,16,30,30,30,30]
    assert target.state['worker_failures'] == 9
    assert target.state['connected'] is False


def test_partial_initialization_closes_every_resource_even_when_close_fails(monkeypatch):
    closed = []
    stop = FastStop()
    def close():
        closed.append('flow')
        raise OSError('fixture close')
    monkeypatch.setattr(stream,'MarketFlowStreamStore',lambda:SimpleNamespace(close=close,mark_disconnected=lambda *a,**k:None))
    monkeypatch.setattr(stream,'MarketFlowOrderbookStreamStore',lambda:SimpleNamespace(close=lambda:closed.append('book')))
    def fail():
        stop.set()
        raise sqlite3.OperationalError('fixture init')
    monkeypatch.setattr(stream,'MarketOrderbookLadderStore',fail)
    target=worker(stop);target.run()
    assert closed == ['flow','book']
    assert target.store is target.orderbook_store is target.ladder_store is None
    assert target.state['worker_failures'] == 1


def test_callback_db_failure_closes_socket_to_leave_receive_loop():
    target=worker();closed=[]
    target.app=SimpleNamespace(close=lambda:closed.append(True))
    target._on_error(target.app,sqlite3.OperationalError('fixture callback'))
    assert closed == [True] and target.state['status'] == 'reconnecting'


def test_connected_socket_without_market_messages_is_not_healthy():
    state={'connected':True,'connected_since':1000}
    assert stream.stream_health(state,True,1050)==dict(worker_alive=True,data_age_seconds=None,health='waiting',healthy=False)
    assert stream.stream_health(state,True,1121)['health']=='stale'


def test_retry_keeps_event_samples_and_rebinds_connection_before_socket(monkeypatch):
    stop=FastStop();target=worker(stop);old=object();new=object();flushed=[]
    sampler=SimpleNamespace(conn=old,pending={'real-tick':1},flush=lambda *a,**k:flushed.append(sampler.conn))
    target.event_sampler=sampler
    monkeypatch.setattr(stream,'MarketFlowStreamStore',lambda:SimpleNamespace(conn=new,close=lambda:None,mark_disconnected=lambda *a,**k:None))
    no_aux_stores(monkeypatch)
    class Socket:
        def __init__(self,*a,**k): pass
        def close(self): pass
        def run_forever(self,**k):
            assert sampler.pending == {'real-tick':1} and flushed == [new]
            target.event_sampler=None;stop.set()
    monkeypatch.setattr(stream.websocket,'WebSocketApp',Socket)
    target.run()
    assert sampler.conn is new


def test_dead_venue_is_restarted_once_without_touching_live_venue(monkeypatch):
    service=stream.MarketFlowStreamService(markets=stream.DEFAULT_MARKETS)
    service.threads['bithumb']=SimpleNamespace(is_alive=lambda:True)
    service.states['bithumb'].update(connected=True,last_socket_message_at=1000)
    launches=[]
    class Thread:
        alive=False
        def __init__(self,**kwargs): launches.append(kwargs['name'])
        def start(self): self.alive=True
        def is_alive(self): return self.alive
    monkeypatch.setattr(stream.threading,'Thread',Thread)
    service._ensure_workers(1000);service._ensure_workers(1001)
    assert launches == ['market-flow-stream-upbit']
    service.threads['upbit'].alive=False
    service._ensure_workers(1002)
    assert len(launches)==1
    service._ensure_workers(1030)
    assert len(launches)==2 and service.states['upbit']['worker_starts']==2
    service.stop_event.set();service.threads['upbit'].alive=False
    service._ensure_workers(1100)
    assert len(launches)==2


def test_stale_socket_reconnects_only_stalled_venue_and_status_is_not_healthy(monkeypatch):
    service=stream.MarketFlowStreamService(markets=stream.DEFAULT_MARKETS)
    closed=[]
    for name in stream.ENDPOINTS:
        target=stream.StreamWorker(name,stream.DEFAULT_MARKETS,service.stop_event,service.states[name],service.state_lock,1000)
        target.app=SimpleNamespace(close=lambda n=name:closed.append(n))
        service.workers[name]=target
        service.threads[name]=SimpleNamespace(is_alive=lambda:True)
        service.states[name].update(connected=True,last_socket_message_at=1000 if name=='upbit' else 1200)
    monkeypatch.setattr(stream.time,'time',lambda:1200)
    status=service._status_payload(running=True)
    assert status['running'] is True and status['ok'] is False and status['health']=='degraded'
    assert status['exchanges']['upbit']['health']=='stale'
    service._ensure_workers(1200);service._ensure_workers(1201)
    assert closed == ['upbit']
    service.states['upbit'].update(connected=True,last_socket_message_at=1200)
    assert service._status_payload(running=True)['ok'] is True
    service.threads['upbit']=SimpleNamespace(is_alive=lambda:False)
    assert service._status_payload(running=True)['exchanges']['upbit']['health']=='worker_stopped'
    service.stop_event.set()
    assert service._status_payload(running=False)['ok'] is False


def test_recovery_health_reaches_readonly_report_and_old_reports_remain_unknown():
    value={'recovery_version':1,'health':'degraded','exchanges':{'upbit':{
        'connected':False,'worker_alive':False,'health':'worker_stopped','worker_starts':2,
        'worker_failures':1,'data_age_seconds':47000,'last_error':'PRIVATE LOCAL PATH',
        'event_markets':['KRW-BTC'],'event_capture':{'messages':703298,'last_trade_ts':1000}}}}
    out=stream_subscription_evidence(value)
    row=out['event_price_collection']['upbit']
    assert row['worker_alive'] is False and row['worker_failures']==1 and row['health']=='worker_stopped'
    assert out['recovery_version']==1 and out['health']=='degraded'
    assert 'PRIVATE' not in json.dumps(out)
    old=stream_subscription_evidence({'exchanges':{'upbit':{'connected':False}}})
    assert old['recovery_version'] is None
    assert old['event_price_collection']['upbit']['worker_alive'] is None
