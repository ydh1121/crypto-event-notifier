from __future__ import annotations

import math
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 1
MINUTE_RETENTION_SECONDS = 3 * 24 * 60 * 60
WINDOW_FEATURE_RETENTION = 2000
WINDOWS: tuple[tuple[str, int], ...] = (
    ("1m", 60),
    ("5m", 5 * 60),
    ("15m", 15 * 60),
    ("1h", 60 * 60),
    ("4h", 4 * 60 * 60),
    ("1d", 24 * 60 * 60),
)


class MarketFlowStreamStore:
    """Thread-affine SQLite store for continuous public WebSocket trade flow.

    Raw trades still share the existing REST dedupe key, but WebSocket continuity
    uses its own seen table. This prevents a race where REST stores a trade first
    and the same WebSocket trade is then incorrectly omitted from stream CVD.
    Minute buckets are separate so 1d flow windows do not depend on raw retention.
    """

    def __init__(self, path: Path | str = DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=10000")
        self._ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_market_trade_flow_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                sequential_id TEXT NOT NULL,
                trade_ts REAL NOT NULL,
                trade_price REAL NOT NULL,
                trade_volume REAL NOT NULL,
                quote_volume REAL NOT NULL,
                aggressor_side TEXT NOT NULL,
                side_source TEXT NOT NULL DEFAULT 'exchange',
                received_at REAL NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,sequential_id)
            );
            CREATE INDEX IF NOT EXISTS idx_research_market_trade_flow_mx_time
            ON research_market_trade_flow_mx(exchange,market,trade_ts DESC);

            CREATE TABLE IF NOT EXISTS research_market_flow_stream_seen_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                sequential_id TEXT NOT NULL,
                trade_ts REAL NOT NULL,
                received_at REAL NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,sequential_id)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_stream_seen_time
            ON research_market_flow_stream_seen_mx(exchange,market,trade_ts DESC);

            CREATE TABLE IF NOT EXISTS research_market_flow_stream_session_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                process_started_at REAL NOT NULL,
                connected_since REAL NOT NULL DEFAULT 0,
                last_disconnect_at REAL NOT NULL DEFAULT 0,
                last_trade_ts REAL NOT NULL DEFAULT 0,
                last_received_at REAL NOT NULL DEFAULT 0,
                messages_seen INTEGER NOT NULL DEFAULT 0,
                inserts INTEGER NOT NULL DEFAULT 0,
                reconnects INTEGER NOT NULL DEFAULT 0,
                connected INTEGER NOT NULL DEFAULT 0,
                session_cvd_quote REAL NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market)
            );

            CREATE TABLE IF NOT EXISTS research_market_flow_stream_minute_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                bucket_ts REAL NOT NULL,
                trade_count INTEGER NOT NULL DEFAULT 0,
                buy_volume REAL NOT NULL DEFAULT 0,
                sell_volume REAL NOT NULL DEFAULT 0,
                buy_quote_volume REAL NOT NULL DEFAULT 0,
                sell_quote_volume REAL NOT NULL DEFAULT 0,
                side_rows INTEGER NOT NULL DEFAULT 0,
                first_trade_ts REAL NOT NULL DEFAULT 0,
                last_trade_ts REAL NOT NULL DEFAULT 0,
                received_at REAL NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,bucket_ts)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_stream_minute_time
            ON research_market_flow_stream_minute_mx(exchange,market,bucket_ts DESC);

            CREATE TABLE IF NOT EXISTS research_market_flow_window_feature_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                window_label TEXT NOT NULL,
                window_seconds REAL NOT NULL,
                feature_ts REAL NOT NULL,
                window_start_ts REAL NOT NULL,
                window_end_ts REAL NOT NULL,
                trade_count INTEGER NOT NULL DEFAULT 0,
                buy_volume REAL NOT NULL DEFAULT 0,
                sell_volume REAL NOT NULL DEFAULT 0,
                buy_quote_volume REAL NOT NULL DEFAULT 0,
                sell_quote_volume REAL NOT NULL DEFAULT 0,
                delta_volume REAL NOT NULL DEFAULT 0,
                delta_quote REAL NOT NULL DEFAULT 0,
                delta_pct REAL,
                session_cvd_quote REAL NOT NULL DEFAULT 0,
                cvd_anchor_ts REAL NOT NULL DEFAULT 0,
                continuity_complete INTEGER NOT NULL DEFAULT 0,
                side_coverage_pct REAL,
                source TEXT NOT NULL DEFAULT 'public_websocket_trade',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,window_label,feature_ts)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_window_feature_time
            ON research_market_flow_window_feature_mx(exchange,market,window_label,feature_ts DESC);
            """
        )
        self.conn.commit()

    def mark_connected(
        self,
        exchange: str,
        markets: Iterable[str],
        *,
        process_started_at: float,
        connected_since: float,
        reconnects: int,
    ) -> None:
        now = time.time()
        with self.conn:
            for market in markets:
                self.conn.execute(
                    """INSERT INTO research_market_flow_stream_session_mx(
                           exchange,market,process_started_at,connected_since,last_disconnect_at,
                           last_trade_ts,last_received_at,messages_seen,inserts,reconnects,connected,
                           session_cvd_quote,updated_at,schema_version
                       ) VALUES(?,?,?,?,0,0,0,0,0,?,1,0,?,?)
                       ON CONFLICT(exchange,market) DO UPDATE SET
                           process_started_at=excluded.process_started_at,
                           connected_since=excluded.connected_since,
                           last_trade_ts=0,
                           last_received_at=0,
                           messages_seen=0,
                           inserts=0,
                           reconnects=excluded.reconnects,
                           connected=1,
                           session_cvd_quote=0,
                           updated_at=excluded.updated_at,
                           schema_version=excluded.schema_version""",
                    (
                        str(exchange),
                        str(market),
                        float(process_started_at),
                        float(connected_since),
                        int(reconnects),
                        float(now),
                        SCHEMA_VERSION,
                    ),
                )

    def mark_disconnected(self, exchange: str, markets: Iterable[str], *, disconnected_at: float) -> None:
        with self.conn:
            for market in markets:
                self.conn.execute(
                    """UPDATE research_market_flow_stream_session_mx
                       SET connected=0,last_disconnect_at=?,updated_at=?
                       WHERE exchange=? AND market=?""",
                    (float(disconnected_at), float(disconnected_at), str(exchange), str(market)),
                )

    @staticmethod
    def _minute_bucket(ts: float) -> float:
        return float(math.floor(float(ts) / 60.0) * 60)

    def insert_trades(self, rows: Iterable[dict[str, Any]], *, received_at: float | None = None) -> dict[str, int]:
        now = float(received_at or time.time())
        inserted = 0
        observed = 0
        raw_inserts = 0
        minute_delta: dict[tuple[str, str, float], dict[str, float]] = {}
        session_delta: dict[tuple[str, str], dict[str, float]] = {}
        with self.conn:
            for row in rows:
                try:
                    side = str(row.get("aggressor_side") or "").upper()
                    if side not in {"BID", "ASK"}:
                        continue
                    exchange = str(row["exchange"])
                    market = str(row["market"])
                    sequential_id = str(row["sequential_id"])
                    trade_ts = float(row["trade_ts"])
                    price = float(row["trade_price"])
                    volume = float(row["trade_volume"])
                    quote = float(row.get("quote_volume") or price * volume)
                except (KeyError, TypeError, ValueError):
                    continue
                if not sequential_id or trade_ts <= 0 or price <= 0 or volume <= 0:
                    continue
                observed += 1

                stream_cursor = self.conn.execute(
                    """INSERT OR IGNORE INTO research_market_flow_stream_seen_mx(
                           exchange,market,sequential_id,trade_ts,received_at,schema_version
                       ) VALUES(?,?,?,?,?,?)""",
                    (exchange, market, sequential_id, trade_ts, now, SCHEMA_VERSION),
                )
                if int(stream_cursor.rowcount or 0) <= 0:
                    continue
                inserted += 1

                raw_cursor = self.conn.execute(
                    """INSERT OR IGNORE INTO research_market_trade_flow_mx(
                           exchange,market,sequential_id,trade_ts,trade_price,trade_volume,
                           quote_volume,aggressor_side,side_source,received_at,schema_version
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        exchange,
                        market,
                        sequential_id,
                        trade_ts,
                        price,
                        volume,
                        quote,
                        side,
                        "exchange",
                        now,
                        SCHEMA_VERSION,
                    ),
                )
                if int(raw_cursor.rowcount or 0) > 0:
                    raw_inserts += 1

                bucket = self._minute_bucket(trade_ts)
                key = (exchange, market, bucket)
                agg = minute_delta.setdefault(
                    key,
                    {
                        "trade_count": 0.0,
                        "buy_volume": 0.0,
                        "sell_volume": 0.0,
                        "buy_quote": 0.0,
                        "sell_quote": 0.0,
                        "side_rows": 0.0,
                        "first_trade_ts": trade_ts,
                        "last_trade_ts": trade_ts,
                    },
                )
                agg["trade_count"] += 1
                agg["side_rows"] += 1
                agg["first_trade_ts"] = min(agg["first_trade_ts"], trade_ts)
                agg["last_trade_ts"] = max(agg["last_trade_ts"], trade_ts)
                if side == "BID":
                    agg["buy_volume"] += volume
                    agg["buy_quote"] += quote
                else:
                    agg["sell_volume"] += volume
                    agg["sell_quote"] += quote
                s_key = (exchange, market)
                s = session_delta.setdefault(s_key, {"messages": 0.0, "inserts": 0.0, "cvd": 0.0, "last_trade_ts": 0.0})
                s["messages"] += 1
                s["inserts"] += 1
                s["cvd"] += quote if side == "BID" else -quote
                s["last_trade_ts"] = max(s["last_trade_ts"], trade_ts)

            for (exchange, market, bucket), agg in minute_delta.items():
                self.conn.execute(
                    """INSERT INTO research_market_flow_stream_minute_mx(
                           exchange,market,bucket_ts,trade_count,buy_volume,sell_volume,
                           buy_quote_volume,sell_quote_volume,side_rows,first_trade_ts,last_trade_ts,
                           received_at,schema_version
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(exchange,market,bucket_ts) DO UPDATE SET
                           trade_count=trade_count+excluded.trade_count,
                           buy_volume=buy_volume+excluded.buy_volume,
                           sell_volume=sell_volume+excluded.sell_volume,
                           buy_quote_volume=buy_quote_volume+excluded.buy_quote_volume,
                           sell_quote_volume=sell_quote_volume+excluded.sell_quote_volume,
                           side_rows=side_rows+excluded.side_rows,
                           first_trade_ts=CASE
                               WHEN first_trade_ts<=0 THEN excluded.first_trade_ts
                               ELSE MIN(first_trade_ts,excluded.first_trade_ts)
                           END,
                           last_trade_ts=MAX(last_trade_ts,excluded.last_trade_ts),
                           received_at=excluded.received_at""",
                    (
                        exchange,
                        market,
                        bucket,
                        int(agg["trade_count"]),
                        agg["buy_volume"],
                        agg["sell_volume"],
                        agg["buy_quote"],
                        agg["sell_quote"],
                        int(agg["side_rows"]),
                        agg["first_trade_ts"],
                        agg["last_trade_ts"],
                        now,
                        SCHEMA_VERSION,
                    ),
                )

            for (exchange, market), agg in session_delta.items():
                self.conn.execute(
                    """UPDATE research_market_flow_stream_session_mx
                       SET messages_seen=messages_seen+?,inserts=inserts+?,
                           session_cvd_quote=session_cvd_quote+?,
                           last_trade_ts=MAX(last_trade_ts,?),last_received_at=?,updated_at=?
                       WHERE exchange=? AND market=?""",
                    (
                        int(agg["messages"]),
                        int(agg["inserts"]),
                        agg["cvd"],
                        agg["last_trade_ts"],
                        now,
                        now,
                        exchange,
                        market,
                    ),
                )
        return {"observed": observed, "inserted": inserted, "raw_inserts": raw_inserts}

    def session(self, exchange: str, market: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM research_market_flow_stream_session_mx WHERE exchange=? AND market=?",
            (str(exchange), str(market)),
        ).fetchone()
        return dict(row) if row else {}

    def compute_window_features(self, *, now: float | None = None) -> int:
        current = float(now or time.time())
        feature_ts = float(math.floor(current / 60.0) * 60)
        sessions = self.conn.execute(
            "SELECT * FROM research_market_flow_stream_session_mx"
        ).fetchall()
        written = 0
        with self.conn:
            for session_row in sessions:
                session = dict(session_row)
                exchange = str(session["exchange"])
                market = str(session["market"])
                connected_since = float(session.get("connected_since") or 0.0)
                connected = bool(session.get("connected"))
                session_cvd = float(session.get("session_cvd_quote") or 0.0)
                for label, seconds in WINDOWS:
                    start_ts = feature_ts - float(seconds)
                    row = self.conn.execute(
                        """SELECT SUM(trade_count) AS trade_count,
                                  SUM(buy_volume) AS buy_volume,
                                  SUM(sell_volume) AS sell_volume,
                                  SUM(buy_quote_volume) AS buy_quote_volume,
                                  SUM(sell_quote_volume) AS sell_quote_volume,
                                  SUM(side_rows) AS side_rows
                           FROM research_market_flow_stream_minute_mx
                           WHERE exchange=? AND market=? AND bucket_ts>=? AND bucket_ts<?""",
                        (exchange, market, start_ts, feature_ts),
                    ).fetchone()
                    count = int(row["trade_count"] or 0) if row else 0
                    buy_volume = float(row["buy_volume"] or 0.0) if row else 0.0
                    sell_volume = float(row["sell_volume"] or 0.0) if row else 0.0
                    buy_quote = float(row["buy_quote_volume"] or 0.0) if row else 0.0
                    sell_quote = float(row["sell_quote_volume"] or 0.0) if row else 0.0
                    side_rows = int(row["side_rows"] or 0) if row else 0
                    total_quote = buy_quote + sell_quote
                    continuity_complete = bool(connected and connected_since > 0 and connected_since <= start_ts)
                    self.conn.execute(
                        """INSERT OR REPLACE INTO research_market_flow_window_feature_mx(
                               exchange,market,window_label,window_seconds,feature_ts,window_start_ts,
                               window_end_ts,trade_count,buy_volume,sell_volume,buy_quote_volume,
                               sell_quote_volume,delta_volume,delta_quote,delta_pct,session_cvd_quote,
                               cvd_anchor_ts,continuity_complete,side_coverage_pct,source,received_at,
                               feature_version
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            exchange,
                            market,
                            label,
                            float(seconds),
                            feature_ts,
                            start_ts,
                            feature_ts,
                            count,
                            buy_volume,
                            sell_volume,
                            buy_quote,
                            sell_quote,
                            buy_volume - sell_volume,
                            buy_quote - sell_quote,
                            ((buy_quote - sell_quote) / total_quote * 100.0) if total_quote > 0 else None,
                            session_cvd,
                            connected_since,
                            1 if continuity_complete else 0,
                            (side_rows / count * 100.0) if count > 0 else None,
                            "public_websocket_trade",
                            current,
                            SCHEMA_VERSION,
                        ),
                    )
                    written += 1
                    self._prune_window(exchange, market, label)
                cutoff = feature_ts - MINUTE_RETENTION_SECONDS
                self.conn.execute(
                    "DELETE FROM research_market_flow_stream_minute_mx WHERE exchange=? AND market=? AND bucket_ts<?",
                    (exchange, market, cutoff),
                )
                self.conn.execute(
                    "DELETE FROM research_market_flow_stream_seen_mx WHERE exchange=? AND market=? AND trade_ts<?",
                    (exchange, market, cutoff),
                )
        return written

    def _prune_window(self, exchange: str, market: str, label: str) -> None:
        self.conn.execute(
            """DELETE FROM research_market_flow_window_feature_mx
               WHERE rowid IN (
                   SELECT rowid FROM research_market_flow_window_feature_mx
                   WHERE exchange=? AND market=? AND window_label=?
                   ORDER BY feature_ts DESC
                   LIMIT -1 OFFSET ?
               )""",
            (str(exchange), str(market), str(label), WINDOW_FEATURE_RETENTION),
        )

    def audit(self) -> dict[str, Any]:
        tables = {
            "seen": "research_market_flow_stream_seen_mx",
            "sessions": "research_market_flow_stream_session_mx",
            "minutes": "research_market_flow_stream_minute_mx",
            "windows": "research_market_flow_window_feature_mx",
        }
        counts: dict[str, int] = {}
        for key, table in tables.items():
            counts[key] = int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        sessions = [dict(row) for row in self.conn.execute(
            """SELECT exchange,market,connected,connected_since,last_disconnect_at,last_trade_ts,
                      last_received_at,messages_seen,inserts,reconnects,session_cvd_quote,updated_at
               FROM research_market_flow_stream_session_mx
               ORDER BY exchange,market"""
        ).fetchall()]
        latest_windows = [dict(row) for row in self.conn.execute(
            """SELECT f.* FROM research_market_flow_window_feature_mx f
               JOIN (
                   SELECT exchange,market,window_label,MAX(feature_ts) AS max_ts
                   FROM research_market_flow_window_feature_mx
                   GROUP BY exchange,market,window_label
               ) latest
               ON latest.exchange=f.exchange AND latest.market=f.market
              AND latest.window_label=f.window_label AND latest.max_ts=f.feature_ts
               ORDER BY f.exchange,f.market,f.window_seconds"""
        ).fetchall()]
        invalid_side = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_trade_flow_mx WHERE aggressor_side NOT IN ('BID','ASK')"
        ).fetchone()[0])
        non_exchange_side = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_trade_flow_mx WHERE side_source!='exchange'"
        ).fetchone()[0])
        return {
            "ok": True,
            "status": "ready" if counts["sessions"] > 0 else "empty",
            "tables_ready": True,
            "stream_seen_rows": counts["seen"],
            "session_rows": counts["sessions"],
            "minute_rows": counts["minutes"],
            "window_rows": counts["windows"],
            "invalid_side_rows": invalid_side,
            "non_exchange_side_rows": non_exchange_side,
            "stream_dedupe_independent_of_rest": True,
            "sessions": sessions,
            "latest_windows": latest_windows,
            "windows": [label for label, _ in WINDOWS],
            "paper_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "raw_cloud_projection": False,
            "schema_version": SCHEMA_VERSION,
        }
