from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 1
DEFAULT_TRADE_RETENTION = 20000
DEFAULT_BOOK_RETENTION = 400
DEFAULT_FEATURE_RETENTION = 400


class MarketFlowStore:
    """Additive local SQLite owner for observed public trade/orderbook flow.

    Raw public trades are deduplicated by exchange+market+sequential_id. CVD is
    explicitly an observed, locally anchored value; continuity metadata is kept
    separately so incomplete REST coverage can never be presented as complete.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        trade_retention: int = DEFAULT_TRADE_RETENTION,
        book_retention: int = DEFAULT_BOOK_RETENTION,
        feature_retention: int = DEFAULT_FEATURE_RETENTION,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.trade_retention = max(1000, int(trade_retention))
        self.book_retention = max(50, int(book_retention))
        self.feature_retention = max(50, int(feature_retention))
        self.conn = sqlite3.connect(str(self.path), timeout=10)
        self.conn.row_factory = sqlite3.Row
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

            CREATE TABLE IF NOT EXISTS research_market_flow_cursor_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                coverage_start_ts REAL NOT NULL DEFAULT 0,
                covered_through_ts REAL NOT NULL DEFAULT 0,
                last_seen_trade_ts REAL NOT NULL DEFAULT 0,
                last_cycle_complete INTEGER NOT NULL DEFAULT 0,
                last_pages INTEGER NOT NULL DEFAULT 0,
                last_rows INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market)
            );

            CREATE TABLE IF NOT EXISTS research_market_orderbook_flow_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                snapshot_ts REAL NOT NULL,
                source_ts REAL NOT NULL DEFAULT 0,
                best_bid REAL,
                best_ask REAL,
                spread_bps REAL,
                bid_depth_quote_5 REAL NOT NULL DEFAULT 0,
                ask_depth_quote_5 REAL NOT NULL DEFAULT 0,
                imbalance_5 REAL,
                bid_depth_quote_all REAL NOT NULL DEFAULT 0,
                ask_depth_quote_all REAL NOT NULL DEFAULT 0,
                imbalance_all REAL,
                received_at REAL NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,snapshot_ts)
            );
            CREATE INDEX IF NOT EXISTS idx_research_market_orderbook_flow_mx_time
            ON research_market_orderbook_flow_mx(exchange,market,snapshot_ts DESC);

            CREATE TABLE IF NOT EXISTS research_market_flow_feature_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                feature_ts REAL NOT NULL,
                window_seconds REAL NOT NULL DEFAULT 0,
                window_start_ts REAL NOT NULL DEFAULT 0,
                window_end_ts REAL NOT NULL DEFAULT 0,
                trade_count INTEGER NOT NULL DEFAULT 0,
                buy_volume REAL NOT NULL DEFAULT 0,
                sell_volume REAL NOT NULL DEFAULT 0,
                buy_quote_volume REAL NOT NULL DEFAULT 0,
                sell_quote_volume REAL NOT NULL DEFAULT 0,
                delta_volume REAL NOT NULL DEFAULT 0,
                delta_quote REAL NOT NULL DEFAULT 0,
                delta_pct REAL,
                observed_cvd_quote REAL NOT NULL DEFAULT 0,
                cvd_anchor_ts REAL NOT NULL DEFAULT 0,
                continuity_complete INTEGER NOT NULL DEFAULT 0,
                side_coverage_pct REAL,
                spread_bps REAL,
                imbalance_5 REAL,
                imbalance_all REAL,
                source TEXT NOT NULL DEFAULT 'public_rest',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,feature_ts)
            );
            CREATE INDEX IF NOT EXISTS idx_research_market_flow_feature_mx_time
            ON research_market_flow_feature_mx(exchange,market,feature_ts DESC);
            """
        )
        self.conn.commit()

    def cursor(self, exchange: str, market: str) -> dict[str, Any]:
        row = self.conn.execute(
            """SELECT * FROM research_market_flow_cursor_mx
               WHERE exchange=? AND market=?""",
            (str(exchange), str(market)),
        ).fetchone()
        return dict(row) if row else {}

    def upsert_cursor(self, exchange: str, market: str, values: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO research_market_flow_cursor_mx(
                   exchange,market,coverage_start_ts,covered_through_ts,last_seen_trade_ts,
                   last_cycle_complete,last_pages,last_rows,updated_at,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(exchange,market) DO UPDATE SET
                   coverage_start_ts=excluded.coverage_start_ts,
                   covered_through_ts=excluded.covered_through_ts,
                   last_seen_trade_ts=excluded.last_seen_trade_ts,
                   last_cycle_complete=excluded.last_cycle_complete,
                   last_pages=excluded.last_pages,
                   last_rows=excluded.last_rows,
                   updated_at=excluded.updated_at,
                   schema_version=excluded.schema_version""",
            (
                str(exchange),
                str(market),
                float(values.get("coverage_start_ts") or 0.0),
                float(values.get("covered_through_ts") or 0.0),
                float(values.get("last_seen_trade_ts") or 0.0),
                1 if bool(values.get("last_cycle_complete")) else 0,
                int(values.get("last_pages") or 0),
                int(values.get("last_rows") or 0),
                float(values.get("updated_at") or time.time()),
                SCHEMA_VERSION,
            ),
        )
        self.conn.commit()

    def insert_trades(self, rows: Iterable[dict[str, Any]]) -> int:
        prepared: list[tuple[Any, ...]] = []
        for row in rows:
            try:
                side = str(row.get("aggressor_side") or "").upper()
                if side not in {"BID", "ASK"}:
                    continue
                prepared.append(
                    (
                        str(row["exchange"]),
                        str(row["market"]),
                        str(row["sequential_id"]),
                        float(row["trade_ts"]),
                        float(row["trade_price"]),
                        float(row["trade_volume"]),
                        float(row.get("quote_volume") or 0.0),
                        side,
                        str(row.get("side_source") or "exchange"),
                        float(row.get("received_at") or time.time()),
                        SCHEMA_VERSION,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not prepared:
            return 0
        before = self.conn.total_changes
        self.conn.executemany(
            """INSERT OR IGNORE INTO research_market_trade_flow_mx(
                   exchange,market,sequential_id,trade_ts,trade_price,trade_volume,
                   quote_volume,aggressor_side,side_source,received_at,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            prepared,
        )
        self.conn.commit()
        return max(0, self.conn.total_changes - before)

    def prune_trades(self, exchange: str, market: str) -> int:
        before = self.conn.total_changes
        self.conn.execute(
            """DELETE FROM research_market_trade_flow_mx
               WHERE rowid IN (
                   SELECT rowid FROM research_market_trade_flow_mx
                   WHERE exchange=? AND market=?
                   ORDER BY trade_ts DESC,sequential_id DESC
                   LIMIT -1 OFFSET ?
               )""",
            (str(exchange), str(market), self.trade_retention),
        )
        self.conn.commit()
        return max(0, self.conn.total_changes - before)

    def trade_stats(self, exchange: str, market: str, *, start_ts: float, end_ts: float) -> dict[str, Any]:
        row = self.conn.execute(
            """SELECT COUNT(*) AS trade_count,
                      SUM(CASE WHEN aggressor_side='BID' THEN trade_volume ELSE 0 END) AS buy_volume,
                      SUM(CASE WHEN aggressor_side='ASK' THEN trade_volume ELSE 0 END) AS sell_volume,
                      SUM(CASE WHEN aggressor_side='BID' THEN quote_volume ELSE 0 END) AS buy_quote_volume,
                      SUM(CASE WHEN aggressor_side='ASK' THEN quote_volume ELSE 0 END) AS sell_quote_volume,
                      SUM(CASE WHEN aggressor_side IN ('BID','ASK') THEN 1 ELSE 0 END) AS side_rows
               FROM research_market_trade_flow_mx
               WHERE exchange=? AND market=? AND trade_ts>=? AND trade_ts<=?""",
            (str(exchange), str(market), float(start_ts), float(end_ts)),
        ).fetchone()
        count = int(row["trade_count"] or 0) if row else 0
        buy_volume = float(row["buy_volume"] or 0.0) if row else 0.0
        sell_volume = float(row["sell_volume"] or 0.0) if row else 0.0
        buy_quote = float(row["buy_quote_volume"] or 0.0) if row else 0.0
        sell_quote = float(row["sell_quote_volume"] or 0.0) if row else 0.0
        side_rows = int(row["side_rows"] or 0) if row else 0
        total_quote = buy_quote + sell_quote
        return {
            "trade_count": count,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "buy_quote_volume": buy_quote,
            "sell_quote_volume": sell_quote,
            "delta_volume": buy_volume - sell_volume,
            "delta_quote": buy_quote - sell_quote,
            "delta_pct": ((buy_quote - sell_quote) / total_quote * 100.0) if total_quote > 0 else None,
            "side_coverage_pct": (side_rows / count * 100.0) if count > 0 else None,
        }

    def observed_cvd_quote(self, exchange: str, market: str, *, anchor_ts: float, end_ts: float) -> float:
        row = self.conn.execute(
            """SELECT SUM(CASE WHEN aggressor_side='BID' THEN quote_volume ELSE -quote_volume END) AS cvd
               FROM research_market_trade_flow_mx
               WHERE exchange=? AND market=? AND trade_ts>=? AND trade_ts<=?""",
            (str(exchange), str(market), float(anchor_ts), float(end_ts)),
        ).fetchone()
        return float(row["cvd"] or 0.0) if row else 0.0

    def insert_orderbook(self, row: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO research_market_orderbook_flow_mx(
                   exchange,market,snapshot_ts,source_ts,best_bid,best_ask,spread_bps,
                   bid_depth_quote_5,ask_depth_quote_5,imbalance_5,
                   bid_depth_quote_all,ask_depth_quote_all,imbalance_all,received_at,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(row["exchange"]),
                str(row["market"]),
                float(row["snapshot_ts"]),
                float(row.get("source_ts") or 0.0),
                row.get("best_bid"),
                row.get("best_ask"),
                row.get("spread_bps"),
                float(row.get("bid_depth_quote_5") or 0.0),
                float(row.get("ask_depth_quote_5") or 0.0),
                row.get("imbalance_5"),
                float(row.get("bid_depth_quote_all") or 0.0),
                float(row.get("ask_depth_quote_all") or 0.0),
                row.get("imbalance_all"),
                float(row.get("received_at") or time.time()),
                SCHEMA_VERSION,
            ),
        )
        self.conn.commit()
        self._prune_history(
            "research_market_orderbook_flow_mx",
            str(row["exchange"]),
            str(row["market"]),
            "snapshot_ts",
            self.book_retention,
        )

    def insert_feature(self, row: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO research_market_flow_feature_mx(
                   exchange,market,feature_ts,window_seconds,window_start_ts,window_end_ts,
                   trade_count,buy_volume,sell_volume,buy_quote_volume,sell_quote_volume,
                   delta_volume,delta_quote,delta_pct,observed_cvd_quote,cvd_anchor_ts,
                   continuity_complete,side_coverage_pct,spread_bps,imbalance_5,imbalance_all,
                   source,received_at,feature_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(row["exchange"]),
                str(row["market"]),
                float(row["feature_ts"]),
                float(row.get("window_seconds") or 0.0),
                float(row.get("window_start_ts") or 0.0),
                float(row.get("window_end_ts") or 0.0),
                int(row.get("trade_count") or 0),
                float(row.get("buy_volume") or 0.0),
                float(row.get("sell_volume") or 0.0),
                float(row.get("buy_quote_volume") or 0.0),
                float(row.get("sell_quote_volume") or 0.0),
                float(row.get("delta_volume") or 0.0),
                float(row.get("delta_quote") or 0.0),
                row.get("delta_pct"),
                float(row.get("observed_cvd_quote") or 0.0),
                float(row.get("cvd_anchor_ts") or 0.0),
                1 if bool(row.get("continuity_complete")) else 0,
                row.get("side_coverage_pct"),
                row.get("spread_bps"),
                row.get("imbalance_5"),
                row.get("imbalance_all"),
                str(row.get("source") or "public_rest"),
                float(row.get("received_at") or time.time()),
                int(row.get("feature_version") or 1),
            ),
        )
        self.conn.commit()
        self._prune_history(
            "research_market_flow_feature_mx",
            str(row["exchange"]),
            str(row["market"]),
            "feature_ts",
            self.feature_retention,
        )

    def _prune_history(self, table: str, exchange: str, market: str, ts_column: str, keep: int) -> None:
        if table not in {"research_market_orderbook_flow_mx", "research_market_flow_feature_mx"}:
            raise ValueError("unsupported table")
        if ts_column not in {"snapshot_ts", "feature_ts"}:
            raise ValueError("unsupported timestamp column")
        self.conn.execute(
            f"""DELETE FROM {table}
                WHERE rowid IN (
                    SELECT rowid FROM {table}
                    WHERE exchange=? AND market=?
                    ORDER BY {ts_column} DESC
                    LIMIT -1 OFFSET ?
                )""",
            (str(exchange), str(market), max(1, int(keep))),
        )
        self.conn.commit()

    def audit(self) -> dict[str, Any]:
        trades = int(self.conn.execute("SELECT COUNT(*) FROM research_market_trade_flow_mx").fetchone()[0])
        books = int(self.conn.execute("SELECT COUNT(*) FROM research_market_orderbook_flow_mx").fetchone()[0])
        features = int(self.conn.execute("SELECT COUNT(*) FROM research_market_flow_feature_mx").fetchone()[0])
        cursors = self.conn.execute(
            """SELECT exchange,COUNT(*) AS markets,
                      SUM(last_cycle_complete) AS complete_markets,
                      MAX(updated_at) AS updated_at
               FROM research_market_flow_cursor_mx GROUP BY exchange ORDER BY exchange"""
        ).fetchall()
        latest = self.conn.execute(
            """SELECT exchange,market,feature_ts,trade_count,delta_quote,delta_pct,
                      observed_cvd_quote,cvd_anchor_ts,continuity_complete,
                      side_coverage_pct,spread_bps,imbalance_5,imbalance_all
               FROM research_market_flow_feature_mx
               WHERE (exchange,market,feature_ts) IN (
                   SELECT exchange,market,MAX(feature_ts)
                   FROM research_market_flow_feature_mx GROUP BY exchange,market
               ) ORDER BY exchange,market LIMIT 20"""
        ).fetchall()
        return {
            "schema_version": SCHEMA_VERSION,
            "trade_rows": trades,
            "orderbook_rows": books,
            "feature_rows": features,
            "exchanges": {
                str(row["exchange"]): {
                    "markets": int(row["markets"] or 0),
                    "last_cycle_complete_markets": int(row["complete_markets"] or 0),
                    "updated_at": float(row["updated_at"] or 0.0),
                }
                for row in cursors
            },
            "latest_samples": [dict(row) for row in latest],
        }
