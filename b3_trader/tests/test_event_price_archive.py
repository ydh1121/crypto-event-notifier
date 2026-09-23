import sqlite3

import pytest

from b3_trader import event_price_archive as archive
from b3_trader import market_flow_store
from b3_trader.event_reaction_view import read_event_context
from b3_trader.intelligence_event_response import IntelligenceEventResponseCollector


def database(path):
    store = market_flow_store.MarketFlowStore(path, trade_retention=1000)
    store.conn.execute('''CREATE TABLE research_intelligence_events (
        event_id TEXT PRIMARY KEY,event_type TEXT,source_id TEXT,title TEXT,source_ts REAL,
        source_url TEXT,published_at REAL,scheduled_at REAL,received_at REAL)''')
    store.conn.execute('''INSERT INTO research_intelligence_events VALUES (
        'release','US_EMPLOYMENT','us_bls_release_calendar','Fixture',100000,
        'https://example.test',100000,100000,100000)''')
    store.conn.commit()
    return store


def trade(market, ts, price=100, *, seq=None, exchange='bithumb'):
    return dict(exchange=exchange, market=market, sequential_id=seq or str(ts),
                trade_ts=ts, trade_price=price, trade_volume=1, quote_volume=price,
                aggressor_side='BID', received_at=ts+1)


def test_pruning_before_first_reaction_preserves_all_horizons_and_view_values(tmp_path, monkeypatch):
    path = tmp_path/'prices.db'
    store = database(path)
    coins = ('KRW-B3','KRW-BTC','KRW-ETH')
    # No reaction collector runs until all five exact price points have been
    # evicted from raw history by the real production pruning function.
    for point, seconds in archive.POINTS.items():
        for n, market in enumerate(coins):
            stamp = 100000 + seconds + (-1 if point == 'baseline' else 1)
            price = 100 if point == 'baseline' else 110 + n
            store.insert_trades([trade(market, stamp, price, seq=point)])
            store.insert_trades([trade(market, 100000+seconds+700+i/100, 999,
                                      seq=f'burst:{point}:{i}') for i in range(1001)])
            monkeypatch.setattr(market_flow_store.time, 'time', lambda s=seconds: 100000+s+800)
            assert store.prune_trades('bithumb',market) > 0
    assert store.conn.execute("SELECT COUNT(*) FROM research_market_trade_flow_mx WHERE sequential_id NOT LIKE 'burst:%'").fetchone()[0] == 0
    assert store.conn.execute(f'SELECT COUNT(*) FROM {archive.TABLE}').fetchone()[0] == 15
    store.close()
    conn = sqlite3.connect(path);conn.row_factory = sqlite3.Row
    collector = IntelligenceEventResponseCollector(conn, benchmarks=[('bithumb',m) for m in coins])
    result = collector.run_once(now=187300)
    assert result['samples_inserted'] == 12
    assert result['archived_baseline_used'] == result['archived_target_used'] == 12
    assert result['missing_baseline'] == result['missing_target'] == 0
    view = read_event_context(conn,'bithumb','KRW-B3')[0]
    for point, _ in archive.HORIZONS:
        response = view['responses'][point]
        assert response['coin'] == pytest.approx(10)
        assert response['btc'] == pytest.approx(11)
        assert response['eth'] == pytest.approx(12)
        assert response['vs_btc_pp'] == pytest.approx(-1)
        assert response['vs_eth_pp'] == pytest.approx(-2)
        assert response['observations']['coin']['baseline_trade_ts'] == 99999
    assert collector.run_once(now=187300)['samples_inserted'] == 0
    conn.close()


