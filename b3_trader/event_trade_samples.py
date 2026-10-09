"""Bounded real-trade evidence for events across the public KRW universe.

Not a volume/CVD source. One row holds the first and last *actual* trade of a
minute, for six hours only. Known event boundaries additionally keep their exact
observed nearest ticks in the permanent event-price archive. No synthetic OHLCV
prices, extrapolation across disconnects, or strategy/holding mutations.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from contextlib import closing
import math
from pathlib import Path
import sqlite3

TABLE = 'research_event_trade_samples'
RETENTION_SECONDS = 6 * 3600
FLUSH_SECONDS = 30
SAMPLED_PROVIDER = 'local_public_exchange_trade_minute_endpoints'


def exists(conn):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone())


def ensure_schema(conn):
    conn.execute(f'''CREATE TABLE IF NOT EXISTS {TABLE} (
        exchange TEXT NOT NULL, market TEXT NOT NULL, bucket_ts INTEGER NOT NULL,
        first_ts REAL NOT NULL, first_price REAL NOT NULL, first_seq TEXT NOT NULL,
        last_ts REAL NOT NULL, last_price REAL NOT NULL, last_seq TEXT NOT NULL,
        received_at REAL NOT NULL,
        PRIMARY KEY(exchange,market,bucket_ts))''')
    conn.execute(f'CREATE INDEX IF NOT EXISTS idx_event_samples_expiry ON {TABLE}(bucket_ts)')


def prepare_database(path):
    """The only production schema owner: verified shared backup before addition."""
    path = Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as conn:
        if exists(conn):
            return
    from .managed_backup import ensure_backup
    ensure_backup(path, role='paper')
    with closing(sqlite3.connect(path, timeout=10)) as conn:
        with conn:
            ensure_schema(conn)


def candidate(conn, exchange, market, target, baseline, now, tolerance):
    """Nearest stored endpoint, never claimed to be the full tick stream."""
    start, end = ((target-tolerance, target) if baseline else (target, min(now, target+tolerance)))
    if end < start:
        return None
    rows = conn.execute(f'''SELECT * FROM {TABLE} WHERE exchange=? AND market=?
        AND bucket_ts BETWEEN ? AND ?''',
        (exchange, market, int(start//60)*60, int(end//60)*60)).fetchall()
    points = []
    for row in rows:
        for prefix in ('first', 'last'):
            stamp, price = row[prefix+'_ts'], row[prefix+'_price']
            received = row['received_at']
            if (all(isinstance(v, (int, float)) and math.isfinite(v) for v in (stamp, price, received))
                    and start <= stamp <= end and stamp <= received <= now and price > 0):
                points.append(dict(trade_ts=stamp, trade_price=price, sequential_id=row[prefix+'_seq']))
    return (max if baseline else min)(points, key=lambda p:(p['trade_ts'], p['sequential_id'])) if points else None


class EventTradeSampler:
    def __init__(self, conn, exchange, markets):
        self.conn, self.exchange = conn, exchange
        self.markets = set(markets)
        self.pending = {}
        self.exact = {}
        self.boundaries, self.clocks = [], []
        self.next_refresh = self.next_flush = self.next_trim = 0
        self.latest = {}
        self.messages = self.writes = self.archived = self.expired = 0
        self.last_flush = 0
        self.registry_error = ''

    def refresh(self, now):
        if now < self.next_refresh:
            return
        from .event_price_archive import eligible_events, POINTS
        from .event_response_contract import EXCLUDED_EVENT_TYPES, EVENT_LOOKBACK_SECONDS, OBSERVATION_TOLERANCE_SECONDS
        tolerance = OBSERVATION_TOLERANCE_SECONDS
        events = eligible_events(self.conn, now+tolerance, lookback=EVENT_LOOKBACK_SECONDS+tolerance)
        self.boundaries = sorted(((float(e['source_ts'])+offset, point, dict(e))
            for e in events if str(e['event_type']).upper() not in EXCLUDED_EVENT_TYPES
            for point, offset in POINTS.items()
            if now-tolerance-FLUSH_SECONDS <= float(e['source_ts'])+offset <= now+tolerance+FLUSH_SECONDS), key=lambda r:(r[0],r[1],r[2]['event_id']))
        # Dicts are not comparison keys: simultaneous releases are independent.
        self.clocks = [r[0] for r in self.boundaries]
        self.next_refresh = now + FLUSH_SECONDS
        self.registry_error = ''

    def observe(self, row, now):
        stamp, price = row.get('trade_ts'), row.get('trade_price')
        market = row.get('market')
        if (row.get('exchange') != self.exchange or market not in self.markets
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in (stamp, price, now))
                or not now-120 <= stamp <= now or price <= 0 or not row.get('sequential_id')):
            return False
        point = dict(trade_ts=stamp, trade_price=price, sequential_id=str(row['sequential_id']))
        key = (market, int(stamp//60)*60)
        first, last = self.pending.get(key, (point, point))
        rank = lambda p:(p['trade_ts'], p['sequential_id'])
        self.pending[key] = (min(first, point, key=rank), max(last, point, key=rank))
        self.latest[market] = max(stamp, self.latest.get(market, 0))
        self.messages += 1
        # Receiving a price must not depend on the event registry being readable.
        # Retain minute evidence and use known boundaries during a transient DB
        # failure; newly discovered events can still use the stored endpoints.
        try:
            self.refresh(now)
        except sqlite3.Error as exc:
            self.registry_error = type(exc).__name__
            self.next_refresh = now + FLUSH_SECONDS
        for target, label, event in self.boundaries[bisect_left(self.clocks, stamp-120):bisect_right(self.clocks, stamp+120)]:
            baseline = label == 'baseline'
            if (baseline and stamp > target) or (not baseline and stamp < target):
                continue
            identity = (event['event_id'], event['source_ts'], event['source_id'], event['event_type'], market, label)
            previous = self.exact.get(identity)
            choose = max if baseline else min
            best = choose(previous[1], point, key=rank) if previous else point
            self.exact[identity] = (event, best, target)
        # A persistent DB failure cannot turn RAM into unbounded raw history.
        if now >= self.next_trim:
            self.pending = {k:v for k,v in self.pending.items() if k[1] >= now-RETENTION_SECONDS-60}
            self.exact = {k:v for k,v in self.exact.items() if v[2] >= now-RETENTION_SECONDS}
            self.next_trim = now+60
        return True

    def flush(self, now, *, force=False):
        if not force and now < self.next_flush:
            return
        from .event_price_archive import save_price
        ready = {k:v for k,v in self.exact.items() if v[2] <= now}
        archived = 0
        with self.conn:
            for (market, bucket), (first, last) in self.pending.items():
                self.conn.execute(f'''INSERT INTO {TABLE} VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(exchange,market,bucket_ts) DO UPDATE SET
                    first_ts=MIN(first_ts,excluded.first_ts),
                    first_price=CASE WHEN excluded.first_ts<first_ts THEN excluded.first_price ELSE first_price END,
                    first_seq=CASE WHEN excluded.first_ts<first_ts THEN excluded.first_seq ELSE first_seq END,
                    last_ts=MAX(last_ts,excluded.last_ts),
                    last_price=CASE WHEN excluded.last_ts>=last_ts THEN excluded.last_price ELSE last_price END,
                    last_seq=CASE WHEN excluded.last_ts>=last_ts THEN excluded.last_seq ELSE last_seq END,
                    received_at=MAX(received_at,excluded.received_at)''',
                    (self.exchange,market,bucket,first['trade_ts'],first['trade_price'],first['sequential_id'],
                     last['trade_ts'],last['trade_price'],last['sequential_id'],now))
            for key, (event, tick, _) in ready.items():
                archived += save_price(self.conn, event, self.exchange, key[4], key[5], tick, now)
            # Indexed batches; reusable SQLite pages, no VACUUM or file rewrite.
            expired = self.conn.execute(f'''DELETE FROM {TABLE} WHERE rowid IN (
                SELECT rowid FROM {TABLE} WHERE bucket_ts<? ORDER BY bucket_ts LIMIT 10000)''',
                (int((now-RETENTION_SECONDS)//60)*60,)).rowcount
        self.writes += len(self.pending)
        self.archived += archived
        self.expired += max(0, expired)
        self.pending.clear()
        for key in ready:
            self.exact.pop(key, None)
        self.last_flush, self.next_flush = now, now+FLUSH_SECONDS

    def evidence(self, now):
        return dict(subscribed_markets=len(self.markets), observed_markets=len(self.latest),
                    recent_markets=sum(now-120 <= ts <= now for ts in self.latest.values()),
                    last_trade_ts=max(self.latest.values(), default=None), last_flush_at=self.last_flush,
                    messages=self.messages, sample_writes=self.writes, exact_prices_archived=self.archived,
                    expired_samples=self.expired, retention_seconds=RETENTION_SECONDS,
                    registry_error=self.registry_error, raw_volume_history=False)
