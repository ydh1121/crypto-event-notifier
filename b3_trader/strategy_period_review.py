"""Coin-scoped, fee-inclusive entry cohorts from reconciled PAPER ledgers.

No ranking, signal changes, annualization or mark-to-market drawdown estimates.
Previous periods are cut at their own end, so later sales/adds cannot leak in.
"""
from __future__ import annotations

from .strategy_lab_journal import position_cycles
from .trade_cycle_metrics import cycle_metrics

PERIODS = {'7d': 7, '30d': 30, '90d': 90, 'all': None}


def _period(trades: list[dict], start: float | None, end: float, *, inclusive: bool) -> tuple[dict, list]:
    visible = [t for t in trades if t['ts'] <= end] if inclusive else [t for t in trades if t['ts'] < end]
    cycles = position_cycles(visible, now=end) or []
    selected = [c for c in cycles if start is None or c['entry_ts'] >= start]
    carried = [c for c in cycles if start is not None and c['entry_ts'] < start
               and (c['exit_ts'] is None or c['exit_ts'] >= start)]
    return {**cycle_metrics(selected), 'carried_positions': len(carried)}, selected


def period_review(exchange: str, market: str, accounts: list[dict], grouped: dict,
                  request: dict, *, now: float) -> dict:
    period = request.get('period', '30d')
    if period not in PERIODS:
        raise ValueError('Invalid period')
    days = PERIODS[period]
    start = now-days*86400 if days is not None else None
    previous_start = start-days*86400 if days is not None else None
    rows, witnesses = [], {}
    for account in accounts:
        key = account['experiment_id']
        trades = grouped.get(key, [])
        row = {k: account.get(k) for k in ('experiment_id', 'style', 'label')}
        row.update(account_revision=account.get('revision'), ledger_trade_count=len(trades),
                   status='unreconciled', current=None, previous=None, first_trade_ts=None)
        rows.append(row)
        if not account.get('reconciliation', {}).get('matches'):
            continue
        if position_cycles(trades, now=now) is None:
            continue
        current, cycles = _period(trades, start, now, inclusive=True)
        previous = _period(trades, previous_start, start, inclusive=False)[0] if start is not None else None
        row.update(status='ok', current=current, previous=previous,
                   first_trade_ts=trades[0]['ts'] if trades else None)
        witnesses[key] = cycles
    selected = next((r for r in rows if r['experiment_id'] == request.get('experiment')), None)
    selected = selected or next((r for r in rows if r['style'] == request.get('style', 'aggressive')), None)
    selected = selected or next(iter(rows), None)
    cycles = witnesses.get(selected['experiment_id'], []) if selected else []
    limit = 20
    page = sorted(cycles, key=lambda c: (c['entry_ts'], c['entry_trade_id']), reverse=True)[:limit]
    return {
        'version': 1, 'status': 'ok' if rows else 'no_account', 'exchange': exchange, 'market': market,
        'period': period, 'observed_at': now, 'start': start, 'end': now,
        'previous_start': previous_start, 'previous_end': start,
        'cohort_basis': 'first_entry_in_period', 'costs_included': True,
        'strategies': rows, 'selected_experiment': selected['experiment_id'] if selected else '',
        'witnesses': page, 'witnesses_total': len(cycles), 'witnesses_limit': limit,
        'predictive_validity': 'not_tested',
    }
