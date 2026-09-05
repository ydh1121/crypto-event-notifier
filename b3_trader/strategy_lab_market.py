from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH, START_KRW


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_strategy_lab_market(exchange: str, market: str, path: Path = DB_PATH) -> dict[str, Any]:
    exchange = str(exchange or "").strip().lower()
    market = str(market or "").strip().upper()
    base = {"paper_only": True, "exchange": exchange, "market": market, "experiments": []}
    if exchange not in {"bithumb", "upbit"} or not market or not path.exists():
        return base
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {str(row["name"]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        required = {"strategy_lab_experiments", "strategy_lab_accounts", "strategy_lab_learning", "strategy_lab_trades"}
        if not required.issubset(tables):
            return base
        custom_table = "strategy_lab_custom_specs" in tables
        custom_join = (
            "LEFT JOIN strategy_lab_custom_specs c ON c.experiment_id=e.experiment_id"
            if custom_table else ""
        )
        custom_cols = (
            ",c.primary_style,c.secondary_style,c.mix_ratio"
            if custom_table else ",NULL AS primary_style,NULL AS secondary_style,NULL AS mix_ratio"
        )
        rows = conn.execute(
            f"""SELECT a.*,e.style,e.label,e.description,e.status{custom_cols},
                       COALESCE(l.entry_bias,0) AS entry_bias,
                       COALESCE(l.weight_multiplier,1) AS weight_multiplier,
                       COALESCE(l.ema_return_pct,0) AS ema_return_pct
                FROM strategy_lab_accounts a
                JOIN strategy_lab_experiments e USING(experiment_id)
                LEFT JOIN strategy_lab_learning l
                  ON l.experiment_id=a.experiment_id AND l.market=a.market
                {custom_join}
                WHERE a.exchange=? AND a.market=?
                ORDER BY e.status='running' DESC,e.created_ts,e.label""",
            (exchange, market),
        ).fetchall()
        trade_rows = conn.execute(
            """SELECT experiment_id,side,ts,price,krw,realized_pnl,return_pct,reason,buy_index
               FROM strategy_lab_trades
               WHERE exchange=? AND market=? ORDER BY id DESC LIMIT 80""",
            (exchange, market),
        ).fetchall()
        latest_trade: dict[str, dict[str, Any]] = {}
        for source in trade_rows:
            exp_id = str(source["experiment_id"])
            if exp_id not in latest_trade:
                latest_trade[exp_id] = dict(source)
        experiments: list[dict[str, Any]] = []
        for source in rows:
            row = dict(source)
            volume = _num(row.get("volume"))
            last_price = _num(row.get("last_price"), _num(row.get("avg_price")))
            avg_price = _num(row.get("avg_price"))
            cash = _num(row.get("cash_krw"))
            equity = cash + volume * last_price
            position_value = volume * last_price
            cost = volume * avg_price
            unrealized = position_value - cost if volume > 0 else 0.0
            closed = int(row.get("closed_trades") or 0)
            wins = int(row.get("wins") or 0)
            trade = latest_trade.get(str(row["experiment_id"]))
            experiments.append(
                {
                    "experiment_id": row["experiment_id"],
                    "style": row["style"],
                    "label": row["label"],
                    "description": row["description"],
                    "status": row["status"],
                    "custom": str(row["style"]).startswith("custom_"),
                    "primary_style": row.get("primary_style"),
                    "secondary_style": row.get("secondary_style"),
                    "mix_ratio": _num(row.get("mix_ratio")) if row.get("mix_ratio") is not None else None,
                    "equity_krw": round(equity, 2),
                    "return_pct": round((equity / START_KRW - 1.0) * 100.0, 6),
                    "cash_krw": round(cash, 2),
                    "position_value_krw": round(position_value, 2),
                    "avg_price": avg_price,
                    "last_price": last_price,
                    "unrealized_pnl_krw": round(unrealized, 2),
                    "realized_pnl_krw": round(_num(row.get("realized_pnl")), 2),
                    "max_drawdown_pct": round(_num(row.get("max_drawdown_pct")), 4),
                    "buy_count": int(row.get("buy_count") or 0),
                    "closed_trades": closed,
                    "wins": wins,
                    "win_rate_pct": round(wins / closed * 100.0, 3) if closed else 0.0,
                    "entry_bias": round(_num(row.get("entry_bias")), 4),
                    "weight_multiplier": round(_num(row.get("weight_multiplier"), 1.0), 4),
                    "ema_return_pct": round(_num(row.get("ema_return_pct")), 4),
                    "latest_trade": ({
                        "side": trade["side"], "ts": _num(trade["ts"]), "price": _num(trade["price"]),
                        "krw": round(_num(trade["krw"]), 2), "realized_pnl": round(_num(trade["realized_pnl"]), 2),
                        "return_pct": round(_num(trade["return_pct"]), 4), "reason": str(trade["reason"] or "")[:160],
                        "buy_index": int(trade["buy_index"] or 0),
                    } if trade else None),
                }
            )
        base["experiments"] = experiments
        return base
    except sqlite3.Error:
        return base
    finally:
        conn.close()
