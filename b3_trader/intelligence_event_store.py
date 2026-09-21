from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Iterable

from .intelligence_event import IntelligenceEvent
from .intelligence_source_registry import IntelligenceSource, default_intelligence_sources


class IntelligenceEventStore:
    """Phase 5 source registry + normalized event persistence.

    This store is research-only. It has no score, PAPER order, position-sizing or
    live-order authority.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        sources: Iterable[IntelligenceSource] | None = None,
    ) -> None:
        self.conn = conn
        self.sources = tuple(sources or default_intelligence_sources())
        self.source_map = {source.source_id: source for source in self.sources}
        if len(self.source_map) != len(self.sources):
            raise ValueError("duplicate intelligence source_id")
        self._init_schema()
        self.sync_sources(self.sources)

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_intelligence_sources (
                source_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                family TEXT NOT NULL,
                authority TEXT NOT NULL,
                url TEXT NOT NULL,
                transport TEXT NOT NULL,
                official INTEGER NOT NULL DEFAULT 0,
                collection_enabled INTEGER NOT NULL DEFAULT 0,
                event_types_json TEXT NOT NULL DEFAULT '[]',
                market_scope_json TEXT NOT NULL DEFAULT '[]',
                notes TEXT NOT NULL DEFAULT '',
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS research_intelligence_events (
                event_id TEXT PRIMARY KEY,
                external_id TEXT NOT NULL DEFAULT '',
                source_id TEXT NOT NULL,
                source_family TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                source_url TEXT NOT NULL,
                published_at REAL NOT NULL DEFAULT 0,
                scheduled_at REAL NOT NULL DEFAULT 0,
                observed_at REAL NOT NULL DEFAULT 0,
                source_ts REAL NOT NULL DEFAULT 0,
                received_at REAL NOT NULL,
                entities_json TEXT NOT NULL DEFAULT '[]',
                market_scope_json TEXT NOT NULL DEFAULT '[]',
                raw_text TEXT NOT NULL DEFAULT '',
                summary_ko TEXT NOT NULL DEFAULT '',
                attributes_json TEXT NOT NULL DEFAULT '{}',
                dedup_hash TEXT NOT NULL,
                confidence REAL,
                version INTEGER NOT NULL DEFAULT 1,
                first_seen_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(source_id) REFERENCES research_intelligence_sources(source_id)
            );
            CREATE INDEX IF NOT EXISTS idx_research_intelligence_events_source_ts
                ON research_intelligence_events(source_ts DESC, event_id);
            CREATE INDEX IF NOT EXISTS idx_research_intelligence_events_scheduled
                ON research_intelligence_events(scheduled_at, event_id);
            CREATE INDEX IF NOT EXISTS idx_research_intelligence_events_source
                ON research_intelligence_events(source_id, source_ts DESC);
            CREATE INDEX IF NOT EXISTS idx_research_intelligence_events_dedup
                ON research_intelligence_events(dedup_hash, source_ts DESC);
            """
        )
        self.conn.commit()

    def sync_sources(
        self,
        sources: Iterable[IntelligenceSource],
        *,
        now: float | None = None,
    ) -> int:
        ts = float(now if now is not None else time.time())
        count = 0
        for source in sources:
            self.conn.execute(
                """INSERT INTO research_intelligence_sources(
                    source_id,name,family,authority,url,transport,official,collection_enabled,
                    event_types_json,market_scope_json,notes,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source_id) DO UPDATE SET
                    name=excluded.name,family=excluded.family,authority=excluded.authority,
                    url=excluded.url,transport=excluded.transport,official=excluded.official,
                    collection_enabled=excluded.collection_enabled,
                    event_types_json=excluded.event_types_json,
                    market_scope_json=excluded.market_scope_json,notes=excluded.notes,
                    updated_at=excluded.updated_at""",
                (
                    source.source_id,
                    source.name,
                    source.family,
                    source.authority,
                    source.url,
                    source.transport,
                    1 if source.official else 0,
                    1 if source.collection_enabled else 0,
                    json.dumps(list(source.event_types), ensure_ascii=False, separators=(",", ":")),
                    json.dumps(list(source.market_scope), ensure_ascii=False, separators=(",", ":")),
                    source.notes,
                    ts,
                ),
            )
            count += 1
        self.conn.commit()
        return count

    def _validate_event(self, event: IntelligenceEvent) -> None:
        source = self.source_map.get(event.source_id)
        if source is None:
            raise ValueError(f"unregistered intelligence source: {event.source_id}")
        if event.source_family != source.family:
            raise ValueError(
                f"source family mismatch for {event.source_id}: {event.source_family} != {source.family}"
            )
        if event.event_type not in source.event_types:
            raise ValueError(
                f"event type {event.event_type} is not registered for source {event.source_id}"
            )

    def ingest(
        self,
        events: Iterable[IntelligenceEvent],
        *,
        seen_at: float | None = None,
    ) -> dict[str, int]:
        now = float(seen_at if seen_at is not None else time.time())
        received = 0
        inserted = 0
        updated = 0
        for event in events:
            self._validate_event(event)
            received += 1
            exists = self.conn.execute(
                "SELECT 1 FROM research_intelligence_events WHERE event_id=?",
                (event.event_id,),
            ).fetchone()
            entities_json = json.dumps(list(event.entities), ensure_ascii=False, separators=(",", ":"))
            scope_json = json.dumps(list(event.market_scope), ensure_ascii=False, separators=(",", ":"))
            attributes_json = json.dumps(event.attributes, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
            self.conn.execute(
                """INSERT INTO research_intelligence_events(
                    event_id,external_id,source_id,source_family,event_type,title,source_url,
                    published_at,scheduled_at,observed_at,source_ts,received_at,
                    entities_json,market_scope_json,raw_text,summary_ko,attributes_json,
                    dedup_hash,confidence,version,first_seen_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(event_id) DO UPDATE SET
                    external_id=CASE WHEN excluded.external_id<>'' THEN excluded.external_id ELSE research_intelligence_events.external_id END,
                    source_family=excluded.source_family,event_type=excluded.event_type,
                    title=excluded.title,source_url=excluded.source_url,
                    published_at=CASE WHEN excluded.published_at>0 THEN excluded.published_at ELSE research_intelligence_events.published_at END,
                    scheduled_at=CASE WHEN excluded.scheduled_at>0 THEN excluded.scheduled_at ELSE research_intelligence_events.scheduled_at END,
                    observed_at=CASE WHEN excluded.observed_at>0 THEN excluded.observed_at ELSE research_intelligence_events.observed_at END,
                    source_ts=CASE WHEN excluded.source_ts>0 THEN excluded.source_ts ELSE research_intelligence_events.source_ts END,
                    received_at=excluded.received_at,
                    entities_json=CASE WHEN excluded.entities_json<>'[]' THEN excluded.entities_json ELSE research_intelligence_events.entities_json END,
                    market_scope_json=CASE WHEN excluded.market_scope_json<>'[]' THEN excluded.market_scope_json ELSE research_intelligence_events.market_scope_json END,
                    raw_text=CASE WHEN excluded.raw_text<>'' THEN excluded.raw_text ELSE research_intelligence_events.raw_text END,
                    summary_ko=CASE WHEN excluded.summary_ko<>'' THEN excluded.summary_ko ELSE research_intelligence_events.summary_ko END,
                    attributes_json=CASE WHEN excluded.attributes_json<>'{}' THEN excluded.attributes_json ELSE research_intelligence_events.attributes_json END,
                    dedup_hash=excluded.dedup_hash,
                    confidence=CASE WHEN excluded.confidence IS NOT NULL THEN excluded.confidence ELSE research_intelligence_events.confidence END,
                    version=CASE WHEN excluded.version>research_intelligence_events.version THEN excluded.version ELSE research_intelligence_events.version END,
                    updated_at=excluded.updated_at""",
                (
                    event.event_id,
                    event.external_id,
                    event.source_id,
                    event.source_family,
                    event.event_type,
                    event.title,
                    event.source_url,
                    event.published_at,
                    event.scheduled_at,
                    event.observed_at,
                    event.source_ts,
                    event.received_at,
                    entities_json,
                    scope_json,
                    event.raw_text,
                    event.summary_ko,
                    attributes_json,
                    event.dedup_hash,
                    event.confidence,
                    event.version,
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
    def _decode_json(value: Any, fallback: Any) -> Any:
        try:
            decoded = json.loads(str(value or ""))
        except (json.JSONDecodeError, TypeError, ValueError):
            return fallback
        return decoded

    def _decode_event_row(self, row: sqlite3.Row, *, now: float) -> dict[str, Any]:
        result = dict(row)
        result["entities"] = self._decode_json(result.pop("entities_json", "[]"), [])
        result["market_scope"] = self._decode_json(result.pop("market_scope_json", "[]"), [])
        result["attributes"] = self._decode_json(result.pop("attributes_json", "{}"), {})
        source_ts = float(result.get("source_ts") or 0.0)
        result["freshness_seconds"] = (
            max(0.0, now - source_ts) if source_ts > 0 and source_ts <= now else None
        )
        return result

    def event(self, event_id: str, *, now: float | None = None) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM research_intelligence_events WHERE event_id=?",
            (str(event_id or ""),),
        ).fetchone()
        if row is None:
            return None
        return self._decode_event_row(row, now=float(now if now is not None else time.time()))

    def recent(
        self,
        *,
        limit: int = 100,
        source_family: str = "",
        source_id: str = "",
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if source_family:
            where.append("source_family=?")
            params.append(str(source_family).strip().lower())
        if source_id:
            where.append("source_id=?")
            params.append(str(source_id).strip().lower())
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(max(1, min(1000, int(limit))))
        rows = self.conn.execute(
            f"""SELECT * FROM research_intelligence_events {clause}
                ORDER BY CASE WHEN source_ts>0 THEN source_ts ELSE received_at END DESC,event_id
                LIMIT ?""",
            params,
        ).fetchall()
        ts = float(now if now is not None else time.time())
        return [self._decode_event_row(row, now=ts) for row in rows]

    def upcoming(
        self,
        *,
        now: float | None = None,
        horizon_seconds: float = 7 * 86400,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        start = float(now if now is not None else time.time())
        end = start + max(0.0, float(horizon_seconds))
        rows = self.conn.execute(
            """SELECT * FROM research_intelligence_events
               WHERE scheduled_at>=? AND scheduled_at<=?
               ORDER BY scheduled_at,event_id LIMIT ?""",
            (start, end, max(1, min(1000, int(limit)))),
        ).fetchall()
        return [self._decode_event_row(row, now=start) for row in rows]

    def source_snapshot(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM research_intelligence_sources ORDER BY family,source_id"
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["official"] = bool(item.get("official"))
            item["collection_enabled"] = bool(item.get("collection_enabled"))
            item["event_types"] = self._decode_json(item.pop("event_types_json", "[]"), [])
            item["market_scope"] = self._decode_json(item.pop("market_scope_json", "[]"), [])
            result.append(item)
        return result
