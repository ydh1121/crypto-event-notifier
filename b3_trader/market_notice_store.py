from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from typing import Any, Iterable

from .market_notice import MarketNotice, lifecycle_state_for_notice

NOTICE_RETENTION_SECONDS = 400 * 86400


class MarketNoticeStore:
    """Normalized official notice persistence and latest per-market notice state."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._init_schema()

    def _columns(self, table: str) -> set[str]:
        return {str(row[1]) for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def _ensure_notice_timing_columns(self) -> None:
        existing = self._columns("market_notices")
        for name in ("announcement_at", "deposit_at", "trade_open_at", "termination_at"):
            if name not in existing:
                self.conn.execute(
                    f"ALTER TABLE market_notices ADD COLUMN {name} REAL NOT NULL DEFAULT 0"
                )

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS market_notices (
                exchange TEXT NOT NULL,
                notice_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                published_at REAL NOT NULL DEFAULT 0,
                event_kind TEXT NOT NULL,
                symbols_json TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL,
                first_seen_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                announcement_at REAL NOT NULL DEFAULT 0,
                deposit_at REAL NOT NULL DEFAULT 0,
                trade_open_at REAL NOT NULL DEFAULT 0,
                termination_at REAL NOT NULL DEFAULT 0,
                PRIMARY KEY(exchange, notice_id)
            );
            CREATE INDEX IF NOT EXISTS idx_market_notices_exchange_published
                ON market_notices(exchange, published_at DESC, notice_id);

            CREATE TABLE IF NOT EXISTS market_lifecycle_notice_state (
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                state TEXT NOT NULL,
                notice_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                source TEXT NOT NULL,
                effective_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY(exchange, market)
            );
            CREATE INDEX IF NOT EXISTS idx_market_lifecycle_notice_state_exchange
                ON market_lifecycle_notice_state(exchange, state, market);
            """
        )
        self._ensure_notice_timing_columns()
        self.conn.commit()

    @staticmethod
    def _effective_at(notice: MarketNotice) -> float:
        # Historical notices without an official publication timestamp are kept
        # for audit, but never allowed to become a current lifecycle override.
        return max(0.0, float(notice.announcement_at or notice.published_at or 0.0))

    def _apply_notice_state(self, notice: MarketNotice, *, seen_at: float) -> int:
        state = lifecycle_state_for_notice(notice.event_kind)
        effective_at = self._effective_at(notice)
        if not state or effective_at <= 0:
            return 0
        changed = 0
        for symbol in notice.symbols:
            market = f"KRW-{str(symbol or '').upper()}"
            existing = self.conn.execute(
                """SELECT effective_at,notice_id FROM market_lifecycle_notice_state
                   WHERE exchange=? AND market=?""",
                (notice.exchange, market),
            ).fetchone()
            existing_at = float(existing["effective_at"] or 0.0) if existing else 0.0
            existing_id = str(existing["notice_id"] or "") if existing else ""
            if existing and (effective_at < existing_at or (effective_at == existing_at and notice.notice_id <= existing_id)):
                continue
            self.conn.execute(
                """INSERT INTO market_lifecycle_notice_state(
                    exchange,market,state,notice_id,title,url,source,effective_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(exchange,market) DO UPDATE SET
                      state=excluded.state,notice_id=excluded.notice_id,title=excluded.title,
                      url=excluded.url,source=excluded.source,effective_at=excluded.effective_at,
                      updated_at=excluded.updated_at""",
                (
                    notice.exchange,
                    market,
                    state,
                    notice.notice_id,
                    notice.title,
                    notice.url,
                    notice.source,
                    effective_at,
                    seen_at,
                ),
            )
            changed += 1
        return changed

    def ingest(self, notices: Iterable[MarketNotice], *, seen_at: float | None = None) -> dict[str, Any]:
        now = float(seen_at or time.time())
        received = 0
        inserted = 0
        state_updates = 0
        by_kind: Counter[str] = Counter()
        for notice in notices:
            if not notice.exchange or not notice.notice_id or not notice.title:
                continue
            received += 1
            by_kind[notice.event_kind] += 1
            existing = self.conn.execute(
                "SELECT 1 FROM market_notices WHERE exchange=? AND notice_id=?",
                (notice.exchange, notice.notice_id),
            ).fetchone()
            self.conn.execute(
                """INSERT INTO market_notices(
                    exchange,notice_id,title,url,published_at,event_kind,symbols_json,source,
                    first_seen_at,updated_at,announcement_at,deposit_at,trade_open_at,termination_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(exchange,notice_id) DO UPDATE SET
                      title=excluded.title,url=excluded.url,published_at=excluded.published_at,
                      event_kind=excluded.event_kind,symbols_json=excluded.symbols_json,
                      source=excluded.source,updated_at=excluded.updated_at,
                      announcement_at=excluded.announcement_at,deposit_at=excluded.deposit_at,
                      trade_open_at=excluded.trade_open_at,termination_at=excluded.termination_at""",
                (
                    notice.exchange,
                    notice.notice_id,
                    notice.title,
                    notice.url,
                    float(notice.published_at or 0.0),
                    notice.event_kind,
                    json.dumps(list(notice.symbols), ensure_ascii=False, separators=(",", ":")),
                    notice.source,
                    now,
                    now,
                    float(notice.announcement_at or 0.0),
                    float(notice.deposit_at or 0.0),
                    float(notice.trade_open_at or 0.0),
                    float(notice.termination_at or 0.0),
                ),
            )
            if not existing:
                inserted += 1
            state_updates += self._apply_notice_state(notice, seen_at=now)

        cutoff = now - NOTICE_RETENTION_SECONDS
        self.conn.execute(
            "DELETE FROM market_notices WHERE published_at>0 AND published_at<?",
            (cutoff,),
        )
        self.conn.commit()
        return {
            "received": received,
            "inserted": inserted,
            "state_updates": state_updates,
            "by_kind": dict(sorted(by_kind.items())),
        }

    def state_snapshot(self, exchange: str) -> dict[str, Any]:
        exchange = str(exchange or "").strip().lower()
        rows = [dict(row) for row in self.conn.execute(
            """SELECT s.exchange,s.market,s.state,s.notice_id,s.title,s.url,s.source,
                      s.effective_at,s.updated_at,
                      COALESCE(n.announcement_at,0) AS announcement_at,
                      COALESCE(n.deposit_at,0) AS deposit_at,
                      COALESCE(n.trade_open_at,0) AS trade_open_at,
                      COALESCE(n.termination_at,0) AS termination_at
               FROM market_lifecycle_notice_state s
               LEFT JOIN market_notices n
                 ON n.exchange=s.exchange AND n.notice_id=s.notice_id
               WHERE s.exchange=? ORDER BY s.market""",
            (exchange,),
        ).fetchall()]
        return {
            "exchange": exchange,
            "states": {str(row["market"]): str(row["state"]) for row in rows},
            "details": {str(row["market"]): row for row in rows},
            "counts": dict(sorted(Counter(str(row["state"]) for row in rows).items())),
        }

    def recent(self, exchange: str, limit: int = 80) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT exchange,notice_id,title,url,published_at,event_kind,symbols_json,source,
                      first_seen_at,updated_at,announcement_at,deposit_at,trade_open_at,termination_at
               FROM market_notices WHERE exchange=?
               ORDER BY CASE WHEN published_at>0 THEN published_at ELSE first_seen_at END DESC
               LIMIT ?""",
            (str(exchange or "").strip().lower(), max(1, min(500, int(limit)))),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for source in rows:
            row = dict(source)
            try:
                symbols = json.loads(str(row.pop("symbols_json") or "[]"))
            except json.JSONDecodeError:
                symbols = []
            row["symbols"] = symbols if isinstance(symbols, list) else []
            result.append(row)
        return result
