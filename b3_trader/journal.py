from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import asdict, is_dataclass
from typing import Any


def _jsonable(value: Any) -> Any:
    return asdict(value) if is_dataclass(value) else value


class TradeJournal:
    def __init__(self, path: str) -> None:
        self.path = path
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    market TEXT NOT NULL,
                    price REAL NOT NULL,
                    regime_score REAL NOT NULL,
                    entry_score REAL NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);
                CREATE INDEX IF NOT EXISTS idx_snapshots_market_ts ON snapshots(market, ts);

                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    mode TEXT NOT NULL,
                    market TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume REAL NOT NULL,
                    krw REAL NOT NULL,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_fills_ts ON fills(ts);
                CREATE INDEX IF NOT EXISTS idx_fills_market_ts ON fills(market, ts);

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    cash_krw REAL NOT NULL,
                    equity_krw REAL NOT NULL,
                    exposure_krw REAL NOT NULL,
                    daily_drawdown_pct REAL NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_ts
                    ON portfolio_snapshots(ts);
                """
            )

    def record_snapshot(
        self,
        *,
        market: str,
        price: float,
        regime_score: float,
        entry_score: float,
        action: str,
        payload: dict[str, Any],
        ts: float | None = None,
    ) -> None:
        timestamp = ts if ts is not None else time.time()
        encoded = json.dumps(payload, ensure_ascii=False, default=_jsonable)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO snapshots(ts, market, price, regime_score, entry_score, action, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    timestamp,
                    market,
                    price,
                    regime_score,
                    entry_score,
                    action,
                    encoded,
                ),
            )

    def record_portfolio_snapshot(
        self,
        payload: dict[str, Any],
        *,
        ts: float | None = None,
    ) -> None:
        timestamp = ts if ts is not None else time.time()
        encoded = json.dumps(payload, ensure_ascii=False, default=_jsonable)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO portfolio_snapshots(ts, cash_krw, equity_krw, exposure_krw, "
                "daily_drawdown_pct, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    timestamp,
                    float(payload.get("cash_krw") or 0.0),
                    float(payload.get("equity_krw") or 0.0),
                    float(payload.get("exposure_krw") or 0.0),
                    float(payload.get("daily_drawdown_pct") or 0.0),
                    encoded,
                ),
            )

    def record_fill(
        self,
        *,
        mode: str,
        market: str,
        fill: Any,
        ts: float | None = None,
    ) -> None:
        timestamp = ts if ts is not None else time.time()
        payload = _jsonable(fill)
        encoded = json.dumps(payload, ensure_ascii=False, default=_jsonable)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO fills(ts, mode, market, side, price, volume, krw, reason, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    timestamp,
                    mode,
                    market,
                    str(payload["side"]),
                    float(payload["price"]),
                    float(payload["volume"]),
                    float(payload["krw"]),
                    str(payload["reason"]),
                    encoded,
                ),
            )

    def record_event(
        self,
        kind: str,
        payload: dict[str, Any],
        ts: float | None = None,
    ) -> None:
        timestamp = ts if ts is not None else time.time()
        encoded = json.dumps(payload, ensure_ascii=False, default=_jsonable)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO events(ts, kind, payload_json) VALUES (?, ?, ?)",
                (timestamp, kind, encoded),
            )

    def recent_fills(self, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(500, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, mode, market, side, price, volume, krw, reason "
                "FROM fills ORDER BY id DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def paper_fills_chronological(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, mode, market, side, price, volume, krw, reason "
                "FROM fills WHERE mode = 'paper' ORDER BY id ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(1000, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, kind, payload_json FROM events ORDER BY id DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return [
            {
                "ts": row["ts"],
                "kind": row["kind"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def latest_snapshot(self, market: str | None = None) -> dict[str, Any] | None:
        query = (
            "SELECT ts, market, price, regime_score, entry_score, action, payload_json "
            "FROM snapshots "
        )
        params: tuple[Any, ...] = ()
        if market:
            query += "WHERE market = ? "
            params = (market,)
        query += "ORDER BY id DESC LIMIT 1"
        with self._lock:
            row = self._conn.execute(query, params).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["payload"] = json.loads(payload.pop("payload_json"))
        return payload

    def snapshot_history(
        self,
        market: str,
        *,
        since_seconds: float = 86_400.0,
        limit: int = 900,
    ) -> list[dict[str, Any]]:
        safe_limit = max(20, min(5000, int(limit)))
        cutoff = time.time() - max(60.0, float(since_seconds))
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, price, regime_score, entry_score, action, payload_json "
                "FROM snapshots WHERE market = ? AND ts >= ? "
                "ORDER BY id DESC LIMIT ?",
                (market, cutoff, safe_limit),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in reversed(rows):
            payload = json.loads(row["payload_json"])
            result.append(
                {
                    "ts": float(row["ts"]),
                    "price": float(row["price"]),
                    "regime_score": float(row["regime_score"]),
                    "entry_score": float(row["entry_score"]),
                    "action": str(row["action"]),
                    "context_score": payload.get("context_score"),
                    "relative_strength_pct": payload.get("asset_vs_majors_pct"),
                    "pullback_pct": payload.get("pullback_pct"),
                    "orderbook_imbalance": payload.get("orderbook_imbalance"),
                }
            )
        return result

    def fills_for_market(
        self,
        market: str,
        *,
        since_seconds: float = 604_800.0,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(2000, int(limit)))
        cutoff = time.time() - max(60.0, float(since_seconds))
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, mode, market, side, price, volume, krw, reason "
                "FROM fills WHERE market = ? AND ts >= ? ORDER BY id DESC LIMIT ?",
                (market, cutoff, safe_limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def portfolio_history(
        self,
        *,
        since_seconds: float = 604_800.0,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        safe_limit = max(20, min(5000, int(limit)))
        cutoff = time.time() - max(60.0, float(since_seconds))
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, cash_krw, equity_krw, exposure_krw, daily_drawdown_pct "
                "FROM portfolio_snapshots WHERE ts >= ? ORDER BY id DESC LIMIT ?",
                (cutoff, safe_limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def paper_trade_stats(self) -> dict[str, Any]:
        fills = self.paper_fills_chronological()
        positions: dict[str, dict[str, float]] = {}
        realized_pnl = 0.0
        winning_pnl = 0.0
        losing_pnl = 0.0
        closed_trades = 0
        wins = 0
        losses = 0
        per_market: dict[str, dict[str, float | int]] = {}

        for fill in fills:
            market = str(fill["market"])
            side = str(fill["side"]).lower()
            volume = float(fill["volume"])
            krw = float(fill["krw"])
            position = positions.setdefault(market, {"volume": 0.0, "cost": 0.0})
            stats = per_market.setdefault(
                market,
                {
                    "realized_pnl_krw": 0.0,
                    "closed_trades": 0,
                    "wins": 0,
                    "losses": 0,
                },
            )

            if side == "buy":
                position["volume"] += volume
                position["cost"] += krw
                continue

            if side != "sell" or volume <= 0:
                continue

            average_cost = (
                position["cost"] / position["volume"]
                if position["volume"] > 0
                else 0.0
            )
            matched_volume = min(volume, position["volume"])
            cost_basis = average_cost * matched_volume
            pnl = krw - cost_basis
            realized_pnl += pnl
            stats["realized_pnl_krw"] = float(stats["realized_pnl_krw"]) + pnl
            closed_trades += 1
            stats["closed_trades"] = int(stats["closed_trades"]) + 1

            if pnl > 0:
                wins += 1
                winning_pnl += pnl
                stats["wins"] = int(stats["wins"]) + 1
            elif pnl < 0:
                losses += 1
                losing_pnl += pnl
                stats["losses"] = int(stats["losses"]) + 1

            if position["volume"] > 0:
                remaining_volume = max(0.0, position["volume"] - matched_volume)
                position["volume"] = remaining_volume
                position["cost"] = average_cost * remaining_volume

        win_rate = wins / closed_trades * 100.0 if closed_trades else 0.0
        profit_factor = (
            winning_pnl / abs(losing_pnl)
            if losing_pnl < 0
            else (float("inf") if winning_pnl > 0 else 0.0)
        )

        history = self.portfolio_history(since_seconds=365 * 86_400.0, limit=5000)
        peak: float | None = None
        max_drawdown_pct = 0.0
        for point in history:
            equity = float(point["equity_krw"])
            peak = equity if peak is None else max(peak, equity)
            if peak and peak > 0:
                drawdown = (peak - equity) / peak * 100.0
                max_drawdown_pct = max(max_drawdown_pct, drawdown)

        return {
            "realized_pnl_krw": round(realized_pnl, 2),
            "closed_trades": closed_trades,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": None if profit_factor == float("inf") else round(profit_factor, 3),
            "profit_factor_infinite": profit_factor == float("inf"),
            "max_drawdown_pct": round(max_drawdown_pct, 4),
            "per_market": per_market,
        }

    def counts(self) -> dict[str, int]:
        with self._lock:
            snapshots = self._conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            fills = self._conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0]
            events = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            portfolio_snapshots = self._conn.execute(
                "SELECT COUNT(*) FROM portfolio_snapshots"
            ).fetchone()[0]
        return {
            "snapshots": snapshots,
            "fills": fills,
            "events": events,
            "portfolio_snapshots": portfolio_snapshots,
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()
