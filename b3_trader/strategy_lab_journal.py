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
