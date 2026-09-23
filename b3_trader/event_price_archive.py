"""Preserve exact event prices before bounded raw trade retention removes them.

At most five observations per known event/clock/exchange/market. No network,
synthetic candles, reaction calculation, or change to the raw retention limit.
Writes belong to the caller's transaction; failed preservation must not prune.
"""
from __future__ import annotations

import math
import sqlite3

from .event_response_contract import (
    EVENT_LOOKBACK_SECONDS, EXCLUDED_EVENT_TYPES, HORIZONS, MAX_EVENTS,
    OFFICIAL_EVENT_SOURCES, PROVIDER_ID,
)

POINTS = {'baseline': 0, **dict(HORIZONS)}
# Retain the nearest real tick across every tolerance allowed by the collector.
# The reader still applies the collector's own (normally 120-second) tolerance.
MAX_TOLERANCE = 600.0
TABLE = 'research_intelligence_event_prices'


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(f'''CREATE TABLE IF NOT EXISTS {TABLE} (
        event_id TEXT NOT NULL, event_ts REAL NOT NULL,
        source_id TEXT NOT NULL, event_type TEXT NOT NULL,
        exchange TEXT NOT NULL, market TEXT NOT NULL, point TEXT NOT NULL,
        provider_id TEXT NOT NULL, sequential_id TEXT NOT NULL,
        trade_ts REAL NOT NULL, trade_price REAL NOT NULL,
        archived_at REAL NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY(event_id,event_ts,source_id,event_type,exchange,market,point,provider_id)
    )''')


def eligible_events(conn, now, *, lookback=EVENT_LOOKBACK_SECONDS, limit=MAX_EVENTS):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_intelligence_events'").fetchone():
        return []
    placeholders = ','.join('?' for _ in OFFICIAL_EVENT_SOURCES)
    return conn.execute(f'''SELECT event_id,event_type,source_id,title,source_ts
        FROM research_intelligence_events WHERE source_id IN ({placeholders})
        AND source_ts>=? AND source_ts<=? ORDER BY source_ts DESC,event_id LIMIT ?''',
        (*OFFICIAL_EVENT_SOURCES, now - lookback, now, limit)).fetchall()


def capture_market(conn, exchange, market, now, *, events=None) -> int:
    if events is None:
        events = eligible_events(conn, now)
    changed = 0
    for event in events:
        stamp = float(event['source_ts'])
        if (not math.isfinite(stamp) or not 0 < stamp <= now
                or str(event['event_type']).strip().upper() in EXCLUDED_EVENT_TYPES):
            continue
        for point, seconds in POINTS.items():
            target = stamp + seconds
            if target > now:
                continue
            baseline = point == 'baseline'
            order = 'DESC' if baseline else 'ASC'
            start = target - MAX_TOLERANCE if baseline else target
            end = target if baseline else min(target + MAX_TOLERANCE, now)
            row = conn.execute(f'''SELECT sequential_id,trade_ts,trade_price
                FROM research_market_trade_flow_mx WHERE exchange=? AND market=?
                AND trade_ts>=? AND trade_ts<=? AND trade_price>0
                ORDER BY trade_ts {order},sequential_id {order} LIMIT 1''',
                (exchange, market, start, end)).fetchone()
            if row is None or not math.isfinite(row['trade_price']):
                continue
            better = '>' if baseline else '<'
            cursor = conn.execute(f'''INSERT INTO {TABLE} (
                event_id,event_ts,source_id,event_type,exchange,market,point,provider_id,
                sequential_id,trade_ts,trade_price,archived_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(event_id,event_ts,source_id,event_type,exchange,market,point,provider_id)
                DO UPDATE SET sequential_id=excluded.sequential_id,trade_ts=excluded.trade_ts,
                    trade_price=excluded.trade_price,archived_at=excluded.archived_at
                WHERE excluded.trade_ts {better} {TABLE}.trade_ts
                   OR (excluded.trade_ts={TABLE}.trade_ts
                       AND excluded.sequential_id {better} {TABLE}.sequential_id)''',
                (event['event_id'],stamp,event['source_id'],event['event_type'],exchange,market,
                 point,PROVIDER_ID,row['sequential_id'],row['trade_ts'],row['trade_price'],now))
            changed += max(0, cursor.rowcount)
    return changed


def read_price(conn, event, exchange, market, point, now, tolerance):
    row = conn.execute(f'''SELECT sequential_id,trade_ts,trade_price,archived_at FROM {TABLE}
        WHERE event_id=? AND event_ts=? AND source_id=? AND event_type=?
          AND exchange=? AND market=? AND point=? AND provider_id=?''',
        (event['event_id'],event['source_ts'],event['source_id'],event['event_type'],
         exchange,market,point,PROVIDER_ID)).fetchone()
    if row is None:
        return None
    values = (row['trade_ts'], row['trade_price'], row['archived_at'])
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        return None
    target = float(event['source_ts']) + POINTS[point]
    lag = target - row['trade_ts'] if point == 'baseline' else row['trade_ts'] - target
    if (row['trade_price'] <= 0 or not 0 <= lag <= tolerance
            or not row['trade_ts'] <= row['archived_at'] <= now or target > now):
        return None
    return {**dict(row), 'from_event_archive': True}
