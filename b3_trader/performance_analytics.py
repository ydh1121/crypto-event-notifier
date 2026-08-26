from __future__ import annotations

import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH, START_KRW

HISTORY_BUCKET_SECONDS = 300
HISTORY_DAYS = 14
MAX_HISTORY_POINTS = 2016  # 7 days at five-minute resolution


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS strategy_lab_equity_history (
            experiment_id TEXT NOT NULL,
            exchange TEXT NOT NULL,
            style TEXT NOT NULL,
            ts REAL NOT NULL,
            equity_krw REAL NOT NULL,
            start_krw REAL NOT NULL,
            realized_pnl REAL NOT NULL,
            return_pct REAL NOT NULL,
            drawdown_pct REAL NOT NULL,
            PRIMARY KEY(experiment_id, ts)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_lab_equity_history_exp_ts
            ON strategy_lab_equity_history(experiment_id, ts DESC);

        CREATE TABLE IF NOT EXISTS paper_portfolio_history (
            exchange TEXT NOT NULL,
            strategy TEXT NOT NULL,
            ts REAL NOT NULL,
            equity_krw REAL NOT NULL,
            start_krw REAL NOT NULL,
            pnl_krw REAL NOT NULL,
            return_pct REAL NOT NULL,
            drawdown_pct REAL NOT NULL,
            active_positions INTEGER NOT NULL,
            PRIMARY KEY(exchange, strategy, ts)
        );
        CREATE INDEX IF NOT EXISTS idx_paper_portfolio_history_scope_ts
            ON paper_portfolio_history(exchange, strategy, ts DESC);
        """
    )
    conn.commit()


def _bucket(now: float | None = None) -> float:
    value = time.time() if now is None else float(now)
    return float(int(value // HISTORY_BUCKET_SECONDS) * HISTORY_BUCKET_SECONDS)


def _drawdown(equity: float, peak: float) -> float:
    if peak <= 0:
        return 0.0
    return min(0.0, (equity / peak - 1.0) * 100.0)


def _capture_strategy(conn: sqlite3.Connection, ts: float) -> None:
    tables = {str(row["name"]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if not {"strategy_lab_metrics", "strategy_lab_experiments"}.issubset(tables):
        return
    rows = conn.execute(
        """SELECT m.experiment_id,m.exchange,m.style,m.total_equity_krw,m.aggregate_start_krw,
                  m.realized_pnl
             FROM strategy_lab_metrics m
             JOIN strategy_lab_experiments e USING(experiment_id)
            WHERE e.status IN ('running','paused')"""
    ).fetchall()
    for source in rows:
        row = dict(source)
        exp = str(row.get("experiment_id") or "")
        if not exp:
            continue
        equity = max(0.0, _num(row.get("total_equity_krw")))
        start = max(0.0, _num(row.get("aggregate_start_krw")))
        realized = _num(row.get("realized_pnl"))
        previous = conn.execute(
            "SELECT MAX(equity_krw) FROM strategy_lab_equity_history WHERE experiment_id=?",
            (exp,),
        ).fetchone()
        peak = max(start, equity, _num(previous[0] if previous else 0.0))
        ret = (equity / start - 1.0) * 100.0 if start > 0 else 0.0
        dd = _drawdown(equity, peak)
        conn.execute(
            """INSERT INTO strategy_lab_equity_history(
                experiment_id,exchange,style,ts,equity_krw,start_krw,realized_pnl,return_pct,drawdown_pct
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(experiment_id,ts) DO UPDATE SET
                equity_krw=excluded.equity_krw,start_krw=excluded.start_krw,
                realized_pnl=excluded.realized_pnl,return_pct=excluded.return_pct,
                drawdown_pct=excluded.drawdown_pct""",
            (exp, str(row.get("exchange") or ""), str(row.get("style") or ""), ts, equity, start, realized, ret, dd),
        )


def _capture_paper(conn: sqlite3.Connection, ts: float) -> None:
    tables = {str(row["name"]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "research_accounts_mx" not in tables:
        return
    has_signals = "research_signals_mx" in tables
    if has_signals:
        sql = """SELECT a.exchange,a.strategy,COUNT(*) AS markets,
                        SUM(a.cash_krw + a.volume * CASE WHEN COALESCE(s.price,0)>0 THEN s.price ELSE a.avg_price END) AS equity,
                        SUM(CASE WHEN a.volume>0 THEN 1 ELSE 0 END) AS active
                   FROM research_accounts_mx a
                   LEFT JOIN research_signals_mx s
                     ON s.exchange=a.exchange AND s.market=a.market AND s.strategy=a.strategy
                  WHERE a.strategy='adaptive'
                  GROUP BY a.exchange,a.strategy"""
    else:
        sql = """SELECT exchange,strategy,COUNT(*) AS markets,
                        SUM(cash_krw + volume * avg_price) AS equity,
                        SUM(CASE WHEN volume>0 THEN 1 ELSE 0 END) AS active
                   FROM research_accounts_mx
                  WHERE strategy='adaptive'
                  GROUP BY exchange,strategy"""
    for source in conn.execute(sql).fetchall():
        row = dict(source)
        exchange = str(row.get("exchange") or "")
        strategy = str(row.get("strategy") or "adaptive")
        markets = int(row.get("markets") or 0)
        equity = max(0.0, _num(row.get("equity")))
        start = START_KRW * markets
        pnl = equity - start
        ret = pnl / start * 100.0 if start > 0 else 0.0
        previous = conn.execute(
            "SELECT MAX(equity_krw) FROM paper_portfolio_history WHERE exchange=? AND strategy=?",
            (exchange, strategy),
        ).fetchone()
        peak = max(start, equity, _num(previous[0] if previous else 0.0))
        dd = _drawdown(equity, peak)
        conn.execute(
            """INSERT INTO paper_portfolio_history(
                exchange,strategy,ts,equity_krw,start_krw,pnl_krw,return_pct,drawdown_pct,active_positions
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(exchange,strategy,ts) DO UPDATE SET
                equity_krw=excluded.equity_krw,start_krw=excluded.start_krw,pnl_krw=excluded.pnl_krw,
                return_pct=excluded.return_pct,drawdown_pct=excluded.drawdown_pct,
                active_positions=excluded.active_positions""",
            (exchange, strategy, ts, equity, start, pnl, ret, dd, int(row.get("active") or 0)),
        )


def _trim(conn: sqlite3.Connection, now: float) -> None:
    cutoff = now - HISTORY_DAYS * 86400
    conn.execute("DELETE FROM strategy_lab_equity_history WHERE ts<?", (cutoff,))
    conn.execute("DELETE FROM paper_portfolio_history WHERE ts<?", (cutoff,))


def _history_by_experiment(conn: sqlite3.Connection) -> dict[str, list[list[float]]]:
    experiments = [
        str(row[0])
        for row in conn.execute("SELECT experiment_id FROM strategy_lab_experiments ORDER BY experiment_id").fetchall()
    ] if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='strategy_lab_experiments'").fetchone() else []
    out: dict[str, list[list[float]]] = {}
    for exp in experiments:
        rows = conn.execute(
            """SELECT ts,equity_krw,return_pct,drawdown_pct,realized_pnl
                 FROM strategy_lab_equity_history
                WHERE experiment_id=? ORDER BY ts DESC LIMIT ?""",
            (exp, MAX_HISTORY_POINTS),
        ).fetchall()
        if rows:
            out[exp] = [
                [round(_num(row["ts"]), 3), round(_num(row["equity_krw"]), 2), round(_num(row["return_pct"]), 5), round(_num(row["drawdown_pct"]), 5), round(_num(row["realized_pnl"]), 2)]
                for row in reversed(rows)
            ]
    return out


def _coin_matrix(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    required = {"strategy_lab_accounts", "strategy_lab_experiments"}
    tables = {str(row["name"]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if not required.issubset(tables):
        return {"bithumb": [], "upbit": []}
    rows = conn.execute(
        """SELECT a.experiment_id,a.exchange,a.market,a.cash_krw,a.volume,a.avg_price,a.realized_pnl,
                  a.max_drawdown_pct,a.closed_trades,a.wins,a.last_price,e.style,e.label,e.status
             FROM strategy_lab_accounts a
             JOIN strategy_lab_experiments e USING(experiment_id)
            WHERE e.status IN ('running','paused')
            ORDER BY a.exchange,a.market,e.style"""
    ).fetchall()
    grouped: dict[str, dict[str, list[list[Any]]]] = {"bithumb": {}, "upbit": {}}
    for source in rows:
        row = dict(source)
        exchange = str(row.get("exchange") or "bithumb")
        if exchange not in grouped:
            continue
        market = str(row.get("market") or "")
        if not market:
            continue
        price = max(0.0, _num(row.get("last_price"), _num(row.get("avg_price"))))
        volume = max(0.0, _num(row.get("volume")))
        cash = _num(row.get("cash_krw"))
        equity = cash + volume * price
        ret = (equity / START_KRW - 1.0) * 100.0 if START_KRW > 0 else 0.0
        avg = max(0.0, _num(row.get("avg_price")))
        unrealized = volume * (price - avg) if volume > 0 and avg > 0 else 0.0
        grouped[exchange].setdefault(market, []).append([
            str(row.get("experiment_id") or ""),
            str(row.get("style") or ""),
            round(ret, 5),
            round(_num(row.get("realized_pnl")), 2),
            round(unrealized, 2),
            round(_num(row.get("max_drawdown_pct")), 5),
            int(row.get("closed_trades") or 0),
            int(row.get("wins") or 0),
            1 if volume > 0 else 0,
        ])
    return {
        exchange: [{"market": market, "rows": values} for market, values in markets.items()]
        for exchange, markets in grouped.items()
    }


def _paper_history(conn: sqlite3.Connection) -> dict[str, list[list[float]]]:
    out: dict[str, list[list[float]]] = {"bithumb": [], "upbit": [], "combined": []}
    per_exchange: dict[str, list[dict[str, float]]] = {}
    for exchange in ("bithumb", "upbit"):
        rows = conn.execute(
            """SELECT ts,equity_krw,start_krw,pnl_krw,return_pct,drawdown_pct,active_positions
                 FROM paper_portfolio_history
                WHERE exchange=? AND strategy='adaptive' ORDER BY ts DESC LIMIT ?""",
            (exchange, MAX_HISTORY_POINTS),
        ).fetchall()
        ordered = [dict(row) for row in reversed(rows)]
        per_exchange[exchange] = ordered
        out[exchange] = [
            [round(_num(row.get("ts")), 3), round(_num(row.get("equity_krw")), 2), round(_num(row.get("pnl_krw")), 2), round(_num(row.get("return_pct")), 5), round(_num(row.get("drawdown_pct")), 5), int(row.get("active_positions") or 0)]
            for row in ordered
        ]
    by_ts: dict[float, dict[str, dict[str, float]]] = {}
    for exchange, rows in per_exchange.items():
        for row in rows:
            by_ts.setdefault(_num(row.get("ts")), {})[exchange] = row
    peak = 0.0
    for ts in sorted(by_ts):
        pair = by_ts[ts]
        if not pair:
            continue
        equity = sum(_num(row.get("equity_krw")) for row in pair.values())
        start = sum(_num(row.get("start_krw")) for row in pair.values())
        pnl = equity - start
        ret = pnl / start * 100.0 if start > 0 else 0.0
        peak = max(peak, start, equity)
        dd = _drawdown(equity, peak)
        active = sum(int(row.get("active_positions") or 0) for row in pair.values())
        out["combined"].append([round(ts, 3), round(equity, 2), round(pnl, 2), round(ret, 5), round(dd, 5), active])
    out["combined"] = out["combined"][-MAX_HISTORY_POINTS:]
    return out


def read_performance_analytics(path: Path = DB_PATH) -> dict[str, Any]:
    base = {
        "version": 1,
        "history_bucket_seconds": HISTORY_BUCKET_SECONDS,
        "strategy_equity_history": {},
        "coin_matrix": {"bithumb": [], "upbit": []},
        "paper_history": {"bithumb": [], "upbit": [], "combined": []},
    }
    if not path.exists():
        return base
    conn = _connect(path)
    try:
        _ensure_schema(conn)
        now = time.time()
        ts = _bucket(now)
        with conn:
            _capture_strategy(conn, ts)
            _capture_paper(conn, ts)
            _trim(conn, now)
        base["strategy_equity_history"] = _history_by_experiment(conn)
        base["coin_matrix"] = _coin_matrix(conn)
        base["paper_history"] = _paper_history(conn)
        return base
    except sqlite3.Error:
        return base
    finally:
        conn.close()
