"""Read existing event responses with exact exchange/provider/time identity."""
from __future__ import annotations

import sqlite3
import time
from statistics import mean, median
from typing import Any

from .event_response_contract import HORIZONS, MAX_EVENTS, OBSERVATION_TOLERANCE_SECONDS, PROVIDER_ID, observation
from .event_price_archive import TABLE as PRICE_TABLE, read_price

HISTORY_SECONDS = 365 * 86400


def review_event_index(events: list[dict]) -> dict:
    """Bounded report of the same saved observations exposed in the coin view.

    Keep a recent event and the strongest complete comparison as exact price
    evidence. The compact index covers every displayed event, not just the first.
    It is not a count of all collected news or a probability of an event's effect.
    """
    items = events[:20]
    index = []
    for e in items:
        complete = []
        horizons = {}
        for h, _ in HORIZONS:
            r = e.get('responses', {}).get(h, {})
            values = {k: r.get(k) for k in ('coin', 'btc', 'eth', 'vs_btc_pp', 'vs_eth_pp')}
            usable = not e.get('anchor_conflict') and not e.get('anchor_changed')
            if usable and all(values[k] is not None for k in ('coin', 'btc', 'eth')):
                complete.append(h)
            horizons[h] = {**values, 'status': {
                name: e.get('price_progress', {}).get(name, {}).get(h, {}).get('status', 'unavailable')
                for name in ('coin', 'btc', 'eth')}}
        index.append({**{k: e.get(k) for k in ('event_id', 'event_ts', 'source_id', 'event_type', 'title')},
                      'complete_comparisons': complete, 'horizons': horizons})
    witnesses = []
    if items:
        best = max(range(len(items)), key=lambda n: (len(index[n]['complete_comparisons']),
                   sum(index[n]['horizons'][h]['coin'] is not None for h, _ in HORIZONS)))
        witnesses = [items[n] for n in dict.fromkeys((0, best))]
    return {'selection': 'latest_20_events_with_local_price_evidence',
            'displayed_event_count': len(index), 'index': index, 'events': witnesses}


def _history(conn: sqlite3.Connection, event: dict, exchange: str, market: str) -> dict:
    """Only earlier same-source/type results already known at this event's time."""
    groups: dict[str, list[float]] = {h: [] for h, _ in HORIZONS}
    rows = conn.execute('''SELECT * FROM research_intelligence_event_responses
        WHERE exchange=? AND market=? AND provider_id=? AND source_id=? AND event_type=?
          AND event_id<>? AND event_ts>=? AND event_ts<? AND captured_at<=?
        ORDER BY event_ts,event_id,horizon_seconds''',
        (exchange, market, PROVIDER_ID, event['source_id'], event['event_type'], event['event_id'],
         event['event_ts'] - HISTORY_SECONDS, event['event_ts'], event['event_ts']))
    for row in rows:
        sample = observation(row)
        if sample:
            groups[row['horizon_label']].append(sample['return_pct'])
    return {h: {'samples': len(values), 'mean_pct': mean(values) if values else None,
                'median_pct': median(values) if values else None,
                'positive_samples': sum(v > 0 for v in values) if values else None}
            for h, values in groups.items()}


def _event_list(conn, exchange, market, limit, now, has_archive):
    # Completed coin/benchmark observations retain their original clock. Pending
    # archive lookups start with at most MAX_EVENTS metadata keys, using the
    # archive's event_id primary-key prefix instead of scanning its full history.
    rows = list(conn.execute('''SELECT event_id,event_ts,source_id,event_type,MAX(captured_at) AS captured_at
        FROM research_intelligence_event_responses
        WHERE exchange=? AND market IN (?,?,?) AND provider_id=? AND captured_at<=? AND event_ts<=?
        GROUP BY event_id,event_ts,source_id,event_type ORDER BY event_ts DESC,event_id LIMIT ?''',
        (exchange, market, 'KRW-BTC', 'KRW-ETH', PROVIDER_ID, now, now, limit)))
    if has_archive:
        rows.extend(conn.execute(f'''SELECT event_id,event_ts,source_id,event_type,NULL AS captured_at
            FROM {PRICE_TABLE} WHERE event_id IN (
                SELECT event_id FROM research_intelligence_events
                ORDER BY source_ts DESC,event_id LIMIT ?)
            AND exchange=? AND market IN (?,?,?) AND provider_id=? AND archived_at<=? AND event_ts<=?
            GROUP BY event_id,event_ts,source_id,event_type
            ORDER BY event_ts DESC,event_id LIMIT ?''',
            (MAX_EVENTS, exchange, market, 'KRW-BTC', 'KRW-ETH', PROVIDER_ID, now, now, limit)))
    unique = {}
    for row in rows:
        key = tuple(row[k] for k in ('event_id', 'event_ts', 'source_id', 'event_type'))
        unique.setdefault(key, dict(row))
    return sorted(unique.values(), key=lambda e: (-e['event_ts'], e['event_id'], e['source_id'], e['event_type']))[:limit]


