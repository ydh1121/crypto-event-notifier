from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 1
DEFAULT_RETENTION_BARS = 400


class MarketOhlcvStore:
    """Additive local SQLite owner for bounded multi-timeframe public OHLCV."""

    def __init__(self, path: Path | str = DB_PATH, *, retention_bars: int = DEFAULT_RETENTION_BARS) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_bars = max(50, int(retention_bars))
        self.conn = sqlite3.connect(str(self.path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_market_ohlcv_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                candle_ts REAL NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                base_volume REAL NOT NULL DEFAULT 0,
                quote_volume REAL NOT NULL DEFAULT 0,
                is_closed INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'public_rest',
                received_at REAL NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,timeframe,candle_ts)
            );
            CREATE INDEX IF NOT EXISTS idx_research_market_ohlcv_mx_lookup
            ON research_market_ohlcv_mx(exchange,market,timeframe,candle_ts DESC);
            CREATE INDEX IF NOT EXISTS idx_research_market_ohlcv_mx_received
            ON research_market_ohlcv_mx(received_at DESC);
            """
        )
        self.conn.commit()

    def latest_ts(self, exchange: str, market: str, timeframe: str) -> float:
        row = self.conn.execute(
            """SELECT MAX(candle_ts) AS ts
               FROM research_market_ohlcv_mx
               WHERE exchange=? AND market=? AND timeframe=?""",
            (str(exchange), str(market), str(timeframe)),
        ).fetchone()
        return float(row["ts"] or 0.0) if row else 0.0

    def upsert_rows(self, rows: Iterable[dict[str, Any]]) -> int:
        prepared: list[tuple[Any, ...]] = []
        for row in rows:
            try:
                prepared.append(
                    (
                        str(row["exchange"]),
                        str(row["market"]),
                        str(row["timeframe"]),
                        float(row["candle_ts"]),
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                        float(row.get("base_volume") or 0.0),
                        float(row.get("quote_volume") or 0.0),
                        1 if bool(row.get("is_closed")) else 0,
                        str(row.get("source") or "public_rest"),
                        float(row.get("received_at") or time.time()),
                        int(row.get("schema_version") or SCHEMA_VERSION),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not prepared:
            return 0
        self.conn.executemany(
            """INSERT INTO research_market_ohlcv_mx(
                   exchange,market,timeframe,candle_ts,open,high,low,close,
                   base_volume,quote_volume,is_closed,source,received_at,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(exchange,market,timeframe,candle_ts) DO UPDATE SET
                   open=excluded.open,
                   high=excluded.high,
                   low=excluded.low,
                   close=excluded.close,
                   base_volume=excluded.base_volume,
                   quote_volume=excluded.quote_volume,
                   is_closed=excluded.is_closed,
                   source=excluded.source,
                   received_at=excluded.received_at,
                   schema_version=excluded.schema_version""",
            prepared,
        )
        self.conn.commit()
        return len(prepared)

    def prune(self, exchange: str, market: str, timeframe: str, *, keep: int | None = None) -> int:
        limit = max(50, int(keep or self.retention_bars))
        before = self.conn.total_changes
        self.conn.execute(
            """DELETE FROM research_market_ohlcv_mx
               WHERE rowid IN (
                   SELECT rowid FROM research_market_ohlcv_mx
                   WHERE exchange=? AND market=? AND timeframe=?
                   ORDER BY candle_ts DESC
                   LIMIT -1 OFFSET ?
               )""",
            (str(exchange), str(market), str(timeframe), limit),
        )
        self.conn.commit()
        return max(0, self.conn.total_changes - before)

    def rows(
        self,
        exchange: str,
        market: str,
        timeframe: str,
        *,
        limit: int = DEFAULT_RETENTION_BARS,
    ) -> list[dict[str, Any]]:
        result = self.conn.execute(
            """SELECT exchange,market,timeframe,candle_ts,open,high,low,close,
                      base_volume,quote_volume,is_closed,source,received_at,schema_version
               FROM research_market_ohlcv_mx
               WHERE exchange=? AND market=? AND timeframe=?
               ORDER BY candle_ts DESC LIMIT ?""",
            (str(exchange), str(market), str(timeframe), max(1, min(self.retention_bars, int(limit)))),
        ).fetchall()
        return [dict(row) for row in result]

    def audit(self) -> dict[str, Any]:
        total = int(self.conn.execute("SELECT COUNT(*) FROM research_market_ohlcv_mx").fetchone()[0])
        grouped = self.conn.execute(
            """SELECT timeframe,COUNT(*) AS rows,COUNT(DISTINCT exchange||':'||market) AS markets,
                      MIN(candle_ts) AS oldest_ts,MAX(candle_ts) AS latest_ts,MAX(received_at) AS received_at
               FROM research_market_ohlcv_mx GROUP BY timeframe ORDER BY timeframe"""
        ).fetchall()
        return {
            "schema_version": SCHEMA_VERSION,
            "retention_bars_per_market_timeframe": self.retention_bars,
            "row_count": total,
            "timeframes": {
                str(row["timeframe"]): {
                    "rows": int(row["rows"] or 0),
                    "markets": int(row["markets"] or 0),
                    "oldest_ts": float(row["oldest_ts"] or 0.0),
                    "latest_ts": float(row["latest_ts"] or 0.0),
                    "received_at": float(row["received_at"] or 0.0),
                }
                for row in grouped
            },
        }
