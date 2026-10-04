"""Read-side ledger reconciliation. Cash amounts already include execution fees."""
from __future__ import annotations

import math
from typing import Any

TRADE_COLUMNS = (
    "id", "ts", "source_memory_id", "side", "price", "volume", "krw",
    "realized_pnl", "return_pct", "reason", "buy_index",
)


def reconcile_account(account: dict[str, Any], trades: list[dict[str, Any]], initial_krw: float) -> dict[str, Any]:
    cash, volume, cost = initial_krw, 0.0, 0.0
    realized = gross_profit = gross_loss = sum_return = 0.0
    closed = wins = buys = 0
    issues: list[str] = []
    for t in trades:
        qty, krw = float(t["volume"]), float(t["krw"])
        if not all(math.isfinite(float(t[k])) for k in ("volume", "krw", "price", "realized_pnl", "return_pct")) or qty <= 0 or krw < 0:
            issues.append(f"invalid_trade:{t['id']}")
            continue
        if t["side"] == "buy":
            cash -= krw
            cost += krw
            volume += qty
            buys += 1
        elif t["side"] == "sell":
            if volume <= 0 or not math.isclose(qty, volume, rel_tol=1e-9, abs_tol=1e-8):
                issues.append(f"incomplete_position:{t['id']}")
            basis = cost * qty / volume if volume > 0 else 0.0
            pnl = krw - basis
            ret = pnl / basis * 100 if basis > 0 else 0.0
            if not math.isclose(pnl, float(t["realized_pnl"]), rel_tol=1e-9, abs_tol=0.01):
                issues.append(f"trade_pnl:{t['id']}")
            if not math.isclose(ret, float(t["return_pct"]), rel_tol=1e-9, abs_tol=1e-7):
                issues.append(f"trade_return:{t['id']}")
            cash += krw
            volume -= qty
            cost -= basis
            if abs(volume) < 1e-8:
                volume = cost = 0.0
            realized += pnl
            sum_return += ret
            closed += 1
            wins += int(pnl > 0)
            gross_profit += max(0.0, pnl)
            gross_loss += min(0.0, pnl)
            buys = 0
        else:
            issues.append(f"unknown_side:{t['id']}")
    values = dict(cash_krw=cash, volume=volume, avg_price=cost / volume if volume > 0 else 0.0,
                  realized_pnl=realized, closed_trades=closed, wins=wins, buy_count=buys,
                  gross_profit=gross_profit, gross_loss=gross_loss, sum_return_pct=sum_return)
    differences = {}
    for key, value in values.items():
        actual = account.get(key)
        tolerance = 0.01 if key in {"cash_krw", "realized_pnl", "gross_profit", "gross_loss"} else 1e-8
        if actual is None or not math.isclose(value, float(actual), rel_tol=1e-9, abs_tol=tolerance):
            differences[key] = {"account": actual, "ledger": value}
    return {"matches": not differences and not issues, "trade_count": len(trades),
            "closed_trades": closed, "wins": wins, "values": values,
            "differences": differences, "issues": issues,
            # Fill-only replay cannot reproduce intratrade marking drawdown.
            "drawdown_reproduced": False}


def position_cycles(trades: list[dict], *, now: float) -> list[dict] | None:
    """Group an already reconciled full-position ledger; reject invalid clocks.

    The caller must require reconcile_account.matches. This adds no new fill or
    profit formula: closed results come from the reconciled sell row.
    """
    cycles, pending = [], []
    previous = 0.0
    for trade in trades:
        ts = trade.get('ts')
        if (not isinstance(ts, (int, float)) or not math.isfinite(ts)
                or ts <= 0 or ts < previous or ts > now or trade['price'] <= 0):
            return None
        previous = ts
        if trade['side'] == 'buy':
            if trade['krw'] <= 0:
                return None
            pending.append(trade)
        elif trade['side'] == 'sell':
            if not pending:
                return None
            cycles.append(_position_cycle(pending, trade))
            pending = []
        else:
            return None
    if pending:
        cycles.append(_position_cycle(pending, None))
    return cycles


def _position_cycle(buys: list[dict], sell: dict | None) -> dict:
    first = buys[0]
    return {'entry_trade_id': first['id'], 'entry_ts': first['ts'], 'entry_price': first['price'],
            'buy_count': len(buys), 'invested_krw': sum(t['krw'] for t in buys),
            'exit_trade_id': sell['id'] if sell else None, 'exit_ts': sell['ts'] if sell else None,
            'exit_price': sell['price'] if sell else None, 'proceeds_krw': sell['krw'] if sell else None,
            'realized_pnl_krw': sell['realized_pnl'] if sell else None,
            'return_pct': sell['return_pct'] if sell else None}
