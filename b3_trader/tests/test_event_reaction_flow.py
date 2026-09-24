from __future__ import annotations

import hashlib
import sqlite3

from b3_trader.event_reaction_view import read_event_context
from b3_trader.intelligence_event_response import IntelligenceEventResponseCollector
from b3_trader.tests.test_intelligence_event_response import _init_db, _insert_event


def setup(path):
    _init_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    for column in ('source_url TEXT', 'published_at REAL', 'scheduled_at REAL', 'received_at REAL'):
        conn.execute('ALTER TABLE research_intelligence_events ADD COLUMN '+column)
    conn.commit()
    return conn


def trade(conn, market, stamp, price, *, exchange='bithumb'):
    conn.execute('INSERT INTO research_market_trade_flow_mx VALUES(?,?,?,?,?)',
                 (exchange, market, f'{market}:{stamp}', stamp, price))
    conn.commit()


def event(path, conn, *, name, stamp, gain, market='KRW-B3', source='us_bls_release_calendar'):
    _insert_event(path, event_id=name, event_ts=stamp, source_id=source)
    trade(conn, market, stamp-1, 100)
    trade(conn, market, stamp+901, 100+gain)


def test_default_collector_includes_observed_coins_but_explicit_scope_stays_exact(tmp_path):
    db=tmp_path/'coins.db';conn=setup(db)
    event(db,conn,name='release',stamp=100000,gain=5)
    trade(conn,'KRW-B3',99999,200,exchange='upbit')
    trade(conn,'KRW-B3',100901,196,exchange='upbit')
    trade(conn,'USDT-B3',99999,1,exchange='upbit')
    trade(conn,'USDT-B3',100901,2,exchange='upbit')
    exact=IntelligenceEventResponseCollector(conn,benchmarks=(('bithumb','KRW-BTC'),))
    assert exact.run_once(now=101000)['samples_inserted']==0
    conn.executescript('''CREATE TABLE research_market_flow_cursor_mx(exchange TEXT,market TEXT);
        INSERT INTO research_market_flow_cursor_mx VALUES('bithumb','KRW-B3');
        CREATE TABLE research_market_flow_stream_session_mx(exchange TEXT,market TEXT);
        INSERT INTO research_market_flow_stream_session_mx VALUES('upbit','KRW-B3');
        INSERT INTO research_market_flow_stream_session_mx VALUES('upbit','USDT-B3');''')
    full=IntelligenceEventResponseCollector(conn)
    result=full.run_once(now=101000)
    assert result['markets_considered']==6
    assert result['samples_inserted']==2
    rows=conn.execute('SELECT exchange,market,return_pct FROM research_intelligence_event_responses ORDER BY exchange').fetchall()
    assert [(r['exchange'],r['market']) for r in rows]==[('bithumb','KRW-B3'),('upbit','KRW-B3')]
    assert abs(rows[0]['return_pct']-5)<1e-9 and abs(rows[1]['return_pct']+2)<1e-9
    assert full.run_once(now=101000)['samples_inserted']==0
    conn.close()


def test_later_horizons_survive_raw_baseline_pruning_and_restart(tmp_path):
    db=tmp_path/'retention.db';conn=setup(db)
    event(db,conn,name='release',stamp=200000,gain=1)
    collector=IntelligenceEventResponseCollector(conn,benchmarks=(('bithumb','KRW-B3'),))
    assert collector.run_once(now=201000)['samples_inserted']==1
    # Simulate existing raw retention in this temporary fixture only.
    conn.execute('DELETE FROM research_market_trade_flow_mx');conn.commit();conn.close()
    conn=sqlite3.connect(db);conn.row_factory=sqlite3.Row
    trade(conn,'KRW-B3',200000+86401,108)
    collector=IntelligenceEventResponseCollector(conn,benchmarks=(('bithumb','KRW-B3'),))
    result=collector.run_once(now=200000+86410)
    assert result['samples_inserted']==result['saved_baseline_used']==1
    row=conn.execute("SELECT * FROM research_intelligence_event_responses WHERE horizon_label='1d'").fetchone()
    assert row['baseline_trade_ts']==199999 and row['baseline_price']==100
    assert abs(row['return_pct']-8)<1e-9
    assert conn.execute("SELECT COUNT(*) FROM research_intelligence_event_responses WHERE horizon_label IN ('1h','4h')").fetchone()[0]==0
    conn.close()


