import json
import threading
from types import SimpleNamespace

import pytest

from b3_trader import market_flow_stream as stream
from b3_trader import market_flow_store
from b3_trader.event_price_archive import POINTS, TABLE
from b3_trader.event_reaction_view import read_event_context
from b3_trader.intelligence_event_response import IntelligenceEventResponseCollector
from b3_trader.market_flow_stream_store import MarketFlowStreamStore
from b3_trader.tests.test_event_price_archive import database, trade


def message(market, stamp, price, seq):
    return json.dumps({'type':'trade','code':market,'trade_timestamp':stamp,
                      'trade_price':price,'trade_volume':1,'ask_bid':'BID','sequential_id':seq})


def test_refresh_reconnects_changed_venue_only():
    service=stream.MarketFlowStreamService(markets=stream.DEFAULT_MARKETS)
    desired={'bithumb':(*stream.DEFAULT_MARKETS,'KRW-B3'),'upbit':stream.DEFAULT_MARKETS}
    service.selector=SimpleNamespace(refresh=lambda now:desired,evidence={})
    closed=[]
    for exchange in stream.ENDPOINTS:
        worker=stream.StreamWorker(exchange,stream.DEFAULT_MARKETS,service.stop_event,
                                   service.states[exchange],service.state_lock,1000)
        worker.app=SimpleNamespace(close=lambda e=exchange:closed.append(e))
        service.workers[exchange]=worker
    service._refresh_subscriptions(1001)
    service._refresh_subscriptions(1002)
    assert closed==['bithumb']
    assert service.workers['bithumb'].markets==stream.DEFAULT_MARKETS  # Worker owns switch after flush.
    assert service.workers['bithumb'].pending_markets==desired['bithumb']
    assert not service.stop_event.is_set()


def test_worker_flushes_old_ticks_before_subscription_change_and_resets_continuity(tmp_path,monkeypatch):
    db=tmp_path/'stream.db'
    monkeypatch.setattr(stream,'MarketFlowStreamStore',lambda:MarketFlowStreamStore(db))
    for name in ('MarketFlowOrderbookStreamStore','MarketOrderbookLadderStore'):
        monkeypatch.setattr(stream,name,lambda:SimpleNamespace(close=lambda:None))
    stop=threading.Event();state={}; subscriptions=[]; reconnect_sessions=[]
    worker=stream.StreamWorker('bithumb',stream.DEFAULT_MARKETS,stop,state,threading.RLock(),1000)
    desired=(*stream.DEFAULT_MARKETS,'KRW-B3')
    class Socket:
        def __init__(self,url,**callbacks): self.callbacks=callbacks
        def close(self): pass
        def send(self,value): subscriptions.append(json.loads(value)[1]['codes'])
        def run_forever(self,**kwargs):
            self.callbacks['on_open'](self)
            if len(subscriptions)==1:
                worker.last_flush_at=stream.time.time()  # Keep this tick buffered until close.
                self.callbacks['on_message'](self,message('KRW-BTC',1001,100,'old'))
                assert len(worker.buffer)==1
                worker.request_markets(desired)
            else:
                reconnect_sessions.append(worker.store.session('bithumb','KRW-BTC'))
                assert worker.store.conn.execute('SELECT COUNT(*) FROM research_market_trade_flow_mx').fetchone()[0]==1
                self.callbacks['on_message'](self,message('KRW-B3',1002,1,'new'))
                stop.set()
            self.callbacks['on_close'](self,1000,'closed')
    monkeypatch.setattr(stream.websocket,'WebSocketApp',Socket)
    worker.run()
    assert subscriptions==[list(stream.DEFAULT_MARKETS),list(desired)]
    assert reconnect_sessions[0]['session_cvd_quote']==0
    assert reconnect_sessions[0]['reconnects']==1
    assert state['markets']==list(desired) and state['connected'] is False
    store=MarketFlowStreamStore(db)
    try:
        assert {r['market'] for r in store.conn.execute('SELECT market FROM research_market_trade_flow_mx')}=={'KRW-BTC','KRW-B3'}
        assert store.session('bithumb','KRW-B3')['connected']==0
    finally: store.close()


def test_websocket_ticks_survive_retention_and_reach_all_four_viewer_horizons(tmp_path,monkeypatch):
    db=tmp_path/'event.db';prices=database(db);ticks=MarketFlowStreamStore(db)
    markets=('KRW-B3','KRW-BTC','KRW-ETH')
    worker=stream.StreamWorker('bithumb',markets,threading.Event(),{},threading.RLock(),99000)
    worker.store=ticks
    service=stream.MarketFlowStreamService(markets=markets)
    service.markets_by_exchange={'bithumb':markets}
    try:
        for point,offset in POINTS.items():
            stamp=100000+offset+(-1 if point=='baseline' else 1)
            monkeypatch.setattr(stream.time,'time',lambda s=stamp:s+2)
            for n,market in enumerate(markets):
                worker._on_message(None,message(market,stamp,100 if point=='baseline' else 110+n,point))
            worker._flush(force=True)
            # More than the configured raw retention between each observation.
            for market in markets:
                ticks.insert_trades([trade(market,100000+offset+700+i/100,999,seq=f'burst:{point}:{i}') for i in range(1001)])
            monkeypatch.setattr(market_flow_store.time,'time',lambda s=offset:100000+s+800)
            service._preserve_prices(prices)
            assert service.last_price_archive_error==''
        assert prices.conn.execute("SELECT COUNT(*) FROM research_market_trade_flow_mx WHERE sequential_id NOT LIKE 'burst:%'").fetchone()[0]==0
        assert prices.conn.execute(f'SELECT COUNT(*) FROM {TABLE}').fetchone()[0]==15
        collector=IntelligenceEventResponseCollector(prices.conn,benchmarks=[('bithumb',m) for m in markets])
        result=collector.run_once(now=187300)
        assert result['samples_inserted']==12
        view=read_event_context(prices.conn,'bithumb','KRW-B3',now=187300)[0]
        for horizon in ('15m','1h','4h','1d'):
            response=view['responses'][horizon]
            assert response['coin']==pytest.approx(10)
            assert response['vs_btc_pp']==pytest.approx(-1)
            assert response['vs_eth_pp']==pytest.approx(-2)
        assert collector.run_once(now=187300)['samples_inserted']==0
    finally:
        ticks.close();prices.close()