def _point(price, stamp, origin):
    return {'price': price, 'trade_ts': stamp, 'origin': origin}


def _price_progress(conn, event, exchange, market, indexed, now, has_archive, identity_conflicts):
    """Expose stored evidence without calculating or inserting a reaction."""
    saved = [observation(r) for (symbol, _), r in indexed.items() if symbol == market]
    anchors = {(s['baseline_price'], s['baseline_trade_ts']) for s in saved if s}
    conflict = market in identity_conflicts or any(s is None for s in saved) or len(anchors) > 1
    baseline = _point(*next(iter(anchors)), 'response') if len(anchors) == 1 and not conflict else None
    archive = {}
    if has_archive:
        anchor = {**event, 'source_ts': event['event_ts']}
        for point in ('baseline', *(h for h, _ in HORIZONS)):
            tick = read_price(conn, anchor, exchange, market, point, now, OBSERVATION_TOLERANCE_SECONDS)
            archive[point] = _point(tick['trade_price'], tick['trade_ts'], 'archive') if tick else None
        if not conflict:
            baseline = baseline or archive['baseline']
    result = {}
    for h, seconds in HORIZONS:
        row = indexed.get((market, h))
        sample = observation(row)
        target = archive.get(h)
        first = baseline
        if sample:
            # Exact completed prices already live in responses.observations.
            # Do not duplicate all twelve observations in every published event.
            result[h] = {'status': 'recorded'}
            continue
        elif row is not None or conflict:
            status = 'invalid_response'
        elif first is None:
            status = 'missing_baseline'
        elif event['event_ts'] + seconds > now:
            status = 'before_horizon'
        else:
            status = 'awaiting_capture' if target else 'missing_target'
        result[h] = {'status': status, 'baseline': first, 'target': target,
                     'target_ts': event['event_ts'] + seconds}
    return result


def read_event_context(conn: sqlite3.Connection, exchange: str, market: str, *, limit: int = 20,
                       now: float | None = None) -> list[dict]:
    current = time.time() if now is None else now
    has_archive = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (PRICE_TABLE,)).fetchone())
    events = _event_list(conn, exchange, market, max(1, min(20, limit)), current, has_archive)
    output = []
    for event in events:
        item = dict(event)
        meta = conn.execute('''SELECT title,source_url,source_ts,published_at,scheduled_at,received_at
            FROM research_intelligence_events WHERE event_id=?''', (item['event_id'],)).fetchone()
        item.update(dict(meta) if meta else {'title': item['event_type'], 'source_url': ''})
        item['anchor_changed'] = meta is not None and meta['source_ts'] != item['event_ts']
        item['exchange'], item['market'], item['observed_at'] = exchange, market, current
        responses = {}
        all_rows = conn.execute('''SELECT * FROM research_intelligence_event_responses
            WHERE event_id=? AND exchange=?
              AND market IN (?,?,?) AND provider_id=? AND captured_at<=?''',
            (item['event_id'], exchange, market, 'KRW-BTC', 'KRW-ETH', PROVIDER_ID, current)).fetchall()
        identity = lambda r: (r['event_ts'], r['source_id'], r['event_type'])
        rows = [r for r in all_rows if identity(r) == identity(item)]
        identity_conflicts = {r['market'] for r in all_rows if identity(r) != identity(item)}
        item['anchor_conflict'] = bool(identity_conflicts)
        indexed = {(r['market'], r['horizon_label']): r for r in rows}
        item['invalid_observations'] = sum(observation(row) is None for row in rows)
        item['price_progress'] = {name: _price_progress(conn, item, exchange, symbol, indexed, current, has_archive, identity_conflicts)
                                 for name, symbol in (('coin', market), ('btc', 'KRW-BTC'), ('eth', 'KRW-ETH'))}
        for h, _ in HORIZONS:
            samples = {name: observation(indexed.get((symbol, h))) for name, symbol in
                       (('coin', market), ('btc', 'KRW-BTC'), ('eth', 'KRW-ETH'))}
            values = {name: sample['return_pct'] if sample else None for name, sample in samples.items()}
            responses[h] = {**values, 'observations': samples,
                'vs_btc_pp': values['coin'] - values['btc'] if values['coin'] is not None and values['btc'] is not None else None,
                'vs_eth_pp': values['coin'] - values['eth'] if values['coin'] is not None and values['eth'] is not None else None}
        item['responses'] = responses
        item['history'] = _history(conn, item, exchange, market)
        item['history_lookback_days'] = 365
        output.append(item)
    return output
