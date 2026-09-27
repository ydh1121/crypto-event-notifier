"""Bounded, read-only evidence for one coin's event-price capture path.

No collector imports, network, schema creation, price interpolation or reactions
are performed here. Raw retention bounds do not prove uninterrupted coverage.
"""
from __future__ import annotations

import math
from pathlib import Path
import sqlite3
import time

from .event_price_archive import POINTS, eligible_events, read_price
from .event_response_contract import (
    EVENT_LOOKBACK_SECONDS, EXCLUDED_EVENT_TYPES, HORIZONS, MAX_EVENTS,
    OBSERVATION_TOLERANCE_SECONDS, OFFICIAL_EVENT_SOURCES, PROVIDER_ID, observation,
)

EXCHANGE = "bithumb"
MARKETS = ("KRW-B3", "KRW-BTC", "KRW-ETH")
ROW_COUNT_LIMIT = 50_000
QUERY_SECONDS = 0.4
TOTAL_SECONDS = 5.0
TRADE_TABLE = "research_market_trade_flow_mx"


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def _clock(value):
    number = _number(value)
    return number if number is not None and number > 0 else None


class _Reader:
    def __init__(self, conn):
        self.conn = conn
        self.deadline = time.monotonic() + TOTAL_SECONDS

    def read(self, function):
        deadline = min(self.deadline, time.monotonic() + QUERY_SECONDS)
        if time.monotonic() >= deadline:
            return {"status": "query_timeout"}
        self.conn.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        try:
            return {"status": "read", **function()}
        except sqlite3.Error as exc:
            return {"status": "query_timeout" if str(exc) == "interrupted" else "unavailable"}
        finally:
            self.conn.set_progress_handler(None, 0)

    def record(self, table, market, clocks, numbers=(), flags=()):
        def query():
            fields = (*clocks, *numbers, *flags)
            row = self.conn.execute(f'''SELECT {','.join(fields)} FROM {table}
                WHERE exchange=? AND market=?''', (EXCHANGE, market)).fetchone()
            if row is None:
                return {"present": False}
            return {"present": True,
                    **{key: _clock(row[key]) for key in clocks},
                    **{key: _number(row[key]) for key in numbers},
                    **{key: bool(row[key]) if row[key] in (0, 1) else None for key in flags}}
        return self.read(query)


def _raw_coverage(conn, market, now):
    bounds = []
    for order in ("ASC", "DESC"):
        row = conn.execute(f'''SELECT trade_ts,received_at FROM {TRADE_TABLE}
            WHERE exchange=? AND market=? ORDER BY trade_ts {order} LIMIT 1''',
            (EXCHANGE, market)).fetchone()
        bounds.append({key: _clock(row[key]) for key in row.keys()} if row else None)
    count = conn.execute(f'''SELECT COUNT(*) FROM (SELECT 1 FROM {TRADE_TABLE}
        WHERE exchange=? AND market=? LIMIT ?)''', (EXCHANGE, market, ROW_COUNT_LIMIT + 1)).fetchone()[0]
    latest = bounds[1]["trade_ts"] if bounds[1] else None
    return {"row_count": min(count, ROW_COUNT_LIMIT), "row_count_capped": count > ROW_COUNT_LIMIT,
            "first": bounds[0], "last": bounds[1],
            "latest_age_seconds": now - latest if latest is not None else None}


def _events(conn, now):
    # Unlike eligible_events' collector-friendly empty fallback, an absent table
    # in a diagnostic is unknown, not evidence of zero eligible releases.
    conn.execute("SELECT event_id FROM research_intelligence_events LIMIT 0")
    selected = eligible_events(conn, now)
    eligible = [r for r in selected if str(r['event_type']).strip().upper() not in EXCLUDED_EVENT_TYPES
                and _clock(r['source_ts']) is not None]
    placeholders = ','.join('?' for _ in OFFICIAL_EVENT_SOURCES)
    columns = "event_id,source_id,event_type,source_ts,received_at"
    witnesses = [dict(row) for row in conn.execute(f'''SELECT {columns}
        FROM research_intelligence_events WHERE source_id IN ({placeholders})
        AND source_ts>0 AND source_ts<=? ORDER BY source_ts DESC,event_id LIMIT 4''',
        (*OFFICIAL_EVENT_SOURCES, now))]
    future = conn.execute(f'''SELECT {columns} FROM research_intelligence_events
        WHERE source_id IN ({placeholders}) AND source_ts>?
        ORDER BY source_ts,event_id LIMIT 1''', (*OFFICIAL_EVENT_SOURCES, now)).fetchone()
    return {"selected_events": len(selected), "eligible_events": len(eligible),
            "excluded_imprecise_events": len(selected) - len(eligible),
            "selection_limit": MAX_EVENTS, "selection_limit_reached": len(selected) == MAX_EVENTS,
            "latest_source_ts": witnesses[0]['source_ts'] if witnesses else None,
            "next_scheduled": dict(future) if future else None, "recent": witnesses}


def _tick(row):
    return {"trade_ts": row['trade_ts'], "price": row['trade_price']} if row else None


