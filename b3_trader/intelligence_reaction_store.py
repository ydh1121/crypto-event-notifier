from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Iterable

from .intelligence_reaction import IntelligenceReaction, REACTION_WINDOWS_SECONDS


class IntelligenceReactionStore:
    """SQLite owner for evidence-backed Phase 5 forward event reactions."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_intelligence_reactions (
                reaction_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                market TEXT NOT NULL,
                window TEXT NOT NULL,
                horizon_seconds INTEGER NOT NULL,
                anchor_kind TEXT NOT NULL,
                anchor_at REAL NOT NULL,
                provider_id TEXT NOT NULL,
                exchange TEXT NOT NULL,
                start_at REAL NOT NULL,
                end_at REAL NOT NULL,
                start_price REAL NOT NULL,
                end_price REAL NOT NULL,
                forward_return_pct REAL NOT NULL,
                start_delay_seconds REAL NOT NULL,
                end_delay_seconds REAL NOT NULL,
                start_source TEXT NOT NULL,
                end_source TEXT NOT NULL,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                version INTEGER NOT NULL DEFAULT 1,
                first_seen_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(event_id, market, window, provider_id, exchange)
            );
            CREATE INDEX IF NOT EXISTS idx_research_intelligence_reactions_event
                ON research_intelligence_reactions(event_id, window, market);
            CREATE INDEX IF NOT EXISTS idx_research_intelligence_reactions_type_market
                ON research_intelligence_reactions(event_type, market, window, anchor_at DESC);
            CREATE INDEX IF NOT EXISTS idx_research_intelligence_reactions_market_time
                ON research_intelligence_reactions(market, anchor_at DESC);
            """
        )
        self.conn.commit()

    @staticmethod
    def _validate(item: IntelligenceReaction) -> None:
        expected_horizon = REACTION_WINDOWS_SECONDS.get(item.window)
        if expected_horizon is None or int(item.horizon_seconds) != expected_horizon:
            raise ValueError(f"reaction window/horizon mismatch: {item.window!r}")
        if not item.event_id or not item.source_id or not item.event_type or not item.market:
            raise ValueError("reaction event/source/type/market are required")
        if not item.provider_id or not item.exchange:
            raise ValueError("reaction provider_id/exchange are required")
        if item.anchor_kind not in {"published_at", "observed_at", "scheduled_at"}:
            raise ValueError(f"invalid reaction anchor_kind: {item.anchor_kind!r}")
        if item.anchor_at <= 0 or item.start_at < item.anchor_at:
            raise ValueError("reaction start must be on/after a positive event anchor")
        if item.end_at < item.anchor_at + expected_horizon:
            raise ValueError("reaction end must be on/after the requested horizon")
        if item.start_delay_seconds < 0 or item.end_delay_seconds < 0:
            raise ValueError("reaction alignment delays must be nonnegative")
        if item.start_price <= 0 or item.end_price <= 0:
            raise ValueError("reaction prices must be positive")

    def ingest(
        self,
        reactions: Iterable[IntelligenceReaction],
        *,
        seen_at: float | None = None,
    ) -> dict[str, int]:
        now = float(seen_at if seen_at is not None else time.time())
        if now <= 0:
            raise ValueError("seen_at must be positive")
        received = 0
        inserted = 0
        updated = 0
        for item in reactions:
            self._validate(item)
            received += 1
            exists = self.conn.execute(
                "SELECT 1 FROM research_intelligence_reactions WHERE reaction_id=?",
                (item.reaction_id,),
            ).fetchone()
            self.conn.execute(
                """INSERT INTO research_intelligence_reactions(
                    reaction_id,event_id,source_id,event_type,market,window,horizon_seconds,
                    anchor_kind,anchor_at,provider_id,exchange,start_at,end_at,start_price,end_price,
                    forward_return_pct,start_delay_seconds,end_delay_seconds,start_source,end_source,
                    evidence_json,version,first_seen_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(reaction_id) DO UPDATE SET
                    source_id=excluded.source_id,event_type=excluded.event_type,
                    horizon_seconds=excluded.horizon_seconds,anchor_kind=excluded.anchor_kind,
                    anchor_at=excluded.anchor_at,start_at=excluded.start_at,end_at=excluded.end_at,
                    start_price=excluded.start_price,end_price=excluded.end_price,
                    forward_return_pct=excluded.forward_return_pct,
                    start_delay_seconds=excluded.start_delay_seconds,
                    end_delay_seconds=excluded.end_delay_seconds,
                    start_source=excluded.start_source,end_source=excluded.end_source,
                    evidence_json=excluded.evidence_json,
                    version=CASE WHEN excluded.version>research_intelligence_reactions.version
                                 THEN excluded.version ELSE research_intelligence_reactions.version END,
                    updated_at=excluded.updated_at""",
                (
                    item.reaction_id,
                    item.event_id,
                    item.source_id,
                    item.event_type,
                    item.market,
                    item.window,
                    item.horizon_seconds,
                    item.anchor_kind,
                    item.anchor_at,
                    item.provider_id,
                    item.exchange,
                    item.start_at,
                    item.end_at,
                    item.start_price,
                    item.end_price,
                    item.forward_return_pct,
                    item.start_delay_seconds,
                    item.end_delay_seconds,
                    item.start_source,
                    item.end_source,
                    json.dumps(item.evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str),
                    item.version,
                    now,
                    now,
                ),
            )
            if exists:
                updated += 1
            else:
                inserted += 1
        self.conn.commit()
        return {"received": received, "inserted": inserted, "updated": updated}

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        try:
            result["evidence"] = json.loads(str(result.pop("evidence_json") or "{}"))
        except (json.JSONDecodeError, TypeError, ValueError):
            result["evidence"] = {}
        return result

    def for_event(self, event_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT * FROM research_intelligence_reactions
               WHERE event_id=?
               ORDER BY horizon_seconds, market, provider_id, exchange LIMIT ?""",
            (str(event_id or "").strip(), max(1, min(2000, int(limit)))),
        ).fetchall()
        return [self._decode(row) for row in rows]

    def history(
        self,
        *,
        event_type: str = "",
        market: str = "",
        window: str = "",
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if event_type:
            clauses.append("event_type=?")
            params.append(str(event_type).strip().upper())
        if market:
            clauses.append("market=?")
            params.append(str(market).strip().upper())
        if window:
            clean_window = str(window).strip().lower()
            if clean_window not in REACTION_WINDOWS_SECONDS:
                raise ValueError(f"unsupported reaction window: {window!r}")
            clauses.append("window=?")
            params.append(clean_window)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(5000, int(limit))))
        rows = self.conn.execute(
            f"SELECT * FROM research_intelligence_reactions{where} ORDER BY anchor_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        return [self._decode(row) for row in rows]
