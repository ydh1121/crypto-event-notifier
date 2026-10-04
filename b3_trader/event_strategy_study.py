"""Read-only, retrospective event/coin/strategy evidence. No trading decisions."""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
import sqlite3

from .event_reaction_catalog import presentation
from .event_response_contract import (HORIZONS, OFFICIAL_EVENT_SOURCES, EXCLUDED_EVENT_TYPES,
                                      PROVIDER_ID, observation, summarize_returns)
from .strategy_lab_journal import position_cycles

LOOKBACK_SECONDS = 365 * 86400
MAX_EVENTS = 4000
WITNESS_LIMIT = 20


def _responses(conn, events, exchange, market, now):
    """Exact primary-key prefixes; retain only validated coin/benchmark observations."""
    indexed, anchors, conflicts = {}, defaultdict(set), set()
    symbols = tuple(dict.fromkeys((market, 'KRW-BTC', 'KRW-ETH')))
    keys = list(events)
    for start in range(0, len(keys), 200):
        batch = keys[start:start+200]
        rows = conn.execute(f'''SELECT * FROM research_intelligence_event_responses
            WHERE event_id IN ({','.join('?' for _ in batch)}) AND exchange=?
              AND market IN ({','.join('?' for _ in symbols)}) AND provider_id=? AND captured_at<=?''',
            (*batch, exchange, *symbols, PROVIDER_ID, now))
        for row in rows:
            event = events[row['event_id']]
            key = (row['event_id'], row['market'])
            if (row['event_ts'], row['source_id'], row['event_type']) != (
                    event['event_ts'], event['source_id'], event['event_type']):
                conflicts.add(key)
                continue
            sample = observation(row)
            if sample:
                indexed[(*key, row['horizon_label'])] = sample['return_pct']
                anchors[key].add((sample['baseline_trade_ts'], sample['baseline_price']))
    conflicts.update(key for key, values in anchors.items() if len(values) != 1)
    return {key: value for key, value in indexed.items() if key[:2] not in conflicts}


def _strategy_rows(accounts, trades, events, selected_ids, seconds, now, valid_ids):
    by_time = defaultdict(list)
    for event in events.values():
        by_time[event['event_ts']].append(event)
    clocks = sorted(by_time)
    output, evidence = [], {}
    for account in accounts:
        exp = account['experiment_id']
        row = {k: account.get(k) for k in ('experiment_id', 'style', 'label')}
        row.update(account_revision=account.get('revision'),
                   ledger_trade_count=account.get('reconciliation', {}).get('trade_count'))
        cycles = position_cycles(trades.get(exp, []), now=now) if account.get('reconciliation', {}).get('matches') else None
        if cycles is None:
            output.append({**row, 'status': 'unreconciled', 'closed': None, 'open': None,
                           'wins': None, 'realized_pnl_krw': None, 'return_pct': None})
            continue
        linked, ambiguous = [], 0
        for cycle in cycles:
            index = bisect_right(clocks, cycle['entry_ts']) - 1
            if index < 0 or cycle['entry_ts'] - clocks[index] > seconds:
                continue
            candidates = by_time[clocks[index]]
            if len(candidates) != 1:
                ambiguous += int(any(e['event_id'] in selected_ids for e in candidates))
                continue
            event = candidates[0]
            if event['event_id'] not in selected_ids:
                continue
            linked.append({**cycle, 'event_id': event['event_id'], 'event_ts': event['event_ts'],
                           'event_label': event['short_label'], 'reaction_recorded': event['event_id'] in valid_ids})
        closed = [c for c in linked if c['exit_ts'] is not None]
        spent = sum(c['invested_krw'] for c in closed)
        pnl = sum(c['realized_pnl_krw'] for c in closed)
        output.append({**row, 'status': 'ok', 'closed': len(closed), 'open': len(linked)-len(closed),
                       'wins': sum(c['realized_pnl_krw'] > 0 for c in closed),
                       'realized_pnl_krw': pnl if closed else None,
                       'invested_krw': spent if closed else None,
                       'return_pct': pnl/spent*100 if spent else None,
                       'reaction_matched_closed': sum(c['reaction_recorded'] for c in closed),
                       'ambiguous_excluded': ambiguous, 'linked_events': len({c['event_id'] for c in linked})})
        evidence[exp] = sorted(linked, key=lambda c: (c['entry_ts'], c['entry_trade_id']), reverse=True)
    return output, evidence


