from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 1
FEATURE_VERSION = 1
LADDER_LEVELS = 5
RETENTION_SECONDS = 3 * 24 * 60 * 60
MAX_PRIOR_AGE_SECONDS = 5.0


class MarketOrderbookLadderStore:
    """Bounded forward-only top-5 orderbook ladder snapshots.

    One snapshot is retained per exchange/market/minute: the latest public
    WebSocket book observed inside that minute. Consumers may only request the
    snapshot from the immediately preceding minute and the source timestamp must
    be strictly earlier than the requested minute boundary. This avoids
    look-ahead while keeping the local SQLite footprint bounded.
    """

    def __init__(self, path: Path | str = DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=10000")
        self._last_prune_bucket: dict[tuple[str, str], float] = {}
        self._ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_market_orderbook_ladder_meta_mx(
                id INTEGER PRIMARY KEY CHECK(id=1),
                collector_started_at REAL NOT NULL,
                first_received_at REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'public_websocket_orderbook_top5',
                received_at REAL NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS research_market_orderbook_ladder_minute_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                bucket_ts REAL NOT NULL,
                source_ts REAL NOT NULL,
                best_bid_price REAL NOT NULL,
                best_ask_price REAL NOT NULL,
                bid_levels_json TEXT NOT NULL,
                ask_levels_json TEXT NOT NULL,
                received_at REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'public_websocket_orderbook_top5',
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,bucket_ts)
            );
            CREATE INDEX IF NOT EXISTS idx_market_orderbook_ladder_source_time
            ON research_market_orderbook_ladder_minute_mx(exchange,market,source_ts DESC);
            """
        )
        self.conn.commit()

    @staticmethod
    def _minute_bucket(ts: float) -> float:
        return float(math.floor(float(ts) / 60.0) * 60)

    @staticmethod
    def _normalize_levels(value: Any, *, side: str) -> list[dict[str, float]] | None:
        if not isinstance(value, list) or not value:
            return None
        levels: list[dict[str, float]] = []
        for raw in value[:LADDER_LEVELS]:
            if not isinstance(raw, dict):
                return None
            try:
                price = float(raw.get("price") or 0.0)
                size = float(raw.get("size") or 0.0)
            except (TypeError, ValueError):
                return None
            if price <= 0 or size < 0 or not math.isfinite(price) or not math.isfinite(size):
                return None
            levels.append({"price": price, "size": size})
        if not levels:
            return None
        levels.sort(key=lambda row: row["price"], reverse=(side == "bid"))
        return levels

    def insert_snapshot(self, row: dict[str, Any], *, received_at: float | None = None) -> dict[str, Any]:
        now = float(received_at or row.get("received_at") or time.time())
        try:
            exchange = str(row["exchange"])
            market = str(row["market"])
            source_ts = float(row["source_ts"])
        except (KeyError, TypeError, ValueError):
            return {"accepted": False, "reason": "invalid_snapshot"}
        bids = self._normalize_levels(row.get("bid_levels"), side="bid")
        asks = self._normalize_levels(row.get("ask_levels"), side="ask")
        if not exchange or not market or source_ts <= 0 or bids is None or asks is None:
            return {"accepted": False, "reason": "invalid_snapshot"}
        best_bid = float(bids[0]["price"])
        best_ask = float(asks[0]["price"])
        if best_ask <= best_bid:
            return {"accepted": False, "reason": "crossed_book"}

        bucket = self._minute_bucket(source_ts)
        bid_json = json.dumps(bids, separators=(",", ":"), sort_keys=True)
        ask_json = json.dumps(asks, separators=(",", ":"), sort_keys=True)
        with self.conn:
            self.conn.execute(
                """INSERT OR IGNORE INTO research_market_orderbook_ladder_meta_mx(
                       id,collector_started_at,first_received_at,source,received_at,schema_version
                   ) VALUES(1,?,?, 'public_websocket_orderbook_top5',?,?)""",
                (source_ts, now, now, SCHEMA_VERSION),
            )
            cursor = self.conn.execute(
                """INSERT INTO research_market_orderbook_ladder_minute_mx(
                       exchange,market,bucket_ts,source_ts,best_bid_price,best_ask_price,
                       bid_levels_json,ask_levels_json,received_at,source,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,'public_websocket_orderbook_top5',?,?)
                   ON CONFLICT(exchange,market,bucket_ts) DO UPDATE SET
                       source_ts=excluded.source_ts,
                       best_bid_price=excluded.best_bid_price,
                       best_ask_price=excluded.best_ask_price,
                       bid_levels_json=excluded.bid_levels_json,
                       ask_levels_json=excluded.ask_levels_json,
                       received_at=excluded.received_at,
                       feature_version=excluded.feature_version,
                       schema_version=excluded.schema_version
                   WHERE excluded.source_ts>research_market_orderbook_ladder_minute_mx.source_ts""",
                (
                    exchange, market, bucket, source_ts, best_bid, best_ask,
                    bid_json, ask_json, now, FEATURE_VERSION, SCHEMA_VERSION,
                ),
            )
            key = (exchange, market)
            if self._last_prune_bucket.get(key) != bucket:
                cutoff = bucket - RETENTION_SECONDS
                self.conn.execute(
                    "DELETE FROM research_market_orderbook_ladder_minute_mx WHERE exchange=? AND market=? AND bucket_ts<?",
                    (exchange, market, cutoff),
                )
                self._last_prune_bucket[key] = bucket
        return {
            "accepted": True,
            "updated": bool(cursor.rowcount),
            "bucket_ts": bucket,
            "source_ts": source_ts,
            "levels": min(len(bids), len(asks)),
        }

    def collector_started_at(self) -> float | None:
        row = self.conn.execute(
            "SELECT collector_started_at FROM research_market_orderbook_ladder_meta_mx WHERE id=1"
        ).fetchone()
        return float(row[0]) if row else None

    def prior_snapshot(
        self,
        exchange: str,
        market: str,
        boundary_ts: float,
        *,
        max_age_seconds: float = MAX_PRIOR_AGE_SECONDS,
    ) -> dict[str, Any] | None:
        boundary = float(boundary_ts)
        if boundary <= 0 or abs(boundary - round(boundary / 60.0) * 60.0) > 0.000001:
            return None
        bucket = boundary - 60.0
        row = self.conn.execute(
            """SELECT * FROM research_market_orderbook_ladder_minute_mx
               WHERE exchange=? AND market=? AND bucket_ts=? AND source_ts<?
               LIMIT 1""",
            (str(exchange), str(market), bucket, boundary),
        ).fetchone()
        if not row:
            return None
        payload = dict(row)
        source_ts = float(payload["source_ts"])
        age = boundary - source_ts
        if age <= 0 or age > float(max_age_seconds):
            return None
        try:
            payload["bid_levels"] = json.loads(str(payload.pop("bid_levels_json")))
            payload["ask_levels"] = json.loads(str(payload.pop("ask_levels_json")))
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        payload["age_seconds"] = age
        return payload

    @staticmethod
    def spread_bps(snapshot: dict[str, Any]) -> float | None:
        try:
            bid = float(snapshot["best_bid_price"])
            ask = float(snapshot["best_ask_price"])
        except (KeyError, TypeError, ValueError):
            return None
        if bid <= 0 or ask <= bid:
            return None
        mid = (bid + ask) / 2.0
        return (ask - bid) / mid * 10_000.0 if mid > 0 else None

    @staticmethod
    def estimate_buy(levels: list[dict[str, Any]], quote_notional: float) -> dict[str, float] | None:
        target = float(quote_notional)
        if target <= 0 or not levels:
            return None
        remaining = target
        base_acquired = 0.0
        quote_spent = 0.0
        best = float(levels[0].get("price") or 0.0)
        if best <= 0:
            return None
        for level in levels:
            price = float(level.get("price") or 0.0)
            size = float(level.get("size") or 0.0)
            if price <= 0 or size < 0:
                return None
            available_quote = price * size
            take_quote = min(remaining, available_quote)
            if take_quote > 0:
                base_acquired += take_quote / price
                quote_spent += take_quote
                remaining -= take_quote
            if remaining <= 0.000001:
                break
        if remaining > max(0.000001, target * 1e-9) or base_acquired <= 0:
            return None
        vwap = quote_spent / base_acquired
        slippage_bps = max(0.0, (vwap / best - 1.0) * 10_000.0)
        return {"vwap": vwap, "slippage_bps": slippage_bps, "quote_notional": quote_spent}

    @staticmethod
    def estimate_sell(levels: list[dict[str, Any]], quote_notional: float) -> dict[str, float] | None:
        target_quote = float(quote_notional)
        if target_quote <= 0 or not levels:
            return None
        best = float(levels[0].get("price") or 0.0)
        if best <= 0:
            return None
        target_base = target_quote / best
        remaining_base = target_base
        sold_base = 0.0
        quote_received = 0.0
        for level in levels:
            price = float(level.get("price") or 0.0)
            size = float(level.get("size") or 0.0)
            if price <= 0 or size < 0:
                return None
            take_base = min(remaining_base, size)
            if take_base > 0:
                sold_base += take_base
                quote_received += take_base * price
                remaining_base -= take_base
            if remaining_base <= 0.000000000001:
                break
        if remaining_base > max(0.000000000001, target_base * 1e-9) or sold_base <= 0:
            return None
        vwap = quote_received / sold_base
        slippage_bps = max(0.0, (1.0 - vwap / best) * 10_000.0)
        return {"vwap": vwap, "slippage_bps": slippage_bps, "quote_notional": quote_received}

    def audit(self) -> dict[str, Any]:
        tables = {
            str(row[0])
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        required = {
            "research_market_orderbook_ladder_meta_mx",
            "research_market_orderbook_ladder_minute_mx",
        }
        if not required.issubset(tables):
            return {"ok": False, "status": "tables_missing", "tables_ready": False}
        row_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_orderbook_ladder_minute_mx"
        ).fetchone()[0])
        crossed = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_orderbook_ladder_minute_mx WHERE best_ask_price<=best_bid_price"
        ).fetchone()[0])
        invalid_level_json = 0
        samples = self.conn.execute(
            "SELECT bid_levels_json,ask_levels_json FROM research_market_orderbook_ladder_minute_mx ORDER BY source_ts DESC LIMIT 200"
        ).fetchall()
        for row in samples:
            try:
                bids = json.loads(str(row[0]))
                asks = json.loads(str(row[1]))
                if not bids or not asks or len(bids) > LADDER_LEVELS or len(asks) > LADDER_LEVELS:
                    invalid_level_json += 1
            except (json.JSONDecodeError, TypeError, ValueError):
                invalid_level_json += 1
        latest = [
            dict(row)
            for row in self.conn.execute(
                """SELECT exchange,market,MAX(bucket_ts) AS bucket_ts,MAX(source_ts) AS source_ts
                   FROM research_market_orderbook_ladder_minute_mx
                   GROUP BY exchange,market ORDER BY exchange,market"""
            ).fetchall()
        ]
        return {
            "ok": crossed == 0 and invalid_level_json == 0,
            "status": "ready",
            "tables_ready": True,
            "row_count": row_count,
            "collector_started_at": self.collector_started_at(),
            "latest": latest,
            "crossed_book_violations": crossed,
            "invalid_level_json_violations": invalid_level_json,
            "ladder_levels": LADDER_LEVELS,
            "retention_seconds": RETENTION_SECONDS,
            "max_prior_age_seconds": MAX_PRIOR_AGE_SECONDS,
            "prior_only_minute_boundary": True,
            "historical_backfill": False,
            "raw_cloud_projection": False,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