def test_future_trade_is_not_used_before_it_occurs(tmp_path):
    db=tmp_path/'future.db';conn=setup(db)
    event(db,conn,name='release',stamp=300000,gain=2)
    collector=IntelligenceEventResponseCollector(conn,benchmarks=(('bithumb','KRW-B3'),))
    assert collector.run_once(now=300900)['samples_inserted']==0
    assert collector.run_once(now=300901)['samples_inserted']==1
    conn.close()


def test_revised_event_clock_does_not_rewrite_or_mix_saved_horizons(tmp_path):
    db=tmp_path/'revision.db';conn=setup(db)
    event(db,conn,name='release',stamp=400000,gain=3)
    collector=IntelligenceEventResponseCollector(conn,benchmarks=(('bithumb','KRW-B3'),))
    collector.run_once(now=401000)
    before=tuple(conn.execute('SELECT * FROM research_intelligence_event_responses').fetchone())
    conn.execute('UPDATE research_intelligence_events SET source_ts=source_ts+10');conn.commit()
    trade(conn,'KRW-B3',400009,110);trade(conn,'KRW-B3',403611,120)
    result=collector.run_once(now=404000)
    assert result['ok'] is False and result['anchor_conflicts']>0
    assert tuple(conn.execute('SELECT * FROM research_intelligence_event_responses').fetchone())==before
    assert conn.execute('SELECT COUNT(*) FROM research_intelligence_event_responses').fetchone()[0]==1
    views=read_event_context(conn,'bithumb','KRW-B3',now=404000)
    shown=next(e for e in views if e['event_ts']==400000)
    assert shown['event_ts']==400000 and shown['source_ts']==400010 and shown['anchor_changed']
    revised=next(e for e in views if e['event_ts']==400010)
    assert revised['responses']['15m']['coin'] is None and revised['anchor_conflict']
    assert revised['price_progress']['coin']['1h']['status']=='invalid_response'
    assert revised['price_progress']['coin']['1h']['target']['price']==120
    conn.close()


def test_event_view_matches_baselines_benchmarks_and_past_available_samples(tmp_path):
    db=tmp_path/'view.db';conn=setup(db)
    collector=IntelligenceEventResponseCollector(conn)
    event(db,conn,name='old',stamp=500000,gain=2)
    collector.run_once(now=501000)
    event(db,conn,name='late-known',stamp=510000,gain=40)
    event(db,conn,name='other-source',stamp=515000,gain=90,source='us_bea_release_schedule')
    event(db,conn,name='current',stamp=520000,gain=5)
    for market,price in [('KRW-BTC',101),('KRW-ETH',98)]:
        trade(conn,market,519999,100);trade(conn,market,520901,price)
    collector.run_once(now=521000)
    event(db,conn,name='future-event',stamp=530000,gain=80)
    collector.run_once(now=531000)
    conn.close();before=hashlib.sha256(db.read_bytes()).hexdigest()
    ro=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True);ro.row_factory=sqlite3.Row
    ro.execute('PRAGMA query_only=ON')
    events=read_event_context(ro,'bithumb','KRW-B3')
    current=next(e for e in events if e['event_id']=='current')
    r=current['responses']['15m']
    assert abs(r['coin']-5)<1e-9 and abs(r['btc']-1)<1e-9 and abs(r['eth']+2)<1e-9
    assert abs(r['vs_btc_pp']-4)<1e-9 and abs(r['vs_eth_pp']-7)<1e-9
    assert r['observations']['coin']['baseline_trade_ts']==519999
    h=current['history']['15m']
    assert h['samples']==1 and abs(h['mean_pct']-2)<1e-9
    assert current['history']['1d']['samples']==0 and current['history']['1d']['mean_pct'] is None
    assert read_event_context(ro,'upbit','KRW-B3')==[]
    ro.close();assert hashlib.sha256(db.read_bytes()).hexdigest()==before


def test_corrupt_saved_response_blocks_anchor_reuse_and_is_not_shown_as_zero(tmp_path):
    db=tmp_path/'bad.db';conn=setup(db)
    event(db,conn,name='release',stamp=600000,gain=1)
    collector=IntelligenceEventResponseCollector(conn,benchmarks=(('bithumb','KRW-B3'),))
    collector.run_once(now=601000)
    conn.execute('UPDATE research_intelligence_event_responses SET return_pct=999');conn.commit()
    trade(conn,'KRW-B3',603601,103)
    result=collector.run_once(now=604000)
    assert result['anchor_conflicts'] and not result['samples_inserted']
    row=read_event_context(conn,'bithumb','KRW-B3')[0]
    assert row['responses']['15m']['coin'] is None and row['invalid_observations']==1
    conn.close()