def _raw_point(conn, event, market, point, now):
    target = event['source_ts'] + POINTS[point]
    baseline = point == 'baseline'
    tolerance = OBSERVATION_TOLERANCE_SECONDS
    start, end = ((target - tolerance, target) if baseline else (target, min(now, target + tolerance)))
    order = 'DESC' if baseline else 'ASC'
    row = conn.execute(f'''SELECT trade_ts,trade_price,received_at FROM {TRADE_TABLE}
        WHERE exchange=? AND market=? AND trade_ts>=? AND trade_ts<=? AND trade_price>0
        ORDER BY trade_ts {order},sequential_id {order} LIMIT 1''',
        (EXCHANGE, market, start, end)).fetchone()
    valid = row is not None and _number(row['trade_price']) is not None and _clock(row['trade_ts']) is not None
    return {"price": _tick(row) if valid else None,
            "received_at": _clock(row['received_at']) if valid else None}


def _responses(conn, event, market, now):
    rows = conn.execute('''SELECT * FROM research_intelligence_event_responses
        WHERE event_id=? AND event_ts=? AND source_id=? AND event_type=?
          AND exchange=? AND market=? AND provider_id=? AND captured_at<=?''',
        (event['event_id'], event['source_ts'], event['source_id'], event['event_type'],
         EXCHANGE, market, PROVIDER_ID, now)).fetchall()
    valid = [(row['horizon_label'], observation(row)) for row in rows]
    anchors = {(r['baseline_trade_ts'], r['baseline_price']) for _, r in valid if r}
    return {"recorded": {h: r for h, r in valid if r},
            "invalid_rows": sum(r is None for _, r in valid), "anchor_conflict": len(anchors) > 1}


def _anchor_checks(reader, events, now):
    checks = []
    for event in events:
        stamp = event['source_ts']
        precise = str(event['event_type']).strip().upper() not in EXCLUDED_EVENT_TYPES
        current = now - EVENT_LOOKBACK_SECONDS <= stamp <= now
        item = {**event, "in_collection_window": current, "precise_clock": precise,
                "receipt_delay_seconds": event['received_at'] - stamp if _clock(event['received_at']) else None,
                "markets": {}}
        checks.append(item)
        if not precise:
            continue
        for market in MARKETS:
            record = reader.read(lambda: _responses(reader.conn, event, market, now))
            points = {}
            for point, seconds in POINTS.items():
                if stamp + seconds > now:
                    points[point] = {"status": "not_due", "target_ts": stamp + seconds}
                    continue
                raw = reader.read(lambda: _raw_point(reader.conn, event, market, point, now))
                archive = reader.read(lambda: {"price": _tick(read_price(
                    reader.conn, event, EXCHANGE, market, point, now, OBSERVATION_TOLERANCE_SECONDS))})
                points[point] = {"status": "due", "target_ts": stamp + seconds, "raw": raw, "archive": archive}
            item['markets'][market] = {"responses": record, "points": points}
    return checks


def read_event_capture(db: Path, *, now=None):
    current = time.time() if now is None else now
    result = {"observed_at": current, "exchange": EXCHANGE, "coin": MARKETS[0],
              "lookback_seconds": EVENT_LOOKBACK_SECONDS,
              "tolerance_seconds": OBSERVATION_TOLERANCE_SECONDS,
              "policy_source": "event_response_contract_defaults",
              "coverage_is_continuous": None, "markets": {}}
    try:
        conn = sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.4)
    except sqlite3.Error:
        return {**result, "status": "unavailable"}
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        reader = _Reader(conn)
        for market in MARKETS:
            result['markets'][market] = {
                "raw": reader.read(lambda: _raw_coverage(conn, market, current)),
                "rest_cursor": reader.record("research_market_flow_cursor_mx", market,
                    ("coverage_start_ts", "covered_through_ts", "last_seen_trade_ts", "updated_at"),
                    ("last_pages", "last_rows"), ("last_cycle_complete",)),
                "websocket_session": reader.record("research_market_flow_stream_session_mx", market,
                    ("process_started_at", "connected_since", "last_disconnect_at", "last_trade_ts",
                     "last_received_at", "updated_at"), ("messages_seen", "inserts", "reconnects"), ("connected",)),
            }
        result['events'] = reader.read(lambda: _events(conn, current))
        result['anchor_checks'] = _anchor_checks(reader, result['events'].pop('recent', []), current)
        return {**result, "status": "observed", "finished_at": time.time()}
    finally:
        conn.close()


def compare_event_capture(before, after):
    compared = {}
    for market in MARKETS:
        pair = [r.get('event_capture', {}).get('markets', {}).get(market, {}).get('raw', {})
                for r in (before, after)]
        clocks = [(r.get('last') or {}).get('trade_ts') for r in pair]
        state = 'unknown'
        if all(r.get('status') == 'read' for r in pair) and all(_clock(v) is not None for v in clocks):
            state = 'advanced' if clocks[1] > clocks[0] else 'unchanged' if clocks[1] == clocks[0] else 'latest_regressed'
        compared[f'{EXCHANGE}|{market}'] = {"observation": state, "before": clocks[0], "after": clocks[1]}
    return compared


def stream_subscription_evidence(value):
    """Saved configuration only. Runtime ownership is reported separately."""
    markets = value.get('markets')
    valid = isinstance(markets, list) and all(isinstance(m, str) for m in markets)
    exchanges = value.get('exchanges')
    state = exchanges.get(EXCHANGE, {}) if isinstance(exchanges, dict) else {}
    state = state if isinstance(state, dict) else {}
    return {"scope": "saved_configuration", "market_count": len(markets) if valid else None,
            "membership": {market: market in markets if valid else None for market in MARKETS},
            "exchange": EXCHANGE,
            "connected": state['connected'] if type(state.get('connected')) is bool else None,
            **{key: _clock(state.get(key)) for key in
               ('connected_since', 'last_disconnect_at', 'last_message_at', 'last_trade_ts', 'updated_at')}}
