"""Read-side totals shared by manual and PAPER position comparisons."""


def cycle_metrics(cycles):
    closed = [c for c in cycles if c['exit_ts'] is not None]
    opened = [c for c in cycles if c['exit_ts'] is None]
    cost = sum(c['invested_krw'] for c in closed)
    pnl = sum(c['realized_pnl_krw'] for c in closed)
    fees = [c.get('fees_krw') for c in closed]
    return {
        'closed': len(closed), 'open': len(opened),
        'wins': sum(c['realized_pnl_krw'] > 0 for c in closed) if closed else None,
        'invested_krw': cost if closed else None,
        'proceeds_krw': sum(c['proceeds_krw'] for c in closed) if closed else None,
        'realized_pnl_krw': pnl if closed else None,
        'return_pct': pnl / cost * 100 if cost > 0 else None,
        'mean_return_pct': sum(c['return_pct'] for c in closed) / len(closed) if closed else None,
        'worst_return_pct': min((c['return_pct'] for c in closed), default=None),
        'open_invested_krw': sum(c['invested_krw'] for c in opened),
        # PAPER net cash includes costs but does not identify separate paid fees.
        'fees_krw': sum(fees) if closed and all(v is not None for v in fees) else None,
    }