def read_event_study(conn: sqlite3.Connection, exchange: str, market: str,
                     accounts: list[dict], trades: dict[str, list[dict]], request: dict, *, now: float) -> dict:
    """One database read transaction owned by read_strategy_lab_market.

    Entries attach once to the nearest preceding official event, across all types.
    Same-time releases are ambiguous and excluded. Outcomes are full closed PAPER
    positions, including costs; they are not event-window asset returns or evidence
    that an event caused a trade. Neither this query nor its output affects PAPER.
    """
    horizon = request.get('horizon', '15m')
    category = request.get('category', 'all')
    if horizon not in dict(HORIZONS) or category not in {'all', 'economic', 'news'}:
        raise ValueError('Invalid event study scope')
    base = {'version': 1, 'exchange': exchange, 'market': market, 'observed_at': now,
            'horizon': horizon, 'category': category, 'lookback_days': 365,
            'window_start': now-LOOKBACK_SECONDS, 'groups': [], 'strategies': [], 'witnesses': [],
            'link_basis': 'nearest_preceding_event_at_first_entry', 'causality_tested': False}
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'research_intelligence_events', 'research_intelligence_event_responses'}.issubset(tables):
        return {**base, 'status': 'unavailable'}
    excluded = tuple(sorted(EXCLUDED_EVENT_TYPES))
    raw = conn.execute(f'''SELECT event_id,source_id,event_type,source_ts AS event_ts,title
        FROM research_intelligence_events WHERE source_id IN ({','.join('?' for _ in OFFICIAL_EVENT_SOURCES)})
          AND source_ts>=? AND source_ts<=? AND source_ts>0
          AND (received_at IS NULL OR received_at<=?)
          AND event_type NOT IN ({','.join('?' for _ in excluded)})
        ORDER BY source_ts DESC,event_id LIMIT ?''',
        (*OFFICIAL_EVENT_SOURCES, now-LOOKBACK_SECONDS, now, now, *excluded, MAX_EVENTS+1)).fetchall()
    truncated = len(raw) > MAX_EVENTS
    included = raw[:MAX_EVENTS]
    # Never turn a cut-through simultaneous release into a unique attribution.
    if truncated and included[-1]['event_ts'] == raw[MAX_EVENTS]['event_ts']:
        cutoff = included[-1]['event_ts']
        included = [r for r in included if r['event_ts'] > cutoff]
    events = {r['event_id']: {**dict(r), **presentation(dict(r))} for r in included}
    values = _responses(conn, events, exchange, market, now)
    seconds = dict(HORIZONS)[horizon]
    groups = defaultdict(list)
    for event in events.values():
        if category == 'all' or event['category'] == category:
            groups[(event['source_id'], event['event_type'])].append(event)
    valid_ids = {key[0] for key in values if key[1:] == (market, horizon)}
    for (source, kind), items in groups.items():
        due = [e for e in items if e['event_ts']+seconds <= now]
        coin = [values[e['event_id'], market, horizon] for e in due if e['event_id'] in valid_ids]
        paired = {}
        for label, symbol in [('btc', 'KRW-BTC'), ('eth', 'KRW-ETH')]:
            relative = [values[e['event_id'], market, horizon]-values[e['event_id'], symbol, horizon]
                        for e in due if e['event_id'] in valid_ids and (e['event_id'], symbol, horizon) in values]
            paired[label] = summarize_returns(relative)
        base['groups'].append({'source_id': source, 'event_type': kind,
            'label': items[0]['short_label'], 'category': items[0]['category'],
            'events': len(items), 'due_events': len(due), 'waiting_events': len(items)-len(due),
            'missing_events': len(due)-len(coin), 'latest_event_ts': items[0]['event_ts'],
            **summarize_returns(coin), 'vs_btc': paired['btc'], 'vs_eth': paired['eth']})
    selected = next((g for g in base['groups'] if (g['source_id'], g['event_type']) ==
                     (request.get('source_id'), request.get('event_type'))), None)
    if selected is None and base['groups']:
        selected = max(base['groups'], key=lambda g: (g['samples'], g['latest_event_ts']))
    if selected:
        ids = {e['event_id'] for e in groups[selected['source_id'], selected['event_type']]}
        rows, witnesses = _strategy_rows(accounts, trades, events, ids, seconds, now, valid_ids)
        selected_exp = next((a['experiment_id'] for a in rows if a['experiment_id'] == request.get('experiment')), None)
        if selected_exp is None:
            selected_exp = next((a['experiment_id'] for a in rows if a['style'] == request.get('style', 'aggressive')), rows[0]['experiment_id'] if rows else None)
        proof = witnesses.get(selected_exp, [])
        base.update(selected={'source_id': selected['source_id'], 'event_type': selected['event_type']},
                    strategies=rows, selected_experiment=selected_exp,
                    witnesses=proof[:WITNESS_LIMIT], witnesses_total=len(proof), witnesses_limit=WITNESS_LIMIT)
    return {**base, 'status': 'ok', 'truncated': truncated, 'event_limit': MAX_EVENTS,
            'earliest_event_ts': min((e['event_ts'] for e in events.values()), default=None)}
