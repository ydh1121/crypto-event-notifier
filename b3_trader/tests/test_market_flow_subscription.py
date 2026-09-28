import json
import sqlite3
from types import SimpleNamespace

from b3_trader.market_flow_subscription import DEFAULT_MARKETS, MAX_MARKETS, SubscriptionSelector


def inputs(root, *, profiles=(), holdings=()):
    control = root/'control/assets.json'; control.parent.mkdir(parents=True, exist_ok=True)
    control.write_text(json.dumps({'assets': list(profiles)}))
    db = root/'b3_trader/data/crypto_trader.sqlite3'; db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS manual_holdings(market TEXT,volume REAL,avg_price REAL,updated_ts REAL,exchange TEXT)')
        conn.execute('DELETE FROM manual_holdings')
        conn.executemany('INSERT INTO manual_holdings VALUES(?,?,100,1,?)', holdings)
    return db


def catalogs(extra, calls=None):
    def get(exchange):
        if calls is not None: calls.append(exchange)
        return [SimpleNamespace(exchange=exchange,market=m) for m in (*DEFAULT_MARKETS,*extra.get(exchange,()))]
    return get


def test_existing_profiles_and_confirmed_holdings_select_per_venue_without_writes(tmp_path, monkeypatch):
    monkeypatch.delenv('B3_JOURNAL_DB', raising=False)
    db = inputs(tmp_path, profiles=[{'enabled':True,'market':m} for m in ('KRW-B3','KRW-ETH/BTC','KRW-UP')],
                holdings=[('KRW-SLX',1,None), ('KRW-CLOSED',0,'bithumb'), ('KRW-NEW',2,'upbit')])
    before = db.read_bytes()
    selection = SubscriptionSelector(tmp_path, environment={'MARKET_FLOW_HOLDINGS_EXCHANGE':'bithumb'},
        catalog=catalogs({'bithumb':('KRW-B3','KRW-UP','KRW-SLX','KRW-CLOSED','KRW-NEW'),
                          'upbit':('KRW-UP','KRW-NEW')}))
    result = selection.refresh(1000)
    assert result['bithumb'] == (*DEFAULT_MARKETS,'KRW-NEW','KRW-SLX','KRW-B3','KRW-UP')
    assert result['upbit'] == (*DEFAULT_MARKETS,'KRW-UP')
    assert all('KRW-ETH/BTC' not in values for values in result.values())
    assert db.read_bytes() == before


def test_added_holding_refreshes_without_other_venue_reconnect_and_failed_reads_preserve_inputs(tmp_path, monkeypatch):
    monkeypatch.delenv('B3_JOURNAL_DB', raising=False)
    db = inputs(tmp_path,holdings=[('KRW-B3',1,'bithumb')])
    calls=[]
    selection=SubscriptionSelector(tmp_path,environment={},catalog=catalogs({'bithumb':('KRW-B3','KRW-NEW')},calls))
    first=selection.refresh(1000)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO manual_holdings VALUES('KRW-NEW',1,100,2,'bithumb')")
    second=selection.refresh(1060)
    assert second['bithumb'] == (*DEFAULT_MARKETS,'KRW-B3','KRW-NEW')
    assert second['upbit'] == first['upbit'] and len(calls)==2
    (tmp_path/'control/assets.json').write_text('{unfinished')
    db.rename(db.with_suffix('.saved'))
    def fail(exchange): raise RuntimeError('private request URL must not reach evidence')
    selection.catalog=fail
    assert selection.refresh(1400)==second
    assert selection.evidence['bithumb']['catalog_status']=='cached'
    assert selection.evidence['bithumb']['holdings_status']=='db_missing'
    assert 'private' not in json.dumps(selection.evidence)
    assert not db.exists()


def test_capacity_never_drops_benchmarks_and_overflow_is_explicit(tmp_path):
    names=tuple('KRW-C'+str(i) for i in range(20))
    inputs(tmp_path)
    selection=SubscriptionSelector(tmp_path,environment={'MARKET_FLOW_STREAM_MARKETS':','.join(names)},
                                   catalog=catalogs({'bithumb':names,'upbit':names[:2]}))
    result=selection.refresh(1000)
    assert result['bithumb']==(*DEFAULT_MARKETS,*names[:MAX_MARKETS-2])
    assert selection.evidence['bithumb']['deferred_markets']==list(names[MAX_MARKETS-2:])
    assert result['upbit']==(*DEFAULT_MARKETS,*names[:2])


def test_unavailable_catalog_does_not_subscribe_unverified_coin_then_recovers(tmp_path):
    inputs(tmp_path,profiles=[{'enabled':True,'market':'KRW-B3'}])
    def fail(exchange): raise TimeoutError()
    selection=SubscriptionSelector(tmp_path,environment={},catalog=fail)
    assert selection.refresh(1000)==dict.fromkeys(('bithumb','upbit'),DEFAULT_MARKETS)
    assert selection.evidence['bithumb']['catalog_status']=='unavailable'
    selection.catalog=catalogs({'bithumb':('KRW-B3',)})
    assert selection.refresh(1060)['bithumb']==(*DEFAULT_MARKETS,'KRW-B3')
