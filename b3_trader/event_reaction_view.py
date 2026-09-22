"""Read existing event responses with exact exchange/provider/time identity."""
from __future__ import annotations

import sqlite3
from statistics import mean, median
from typing import Any

from .event_response_contract import HORIZONS, PROVIDER_ID, observation

HISTORY_SECONDS = 365 * 86400


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


def read_event_context(conn: sqlite3.Connection, exchange: str, market: str, *, limit: int = 20) -> list[dict]:
    # Group by the captured event clock, not the calendar's potentially revised clock.
    events = conn.execute('''SELECT event_id,event_ts,source_id,event_type,MAX(captured_at) AS captured_at
        FROM research_intelligence_event_responses
        WHERE exchange=? AND market=? AND provider_id=?
        GROUP BY event_id,event_ts,source_id,event_type ORDER BY event_ts DESC,event_id LIMIT ?''',
        (exchange, market, PROVIDER_ID, max(1, min(20, limit)))).fetchall()
    output = []
    for event in events:
        item = dict(event)
        meta = conn.execute('''SELECT title,source_url,source_ts,published_at,scheduled_at,received_at
            FROM research_intelligence_events WHERE event_id=?''', (item['event_id'],)).fetchone()
        item.update(dict(meta) if meta else {'title': item['event_type'], 'source_url': ''})
        item['anchor_changed'] = meta is not None and meta['source_ts'] != item['event_ts']
        item['exchange'], item['market'] = exchange, market
        responses = {}
        rows = conn.execute('''SELECT * FROM research_intelligence_event_responses
            WHERE event_id=? AND event_ts=? AND source_id=? AND event_type=? AND exchange=?
              AND market IN (?,?,?) AND provider_id=?''',
            (item['event_id'], item['event_ts'], item['source_id'], item['event_type'],
             exchange, market, 'KRW-BTC', 'KRW-ETH', PROVIDER_ID)).fetchall()
        indexed = {(r['market'], r['horizon_label']): r for r in rows}
        item['invalid_observations'] = sum(observation(row) is None for row in rows)
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
