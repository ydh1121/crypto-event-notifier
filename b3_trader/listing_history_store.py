from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from .listing_history import ListingCandle
from .listing_identity import ListingIdentity


DEFAULT_DB_PATH = Path("b3_trader/data/auto_demo.sqlite3")


class ListingHistoryStore:
    """Additive local SQLite store for pre/post domestic-listing research."""

    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=20)
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def _columns(self, table: str) -> set[str]:
        return {str(row[1]) for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS listing_history_cases (
              case_key TEXT PRIMARY KEY,
              domestic_exchange TEXT NOT NULL,
              domestic_market TEXT NOT NULL,
              domestic_notice_id TEXT NOT NULL DEFAULT '',
              symbol TEXT NOT NULL,
              announcement_at REAL NOT NULL DEFAULT 0,
              domestic_open_at REAL NOT NULL DEFAULT 0,
              domestic_open_price REAL NOT NULL DEFAULT 0,
              identity_json TEXT NOT NULL DEFAULT '{}',
              identity_verified INTEGER NOT NULL DEFAULT 0,
              identity_confidence REAL NOT NULL DEFAULT 0,
              status TEXT NOT NULL DEFAULT 'pending_identity',
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_listing_history_cases_status
              ON listing_history_cases(status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_listing_history_cases_market
              ON listing_history_cases(domestic_exchange, domestic_market, domestic_open_at DESC);

            CREATE TABLE IF NOT EXISTS listing_history_sources (
              case_key TEXT NOT NULL,
              source_exchange TEXT NOT NULL,
              source_market TEXT NOT NULL,
              base_asset TEXT NOT NULL DEFAULT '',
              quote_asset TEXT NOT NULL DEFAULT '',
              source_listing_at REAL NOT NULL DEFAULT 0,
              first_price REAL NOT NULL DEFAULT 0,
              match_confidence REAL NOT NULL DEFAULT 0,
              match_basis_json TEXT NOT NULL DEFAULT '{}',
              updated_at REAL NOT NULL,
              PRIMARY KEY(case_key, source_exchange, source_market),
              FOREIGN KEY(case_key) REFERENCES listing_history_cases(case_key) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS listing_history_candles (
              case_key TEXT NOT NULL,
              source_exchange TEXT NOT NULL,
              source_market TEXT NOT NULL,
              candle_ts REAL NOT NULL,
              interval_seconds INTEGER NOT NULL,
              open REAL NOT NULL,
              high REAL NOT NULL,
              low REAL NOT NULL,
              close REAL NOT NULL,
              volume REAL NOT NULL DEFAULT 0,
              quote_volume REAL NOT NULL DEFAULT 0,
              confirmed INTEGER NOT NULL DEFAULT 1,
              PRIMARY KEY(case_key, source_exchange, source_market, candle_ts, interval_seconds),
              FOREIGN KEY(case_key) REFERENCES listing_history_cases(case_key) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_listing_history_candles_case_time
              ON listing_history_candles(case_key, source_exchange, source_market, candle_ts);

            CREATE TABLE IF NOT EXISTS listing_history_features (
              case_key TEXT NOT NULL,
              source_exchange TEXT NOT NULL,
              source_market TEXT NOT NULL,
              feature_version INTEGER NOT NULL DEFAULT 1,
              calculated_at REAL NOT NULL,
              feature_json TEXT NOT NULL DEFAULT '{}',
              PRIMARY KEY(case_key, source_exchange, source_market),
              FOREIGN KEY(case_key) REFERENCES listing_history_cases(case_key) ON DELETE CASCADE
            );
            """
        )
        existing = self._columns("listing_history_cases")
        if "domestic_notice_id" not in existing:
            self.conn.execute(
                "ALTER TABLE listing_history_cases ADD COLUMN domestic_notice_id TEXT NOT NULL DEFAULT ''"
            )
        self.conn.commit()

    @staticmethod
    def case_key(
        domestic_exchange: str,
        domestic_market: str,
        *,
        domestic_notice_id: str = "",
        announcement_at: float = 0.0,
        domestic_open_at: float = 0.0,
    ) -> str:
        exchange = str(domestic_exchange or "").strip().lower()
        market = str(domestic_market or "").strip().upper()
        stable_notice = str(domestic_notice_id or "").strip()
        if stable_notice:
            suffix = f"notice:{stable_notice}"
        else:
            stamp = int(float(announcement_at or domestic_open_at or 0))
            suffix = f"event:{stamp}"
        return f"{exchange}|{market}|{suffix}"

    def upsert_case(
        self,
        *,
        domestic_exchange: str,
        domestic_market: str,
        symbol: str,
        domestic_notice_id: str = "",
        announcement_at: float = 0.0,
        domestic_open_at: float = 0.0,
        domestic_open_price: float = 0.0,
        identity: ListingIdentity | None = None,
        identity_verified: bool = False,
        status: str = "pending_identity",
    ) -> str:
        now = time.time()
        key = self.case_key(
            domestic_exchange,
            domestic_market,
            domestic_notice_id=domestic_notice_id,
            announcement_at=announcement_at,
            domestic_open_at=domestic_open_at,
        )
        identity_json = json.dumps(identity.to_dict() if identity else {}, ensure_ascii=False, separators=(",", ":"))
        confidence = float(identity.match_confidence if identity else 0.0)
        self.conn.execute(
            """
            INSERT INTO listing_history_cases(
              case_key,domestic_exchange,domestic_market,domestic_notice_id,symbol,announcement_at,domestic_open_at,
              domestic_open_price,identity_json,identity_verified,identity_confidence,status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(case_key) DO UPDATE SET
              domestic_notice_id=CASE WHEN excluded.domestic_notice_id<>'' THEN excluded.domestic_notice_id ELSE listing_history_cases.domestic_notice_id END,
              symbol=excluded.symbol,
              announcement_at=CASE WHEN excluded.announcement_at>0 THEN excluded.announcement_at ELSE listing_history_cases.announcement_at END,
              domestic_open_at=CASE WHEN excluded.domestic_open_at>0 THEN excluded.domestic_open_at ELSE listing_history_cases.domestic_open_at END,
              domestic_open_price=CASE WHEN excluded.domestic_open_price>0 THEN excluded.domestic_open_price ELSE listing_history_cases.domestic_open_price END,
              identity_json=CASE WHEN excluded.identity_json<>'{}' THEN excluded.identity_json ELSE listing_history_cases.identity_json END,
              identity_verified=MAX(listing_history_cases.identity_verified, excluded.identity_verified),
              identity_confidence=MAX(listing_history_cases.identity_confidence, excluded.identity_confidence),
              status=CASE
                WHEN excluded.status='pending_identity' AND listing_history_cases.status<>'pending_identity'
                  THEN listing_history_cases.status
                ELSE excluded.status
              END,
              updated_at=excluded.updated_at
            """,
            (
                key,
                str(domestic_exchange or "").lower(),
                str(domestic_market or "").upper(),
                str(domestic_notice_id or ""),
                str(symbol or "").upper(),
                float(announcement_at or 0),
                float(domestic_open_at or 0),
                float(domestic_open_price or 0),
                identity_json,
                1 if identity_verified else 0,
                confidence,
                str(status or "pending_identity"),
                now,
                now,
            ),
        )
        self.conn.commit()
        return key

    def update_case_status(self, case_key: str, status: str) -> None:
        self.conn.execute(
            "UPDATE listing_history_cases SET status=?,updated_at=? WHERE case_key=?",
            (str(status), time.time(), case_key),
        )
        self.conn.commit()

    def upsert_source(
        self,
        *,
        case_key: str,
        source_exchange: str,
        source_market: str,
        base_asset: str,
        quote_asset: str,
        source_listing_at: float = 0.0,
        first_price: float = 0.0,
        match_confidence: float = 0.0,
        match_basis: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO listing_history_sources(
              case_key,source_exchange,source_market,base_asset,quote_asset,source_listing_at,
              first_price,match_confidence,match_basis_json,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(case_key,source_exchange,source_market) DO UPDATE SET
              source_listing_at=CASE WHEN excluded.source_listing_at>0 THEN excluded.source_listing_at ELSE listing_history_sources.source_listing_at END,
              first_price=CASE WHEN excluded.first_price>0 THEN excluded.first_price ELSE listing_history_sources.first_price END,
              match_confidence=MAX(listing_history_sources.match_confidence, excluded.match_confidence),
              match_basis_json=excluded.match_basis_json,
              updated_at=excluded.updated_at
            """,
            (
                case_key,
                str(source_exchange or "").lower(),
                str(source_market or "").upper(),
                str(base_asset or "").upper(),
                str(quote_asset or "").upper(),
                float(source_listing_at or 0),
                float(first_price or 0),
                float(match_confidence or 0),
                json.dumps(match_basis or {}, ensure_ascii=False, separators=(",", ":")),
                time.time(),
            ),
        )
        self.conn.commit()

    def upsert_candles(
        self,
        *,
        case_key: str,
        source_exchange: str,
        source_market: str,
        candles: Iterable[ListingCandle],
    ) -> int:
        rows = [
            (
                case_key,
                str(source_exchange or "").lower(),
                str(source_market or "").upper(),
                float(row.ts),
                int(row.interval_seconds),
                float(row.open),
                float(row.high),
                float(row.low),
                float(row.close),
                float(row.volume),
                float(row.quote_volume),
                1 if row.confirmed else 0,
            )
            for row in candles
            if row.ts > 0 and row.close > 0
        ]
        if not rows:
            return 0
        self.conn.executemany(
            """
            INSERT INTO listing_history_candles(
              case_key,source_exchange,source_market,candle_ts,interval_seconds,open,high,low,close,volume,quote_volume,confirmed
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(case_key,source_exchange,source_market,candle_ts,interval_seconds) DO UPDATE SET
              open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,
              volume=excluded.volume,quote_volume=excluded.quote_volume,confirmed=excluded.confirmed
            """,
            rows,
        )
        self.conn.commit()
        return len(rows)

    def candles(
        self,
        *,
        case_key: str,
        source_exchange: str,
        source_market: str,
    ) -> list[ListingCandle]:
        rows = self.conn.execute(
            """
            SELECT candle_ts,interval_seconds,open,high,low,close,volume,quote_volume,confirmed
            FROM listing_history_candles
            WHERE case_key=? AND source_exchange=? AND source_market=?
            ORDER BY candle_ts
            """,
            (case_key, str(source_exchange).lower(), str(source_market).upper()),
        ).fetchall()
        return [
            ListingCandle(
                ts=float(row["candle_ts"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                quote_volume=float(row["quote_volume"]),
                interval_seconds=int(row["interval_seconds"]),
                confirmed=bool(row["confirmed"]),
            )
            for row in rows
        ]

    def upsert_features(
        self,
        *,
        case_key: str,
        source_exchange: str,
        source_market: str,
        features: dict[str, Any],
        feature_version: int = 1,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO listing_history_features(case_key,source_exchange,source_market,feature_version,calculated_at,feature_json)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(case_key,source_exchange,source_market) DO UPDATE SET
              feature_version=excluded.feature_version,
              calculated_at=excluded.calculated_at,
              feature_json=excluded.feature_json
            """,
            (
                case_key,
                str(source_exchange or "").lower(),
                str(source_market or "").upper(),
                int(feature_version),
                time.time(),
                json.dumps(features, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        self.conn.commit()

    def pending_cases(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM listing_history_cases
            WHERE status NOT IN ('complete','rejected_identity','rejected_notice')
            ORDER BY updated_at ASC LIMIT ?
            """,
            (max(1, min(500, int(limit))),),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["identity"] = json.loads(str(item.pop("identity_json") or "{}"))
            except json.JSONDecodeError:
                item["identity"] = {}
            result.append(item)
        return result
