from __future__ import annotations

import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 1
SAMPLE_INTERVAL_SECONDS = 1.0
MAX_PAIR_GAP_SECONDS = 5.0
MIN_REPLENISHMENT_PAIRS = 5
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


class MarketFlowOrderbookStreamStore:
    """Bounded local orderbook sampling and replenishment-proxy feature store.

    This store intentionally does not attempt to reconstruct individual orders.
    Replenishment is measured only across consecutive sampled books where the
    corresponding best price is unchanged. That prevents a best-price move from
    being mislabeled as refill/depletion at the old price.
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
            CREATE TABLE IF NOT EXISTS research_market_orderbook_stream_state_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                source_ts REAL NOT NULL,
                best_bid_price REAL NOT NULL,
                best_ask_price REAL NOT NULL,
                bid_depth_top5_quote REAL NOT NULL,
                ask_depth_top5_quote REAL NOT NULL,
                spread_bps REAL NOT NULL,
                imbalance_pct REAL NOT NULL,
                received_at REAL NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market)
            );

            CREATE TABLE IF NOT EXISTS research_market_orderbook_stream_minute_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                bucket_ts REAL NOT NULL,
                snapshot_count INTEGER NOT NULL DEFAULT 0,
                spread_bps_sum REAL NOT NULL DEFAULT 0,
                spread_bps_max REAL NOT NULL DEFAULT 0,
                bid_depth_quote_sum REAL NOT NULL DEFAULT 0,
                ask_depth_quote_sum REAL NOT NULL DEFAULT 0,
                imbalance_pct_sum REAL NOT NULL DEFAULT 0,
                bid_refill_quote REAL NOT NULL DEFAULT 0,
                bid_depletion_quote REAL NOT NULL DEFAULT 0,
                ask_refill_quote REAL NOT NULL DEFAULT 0,
                ask_depletion_quote REAL NOT NULL DEFAULT 0,
                bid_same_best_pairs INTEGER NOT NULL DEFAULT 0,
                ask_same_best_pairs INTEGER NOT NULL DEFAULT 0,
                first_source_ts REAL NOT NULL DEFAULT 0,
                last_source_ts REAL NOT NULL DEFAULT 0,
                received_at REAL NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,bucket_ts)
            );
            CREATE INDEX IF NOT EXISTS idx_market_orderbook_stream_minute_time
            ON research_market_orderbook_stream_minute_mx(exchange,market,bucket_ts DESC);

            CREATE TABLE IF NOT EXISTS research_market_orderbook_window_feature_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                window_label TEXT NOT NULL,
                window_seconds REAL NOT NULL,
                feature_ts REAL NOT NULL,
                window_start_ts REAL NOT NULL,
                window_end_ts REAL NOT NULL,
                snapshot_count INTEGER NOT NULL DEFAULT 0,
                spread_bps_avg REAL,
                spread_bps_max REAL,
                bid_depth_quote_avg REAL,
                ask_depth_quote_avg REAL,
                imbalance_pct_avg REAL,
                bid_refill_quote REAL NOT NULL DEFAULT 0,
                bid_depletion_quote REAL NOT NULL DEFAULT 0,
                ask_refill_quote REAL NOT NULL DEFAULT 0,
                ask_depletion_quote REAL NOT NULL DEFAULT 0,
                bid_same_best_pairs INTEGER NOT NULL DEFAULT 0,
                ask_same_best_pairs INTEGER NOT NULL DEFAULT 0,
                bid_replenishment_ratio REAL,
                ask_replenishment_ratio REAL,
                bid_refill_quote_per_second REAL,
                ask_refill_quote_per_second REAL,
                continuity_complete INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'public_websocket_orderbook',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,window_label,feature_ts)
            );
            CREATE INDEX IF NOT EXISTS idx_market_orderbook_window_feature_time
            ON research_market_orderbook_window_feature_mx(exchange,market,window_label,feature_ts DESC);
            """
        )
        self.conn.commit()

    @staticmethod
    def _minute_bucket(ts: float) -> float:
        return float(math.floor(float(ts) / 60.0) * 60)

    def insert_snapshot(self, row: dict[str, Any], *, received_at: float | None = None) -> dict[str, Any]:
        now = float(received_at or row.get("received_at") or time.time())
        try:
            exchange = str(row["exchange"])
            market = str(row["market"])
            source_ts = float(row["source_ts"])
            best_bid = float(row["best_bid_price"])
            best_ask = float(row["best_ask_price"])
            bid_depth = float(row["bid_depth_top5_quote"])
            ask_depth = float(row["ask_depth_top5_quote"])
            spread_bps = float(row["spread_bps"])
            imbalance_pct = float(row["imbalance_pct"])
        except (KeyError, TypeError, ValueError):
            return {"accepted": False, "reason": "invalid_snapshot"}
        if (
            not exchange
            or not market
            or source_ts <= 0
            or best_bid <= 0
            or best_ask <= best_bid
            or bid_depth < 0
            or ask_depth < 0
            or spread_bps < 0
            or not math.isfinite(imbalance_pct)
        ):
            return {"accepted": False, "reason": "invalid_snapshot"}

        previous_row = self.conn.execute(
            "SELECT * FROM research_market_orderbook_stream_state_mx WHERE exchange=? AND market=?",
            (exchange, market),
        ).fetchone()
        previous = dict(previous_row) if previous_row else None
        if previous is not None:
            previous_received = float(previous.get("received_at") or 0.0)
            previous_source = float(previous.get("source_ts") or 0.0)
            if source_ts <= previous_source:
                return {"accepted": False, "reason": "non_monotonic_source_ts"}
            if now - previous_received < SAMPLE_INTERVAL_SECONDS:
                return {"accepted": False, "reason": "sample_interval"}

        bid_refill = 0.0
        bid_depletion = 0.0
        ask_refill = 0.0
        ask_depletion = 0.0
        bid_same_best_pairs = 0
        ask_same_best_pairs = 0
        if previous is not None:
            previous_received = float(previous.get("received_at") or 0.0)
            pair_gap = now - previous_received
            if 0 < pair_gap <= MAX_PAIR_GAP_SECONDS:
                previous_bid = float(previous.get("best_bid_price") or 0.0)
                previous_ask = float(previous.get("best_ask_price") or 0.0)
                previous_bid_depth = float(previous.get("bid_depth_top5_quote") or 0.0)
                previous_ask_depth = float(previous.get("ask_depth_top5_quote") or 0.0)
                if previous_bid == best_bid:
                    bid_same_best_pairs = 1
                    bid_delta = bid_depth - previous_bid_depth
                    if bid_delta >= 0:
                        bid_refill = bid_delta
                    else:
                        bid_depletion = -bid_delta
                if previous_ask == best_ask:
                    ask_same_best_pairs = 1
                    ask_delta = ask_depth - previous_ask_depth
                    if ask_delta >= 0:
                        ask_refill = ask_delta
                    else:
                        ask_depletion = -ask_delta

        bucket = self._minute_bucket(source_ts)
        with self.conn:
            self.conn.execute(
                """INSERT INTO research_market_orderbook_stream_state_mx(
                       exchange,market,source_ts,best_bid_price,best_ask_price,
                       bid_depth_top5_quote,ask_depth_top5_quote,spread_bps,
                       imbalance_pct,received_at,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(exchange,market) DO UPDATE SET
                       source_ts=excluded.source_ts,
                       best_bid_price=excluded.best_bid_price,
                       best_ask_price=excluded.best_ask_price,
                       bid_depth_top5_quote=excluded.bid_depth_top5_quote,
                       ask_depth_top5_quote=excluded.ask_depth_top5_quote,
                       spread_bps=excluded.spread_bps,
                       imbalance_pct=excluded.imbalance_pct,
                       received_at=excluded.received_at,
                       schema_version=excluded.schema_version""",
                (
                    exchange,
                    market,
                    source_ts,
                    best_bid,
                    best_ask,
                    bid_depth,
                    ask_depth,
                    spread_bps,
                    imbalance_pct,
                    now,
                    SCHEMA_VERSION,
                ),
            )
            self.conn.execute(
                """INSERT INTO research_market_orderbook_stream_minute_mx(
                       exchange,market,bucket_ts,snapshot_count,spread_bps_sum,spread_bps_max,
                       bid_depth_quote_sum,ask_depth_quote_sum,imbalance_pct_sum,
                       bid_refill_quote,bid_depletion_quote,ask_refill_quote,ask_depletion_quote,
                       bid_same_best_pairs,ask_same_best_pairs,first_source_ts,last_source_ts,
                       received_at,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(exchange,market,bucket_ts) DO UPDATE SET
                       snapshot_count=snapshot_count+1,
                       spread_bps_sum=spread_bps_sum+excluded.spread_bps_sum,
                       spread_bps_max=MAX(spread_bps_max,excluded.spread_bps_max),
                       bid_depth_quote_sum=bid_depth_quote_sum+excluded.bid_depth_quote_sum,
                       ask_depth_quote_sum=ask_depth_quote_sum+excluded.ask_depth_quote_sum,
                       imbalance_pct_sum=imbalance_pct_sum+excluded.imbalance_pct_sum,
                       bid_refill_quote=bid_refill_quote+excluded.bid_refill_quote,
                       bid_depletion_quote=bid_depletion_quote+excluded.bid_depletion_quote,
                       ask_refill_quote=ask_refill_quote+excluded.ask_refill_quote,
                       ask_depletion_quote=ask_depletion_quote+excluded.ask_depletion_quote,
                       bid_same_best_pairs=bid_same_best_pairs+excluded.bid_same_best_pairs,
                       ask_same_best_pairs=ask_same_best_pairs+excluded.ask_same_best_pairs,
                       first_source_ts=CASE
                           WHEN first_source_ts<=0 THEN excluded.first_source_ts
                           ELSE MIN(first_source_ts,excluded.first_source_ts)
                       END,
                       last_source_ts=MAX(last_source_ts,excluded.last_source_ts),
                       received_at=excluded.received_at""",
                (
                    exchange,
                    market,
                    bucket,
                    1,
                    spread_bps,
                    spread_bps,
                    bid_depth,
                    ask_depth,
                    imbalance_pct,
                    bid_refill,
                    bid_depletion,
                    ask_refill,
                    ask_depletion,
                    bid_same_best_pairs,
                    ask_same_best_pairs,
                    source_ts,
                    source_ts,
                    now,
                    SCHEMA_VERSION,
                ),
            )
        return {
            "accepted": True,
            "reason": "sampled",
            "bid_refill_quote": bid_refill,
            "bid_depletion_quote": bid_depletion,
            "ask_refill_quote": ask_refill,
            "ask_depletion_quote": ask_depletion,
            "bid_same_best_pair": bool(bid_same_best_pairs),
            "ask_same_best_pair": bool(ask_same_best_pairs),
        }

    def _prune_window(self, exchange: str, market: str, label: str) -> None:
        self.conn.execute(
            """DELETE FROM research_market_orderbook_window_feature_mx
               WHERE rowid IN (
                   SELECT rowid FROM research_market_orderbook_window_feature_mx
                   WHERE exchange=? AND market=? AND window_label=?
                   ORDER BY feature_ts DESC
                   LIMIT -1 OFFSET ?
               )""",
            (exchange, market, label, WINDOW_FEATURE_RETENTION),
        )

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
                for label, seconds in WINDOWS:
                    start_ts = feature_ts - float(seconds)
                    row = self.conn.execute(
                        """SELECT SUM(snapshot_count) AS snapshot_count,
                                  SUM(spread_bps_sum) AS spread_bps_sum,
                                  MAX(spread_bps_max) AS spread_bps_max,
                                  SUM(bid_depth_quote_sum) AS bid_depth_quote_sum,
                                  SUM(ask_depth_quote_sum) AS ask_depth_quote_sum,
                                  SUM(imbalance_pct_sum) AS imbalance_pct_sum,
                                  SUM(bid_refill_quote) AS bid_refill_quote,
                                  SUM(bid_depletion_quote) AS bid_depletion_quote,
                                  SUM(ask_refill_quote) AS ask_refill_quote,
                                  SUM(ask_depletion_quote) AS ask_depletion_quote,
                                  SUM(bid_same_best_pairs) AS bid_same_best_pairs,
                                  SUM(ask_same_best_pairs) AS ask_same_best_pairs
                           FROM research_market_orderbook_stream_minute_mx
                           WHERE exchange=? AND market=? AND bucket_ts>=? AND bucket_ts<?""",
                        (exchange, market, start_ts, feature_ts),
                    ).fetchone()
                    count = int(row["snapshot_count"] or 0) if row else 0
                    spread_sum = float(row["spread_bps_sum"] or 0.0) if row else 0.0
                    spread_max = float(row["spread_bps_max"] or 0.0) if row else 0.0
                    bid_depth_sum = float(row["bid_depth_quote_sum"] or 0.0) if row else 0.0
                    ask_depth_sum = float(row["ask_depth_quote_sum"] or 0.0) if row else 0.0
                    imbalance_sum = float(row["imbalance_pct_sum"] or 0.0) if row else 0.0
                    bid_refill = float(row["bid_refill_quote"] or 0.0) if row else 0.0
                    bid_depletion = float(row["bid_depletion_quote"] or 0.0) if row else 0.0
                    ask_refill = float(row["ask_refill_quote"] or 0.0) if row else 0.0
                    ask_depletion = float(row["ask_depletion_quote"] or 0.0) if row else 0.0
                    bid_pairs = int(row["bid_same_best_pairs"] or 0) if row else 0
                    ask_pairs = int(row["ask_same_best_pairs"] or 0) if row else 0
                    continuity_complete = bool(connected and connected_since > 0 and connected_since <= start_ts)
                    bid_ratio = (
                        bid_refill / bid_depletion
                        if bid_pairs >= MIN_REPLENISHMENT_PAIRS and bid_depletion > 0
                        else None
                    )
                    ask_ratio = (
                        ask_refill / ask_depletion
                        if ask_pairs >= MIN_REPLENISHMENT_PAIRS and ask_depletion > 0
                        else None
                    )
                    self.conn.execute(
                        """INSERT OR REPLACE INTO research_market_orderbook_window_feature_mx(
                               exchange,market,window_label,window_seconds,feature_ts,
                               window_start_ts,window_end_ts,snapshot_count,spread_bps_avg,
                               spread_bps_max,bid_depth_quote_avg,ask_depth_quote_avg,
                               imbalance_pct_avg,bid_refill_quote,bid_depletion_quote,
                               ask_refill_quote,ask_depletion_quote,bid_same_best_pairs,
                               ask_same_best_pairs,bid_replenishment_ratio,ask_replenishment_ratio,
                               bid_refill_quote_per_second,ask_refill_quote_per_second,
                               continuity_complete,source,received_at,feature_version
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            exchange,
                            market,
                            label,
                            float(seconds),
                            feature_ts,
                            start_ts,
                            feature_ts,
                            count,
                            (spread_sum / count) if count > 0 else None,
                            spread_max if count > 0 else None,
                            (bid_depth_sum / count) if count > 0 else None,
                            (ask_depth_sum / count) if count > 0 else None,
                            (imbalance_sum / count) if count > 0 else None,
                            bid_refill,
                            bid_depletion,
                            ask_refill,
                            ask_depletion,
                            bid_pairs,
                            ask_pairs,
                            bid_ratio,
                            ask_ratio,
                            bid_refill / float(seconds),
                            ask_refill / float(seconds),
                            1 if continuity_complete else 0,
                            "public_websocket_orderbook",
                            current,
                            SCHEMA_VERSION,
                        ),
                    )
                    written += 1
                    self._prune_window(exchange, market, label)
                cutoff = feature_ts - MINUTE_RETENTION_SECONDS
                self.conn.execute(
                    "DELETE FROM research_market_orderbook_stream_minute_mx WHERE exchange=? AND market=? AND bucket_ts<?",
                    (exchange, market, cutoff),
                )
        return written

    def audit(self) -> dict[str, Any]:
        tables = {
            str(row[0])
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        required = {
            "research_market_orderbook_stream_state_mx",
            "research_market_orderbook_stream_minute_mx",
            "research_market_orderbook_window_feature_mx",
        }
        if not required.issubset(tables):
            return {"ok": False, "status": "tables_missing", "tables_ready": False}
        state_rows = [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM research_market_orderbook_stream_state_mx ORDER BY exchange,market"
            ).fetchall()
        ]
        minute_rows = int(
            self.conn.execute("SELECT COUNT(*) FROM research_market_orderbook_stream_minute_mx").fetchone()[0]
        )
        window_rows = int(
            self.conn.execute("SELECT COUNT(*) FROM research_market_orderbook_window_feature_mx").fetchone()[0]
        )
        latest_windows = [
            dict(row)
            for row in self.conn.execute(
                """SELECT f.* FROM research_market_orderbook_window_feature_mx f
                   JOIN (
                       SELECT exchange,market,window_label,MAX(feature_ts) AS max_ts
                       FROM research_market_orderbook_window_feature_mx
                       GROUP BY exchange,market,window_label
                   ) latest
                   ON latest.exchange=f.exchange
                  AND latest.market=f.market
                  AND latest.window_label=f.window_label
                  AND latest.max_ts=f.feature_ts
                   ORDER BY f.exchange,f.market,
                       CASE f.window_label
                           WHEN '1m' THEN 1 WHEN '5m' THEN 2 WHEN '15m' THEN 3
                           WHEN '1h' THEN 4 WHEN '4h' THEN 5 WHEN '1d' THEN 6 ELSE 99 END"""
            ).fetchall()
        ]
        return {
            "ok": True,
            "status": "ready",
            "tables_ready": True,
            "state_rows": state_rows,
            "minute_rows": minute_rows,
            "window_rows": window_rows,
            "latest_windows": latest_windows,
            "sample_interval_seconds": SAMPLE_INTERVAL_SECONDS,
            "max_pair_gap_seconds": MAX_PAIR_GAP_SECONDS,
            "min_replenishment_pairs": MIN_REPLENISHMENT_PAIRS,
            "windows": [label for label, _ in WINDOWS],
            "raw_orderbook_cloud_projection": False,
            "paper_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "schema_version": SCHEMA_VERSION,
        }
