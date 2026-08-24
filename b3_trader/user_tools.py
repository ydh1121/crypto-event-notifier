from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any


MAX_AVERAGING_ROWS = 20


def calculate_averaging(
    *,
    volume: float,
    avg_price: float,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    current_volume = max(0.0, float(volume or 0.0))
    current_avg = max(0.0, float(avg_price or 0.0))
    current_cost = current_volume * current_avg
    stages: list[dict[str, Any]] = []

    for index, raw in enumerate(rows[:MAX_AVERAGING_ROWS], start=1):
        price = max(0.0, float(raw.get("price") or 0.0))
        amount_krw = max(0.0, float(raw.get("amount_krw") or 0.0))
        if price <= 0 or amount_krw <= 0:
            continue
        buy_volume = amount_krw / price
        current_volume += buy_volume
        current_cost += amount_krw
        current_avg = current_cost / current_volume if current_volume > 0 else 0.0
        stages.append(
            {
                "round": index,
                "price": round(price, 12),
                "amount_krw": round(amount_krw, 2),
                "buy_volume": round(buy_volume, 12),
                "total_volume": round(current_volume, 12),
                "total_cost_krw": round(current_cost, 2),
                "avg_price": round(current_avg, 12),
            }
        )

    return {
        "starting_volume": round(max(0.0, float(volume or 0.0)), 12),
        "starting_avg_price": round(max(0.0, float(avg_price or 0.0)), 12),
        "stages": stages,
        "final_volume": round(current_volume, 12),
        "final_cost_krw": round(current_cost, 2),
        "final_avg_price": round(current_avg, 12),
    }


class UserToolsStore:
    """Local-only manual holdings and averaging plans stored in the journal DB."""

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
                CREATE TABLE IF NOT EXISTS manual_holdings (
                    market TEXT PRIMARY KEY,
                    volume REAL NOT NULL,
                    avg_price REAL NOT NULL,
                    updated_ts REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS averaging_plans (
                    market TEXT PRIMARY KEY,
                    rows_json TEXT NOT NULL,
                    updated_ts REAL NOT NULL
                );
                """
            )

    def get_holding(self, market: str) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT market, volume, avg_price, updated_ts FROM manual_holdings WHERE market = ?",
                (market,),
            ).fetchone()
        if row is None:
            return {"market": market, "volume": 0.0, "avg_price": 0.0, "updated_ts": None}
        return dict(row)

    def list_holdings(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT market, volume, avg_price, updated_ts FROM manual_holdings ORDER BY market"
            ).fetchall()
        return [dict(row) for row in rows]

    def set_holding(self, market: str, *, volume: float, avg_price: float) -> dict[str, Any]:
        volume = max(0.0, float(volume))
        avg_price = max(0.0, float(avg_price))
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO manual_holdings(market, volume, avg_price, updated_ts) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(market) DO UPDATE SET volume=excluded.volume, avg_price=excluded.avg_price, updated_ts=excluded.updated_ts",
                (market, volume, avg_price, now),
            )
        return self.get_holding(market)

    def delete_holding(self, market: str) -> bool:
        with self._lock, self._conn:
            cursor = self._conn.execute("DELETE FROM manual_holdings WHERE market = ?", (market,))
        return cursor.rowcount > 0

    def get_plan(self, market: str) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT market, rows_json, updated_ts FROM averaging_plans WHERE market = ?",
                (market,),
            ).fetchone()
        if row is None:
            return {"market": market, "rows": [], "updated_ts": None}
        try:
            rows = json.loads(row["rows_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            rows = []
        return {"market": market, "rows": rows if isinstance(rows, list) else [], "updated_ts": row["updated_ts"]}

    def set_plan(self, market: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        cleaned: list[dict[str, float]] = []
        for raw in rows[:MAX_AVERAGING_ROWS]:
            try:
                price = max(0.0, float(raw.get("price") or 0.0))
                amount = max(0.0, float(raw.get("amount_krw") or 0.0))
            except (TypeError, ValueError):
                continue
            cleaned.append({"price": price, "amount_krw": amount})
        now = time.time()
        encoded = json.dumps(cleaned, ensure_ascii=False)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO averaging_plans(market, rows_json, updated_ts) VALUES (?, ?, ?) "
                "ON CONFLICT(market) DO UPDATE SET rows_json=excluded.rows_json, updated_ts=excluded.updated_ts",
                (market, encoded, now),
            )
        return self.get_plan(market)

    def delete_plan(self, market: str) -> bool:
        with self._lock, self._conn:
            cursor = self._conn.execute("DELETE FROM averaging_plans WHERE market = ?", (market,))
        return cursor.rowcount > 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()