def test_first_early_cycle_saves_baseline_before_target_is_due(tmp_path):
    store = database(tmp_path/'early.db')
    store.insert_trades([trade('KRW-B3',99999)])
    collector = IntelligenceEventResponseCollector(store.conn, benchmarks=[('bithumb','KRW-B3')])
    result = collector.run_once(now=100005)
    assert result['samples_inserted'] == 0 and result['prices_archived'] == 1
    store.conn.execute('DELETE FROM research_market_trade_flow_mx');store.conn.commit()
    store.insert_trades([trade('KRW-B3',100901,105)])
    result = collector.run_once(now=101000)
    assert result['samples_inserted'] == result['archived_baseline_used'] == 1
    store.close()


def test_archive_does_not_fabricate_outage_prices_or_relax_tolerance(tmp_path):
    store = database(tmp_path/'outage.db')
    # One price is too old for the normal 120s contract; the other is after
    # publication. Neither is a valid baseline even though they exist locally.
    store.insert_trades([trade('KRW-B3',99500),trade('KRW-B3',100001),trade('KRW-B3',100901,105)])
    collector = IntelligenceEventResponseCollector(store.conn, benchmarks=[('bithumb','KRW-B3')])
    result = collector.run_once(now=101000)
    assert result['samples_inserted'] == 0 and result['missing_baseline'] == 1
    assert store.conn.execute('SELECT COUNT(*) FROM research_intelligence_event_responses').fetchone()[0] == 0
    store.close()


def test_revision_and_exchange_cannot_borrow_another_price(tmp_path):
    store = database(tmp_path/'identity.db')
    store.insert_trades([trade('KRW-B3',99999)])
    archive.capture_market(store.conn,'bithumb','KRW-B3',100000)
    event = dict(store.conn.execute('SELECT * FROM research_intelligence_events').fetchone())
    assert archive.read_price(store.conn,event,'upbit','KRW-B3','baseline',100000,120) is None
    assert archive.read_price(store.conn,event,'bithumb','KRW-OTHER','baseline',100000,120) is None
    event['source_ts'] += 1
    assert archive.read_price(store.conn,event,'bithumb','KRW-B3','baseline',100001,120) is None
    store.close()


def test_closest_observation_can_improve_before_reaction_and_no_future_tick_is_used(tmp_path):
    store = database(tmp_path/'late.db')
    store.insert_trades([trade('KRW-B3',99950),trade('KRW-B3',100910,110)])
    archive.capture_market(store.conn,'bithumb','KRW-B3',100905)
    assert store.conn.execute(f"SELECT COUNT(*) FROM {archive.TABLE} WHERE point='15m'").fetchone()[0] == 0
    store.insert_trades([trade('KRW-B3',99999,101),trade('KRW-B3',100901,109)])
    archive.capture_market(store.conn,'bithumb','KRW-B3',100920)
    event = dict(store.conn.execute('SELECT * FROM research_intelligence_events').fetchone())
    assert archive.read_price(store.conn,event,'bithumb','KRW-B3','baseline',100920,120)['trade_price'] == 101
    assert archive.read_price(store.conn,event,'bithumb','KRW-B3','15m',100920,120)['trade_ts'] == 100901
    assert archive.read_price(store.conn,event,'bithumb','KRW-B3','baseline',100910,120) is None
    store.close()


def test_failed_price_preservation_rolls_back_without_pruning(tmp_path, monkeypatch):
    store = database(tmp_path/'rollback.db')
    store.insert_trades([trade('KRW-B3',99999)])
    store.insert_trades([trade('KRW-B3',100700+i/100) for i in range(1001)])
    def fail(conn, exchange, market, now):
        archive.capture_market(conn,exchange,market,100800)
        raise sqlite3.OperationalError('fixture failure after archive write')
    monkeypatch.setattr(market_flow_store,'capture_market',fail)
    with pytest.raises(sqlite3.OperationalError):
        store.prune_trades('bithumb','KRW-B3')
    assert store.conn.execute('SELECT COUNT(*) FROM research_market_trade_flow_mx').fetchone()[0] == 1002
    assert store.conn.execute(f'SELECT COUNT(*) FROM {archive.TABLE}').fetchone()[0] == 0
    store.close()
