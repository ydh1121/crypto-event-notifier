from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import asdict, is_dataclass
from typing import Any


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value


class TradeJournal:
    def __init__(self, path: str) -> None:
        self.path = path
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
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

                CREATE INDEX IF NOT EXISTS idx_snapshots_ts
                    ON snapshots(ts);

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

                CREATE INDEX IF NOT EXISTS idx_fills_ts
                    ON fills(ts);

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_ts
                    ON events(ts);
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
                """
                INSERT INTO snapshots(
                    ts, market, price, regime_score, entry_score, action, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
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
                """
                INSERT INTO fills(
                    ts, mode, market, side, price, volume, krw, reason, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
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

    def counts(self) -> dict[str, int]:
        with self._lock:
            snapshots = self._conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            fills = self._conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0]
            events = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return {"snapshots": snapshots, "fills": fills, "events": events}

    def close(self) -> None:
        with self._lock:
            self._conn.close()
