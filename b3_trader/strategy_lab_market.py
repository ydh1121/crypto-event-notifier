from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .paper_constants import DB_PATH, START_KRW
from .strategy_lab_context import read_coin_context
from .strategy_lab_journal import TRADE_COLUMNS, reconcile_account
from .strategy_lab_plan import project_plan
from .strategy_lab_rules import STYLE_SPECS, StyleSpec, _num


def read_strategy_lab_market(exchange: str, market: str, path: Path = DB_PATH) -> dict[str, Any]:
    """One consistent, read-only account + COMPLETE journal view, scoped to one coin.

    Publication may put large journals into immutable detail chunks. API pagination
    operates on this exact revision, so polling cannot mix account and fill versions.
    No Store constructors, initialization, migration, pruning or exchange calls.
    """
    exchange, market, path = str(exchange or "").strip().lower(), str(market or "").strip().upper(), Path(path)
    base: dict[str, Any] = {"version": 2, "paper_only": True, "exchange": exchange, "market": market,
                           "quote_currency": market.split("-", 1)[0], "experiments": [], "status": "unavailable"}
    if exchange not in {"bithumb", "upbit"} or not market.startswith("KRW-") or not path.is_file():
        return base
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"strategy_lab_experiments", "strategy_lab_accounts", "strategy_lab_learning", "strategy_lab_trades"}
        if not required.issubset(tables):
            return base
        custom = "strategy_lab_custom_specs" in tables
        custom_cols = ",c.primary_style,c.secondary_style,c.mix_ratio,c.spec_json" if custom else ",NULL AS spec_json"
        custom_join = "LEFT JOIN strategy_lab_custom_specs c ON c.experiment_id=e.experiment_id" if custom else ""
        rows = conn.execute(f"""SELECT a.*,e.style,e.label,e.description,e.status,e.initial_krw{custom_cols},
                COALESCE(l.entry_bias,0) AS entry_bias,COALESCE(l.weight_multiplier,1) AS weight_multiplier,
                COALESCE(l.ema_return_pct,0) AS ema_return_pct
            FROM strategy_lab_accounts a JOIN strategy_lab_experiments e USING(experiment_id)
            LEFT JOIN strategy_lab_learning l ON l.experiment_id=a.experiment_id AND l.market=a.market
            {custom_join} WHERE a.exchange=? AND e.exchange=? AND a.market=?
            ORDER BY e.status='running' DESC,e.created_ts,e.label""", (exchange, exchange, market)).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for r in conn.execute("SELECT * FROM strategy_lab_trades WHERE exchange=? AND market=? ORDER BY id", (exchange, market)):
            grouped.setdefault(str(r["experiment_id"]), []).append(dict(r))
        for raw in rows:
            a = dict(raw)
            exp_id = str(a["experiment_id"])
            trades = grouped.get(exp_id, [])
            memory = None
            if "research_market_memory_mx" in tables:
                r = conn.execute("""SELECT * FROM research_market_memory_mx
                    WHERE id=? AND exchange=? AND market=? AND strategy='adaptive'""",
                    (a["last_memory_id"], exchange, market)).fetchone()
                memory = dict(r) if r else None
            spec = STYLE_SPECS.get(a["style"])
            if a.get("spec_json"):
                try:
                    spec = StyleSpec(**json.loads(a["spec_json"]))
                except (TypeError, ValueError):
                    spec = None
            volume, last, cash, avg = (_num(a.get(k)) for k in ("volume", "last_price", "cash_krw", "avg_price"))
            equity = cash + volume * last
            closed, wins = int(a["closed_trades"]), int(a["wins"])
            initial = _num(a["initial_krw"], START_KRW)
            item = {k: a[k] for k in ("experiment_id", "style", "label", "description", "status", "cash_krw",
                "volume", "avg_price", "last_price", "updated_ts", "last_memory_id", "entry_ts", "buy_count",
                "closed_trades", "wins", "max_drawdown_pct", "entry_bias", "weight_multiplier", "ema_return_pct")}
            item.update(custom=str(a["style"]).startswith("custom_"), primary_style=a.get("primary_style"),
                secondary_style=a.get("secondary_style"), mix_ratio=a.get("mix_ratio"), initial_krw=initial,
                equity_krw=equity, return_pct=(equity / initial - 1) * 100 if initial > 0 else None,
                position_value_krw=volume * last, unrealized_pnl_krw=volume * (last - avg),
                realized_pnl_krw=a["realized_pnl"], win_rate_pct=wins / closed * 100 if closed else None,
                source_ts=(_num((memory or {}).get("signal_ts")) or _num((memory or {}).get("ts"))) or None,
                latest_trade={k: trades[-1][k] for k in TRADE_COLUMNS} if trades else None,
                reconciliation=reconcile_account(a, trades, initial), plan=project_plan(a, memory, spec))
            journal = {"columns": list(TRADE_COLUMNS), "rows": [[t[k] for k in TRADE_COLUMNS] for t in trades],
                       "total": len(trades), "complete": True}
            item["journal"] = journal
            item["revision"] = hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False,
                separators=(",", ":"), allow_nan=False).encode()).hexdigest()[:24]
            base["experiments"].append(item)
        base.update(read_coin_context(conn, tables, exchange, market))
        base["status"] = "ok" if rows else "no_account"
        return base
    except (sqlite3.Error, ValueError):
        base["status"] = "read_error"
        base["experiments"] = []
        return base
    finally:
        conn.close()
