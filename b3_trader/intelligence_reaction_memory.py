from __future__ import annotations

import sqlite3
import statistics
import time
from collections import defaultdict
from typing import Any

from .intelligence_reaction import REACTION_WINDOWS_SECONDS

MEMORY_VERSION = 1


class IntelligenceReactionMemoryStore:
    """Empirical event-type/coin reaction memory derived from raw reactions.

    Provider and exchange remain part of the grouping key so statistics never
    hide a cross-venue or cross-provider mixture. This layer exposes evidence
    inputs only; it deliberately does not emit a trading score or confidence
    weight before promotion gates are defined and validated.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_intelligence_reaction_memory (
                event_type TEXT NOT NULL,
                market TEXT NOT NULL,
                window TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                exchange TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                mean_return_pct REAL NOT NULL,
                median_return_pct REAL NOT NULL,
                stdev_return_pct REAL NOT NULL,
                positive_count INTEGER NOT NULL,
                negative_count INTEGER NOT NULL,
                zero_count INTEGER NOT NULL,
                positive_rate_pct REAL NOT NULL,
                negative_rate_pct REAL NOT NULL,
                earliest_anchor_at REAL NOT NULL,
                latest_anchor_at REAL NOT NULL,
                mean_start_delay_seconds REAL NOT NULL,
                mean_end_delay_seconds REAL NOT NULL,
                updated_at REAL NOT NULL,
                memory_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(event_type,market,window,provider_id,exchange)
            );
            CREATE INDEX IF NOT EXISTS idx_research_intelligence_reaction_memory_lookup
                ON research_intelligence_reaction_memory(market,event_type,window,sample_count DESC);
            CREATE INDEX IF NOT EXISTS idx_research_intelligence_reaction_memory_recent
                ON research_intelligence_reaction_memory(latest_anchor_at DESC);
            """
        )
        self.conn.commit()

    def refresh(self, *, now: float | None = None) -> dict[str, int]:
        current = float(now if now is not None else time.time())
        if current <= 0:
            raise ValueError("now must be positive")
        tables = {
            str(row[0])
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "research_intelligence_reactions" not in tables:
            return {"source_rows": 0, "groups": 0}

        rows = self.conn.execute(
            """SELECT event_type,market,window,provider_id,exchange,anchor_at,
                      forward_return_pct,start_delay_seconds,end_delay_seconds
               FROM research_intelligence_reactions
               ORDER BY anchor_at"""
        ).fetchall()
        grouped: dict[tuple[str, str, str, str, str], list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            window = str(row["window"])
            if window not in REACTION_WINDOWS_SECONDS:
                continue
            key = (
                str(row["event_type"]),
                str(row["market"]),
                window,
                str(row["provider_id"]),
                str(row["exchange"]),
            )
            grouped[key].append(row)

        self.conn.execute("DELETE FROM research_intelligence_reaction_memory")
        for key, group in grouped.items():
            returns = [float(row["forward_return_pct"]) for row in group]
            anchors = [float(row["anchor_at"]) for row in group]
            start_delays = [float(row["start_delay_seconds"]) for row in group]
            end_delays = [float(row["end_delay_seconds"]) for row in group]
            positive = sum(1 for value in returns if value > 0)
            negative = sum(1 for value in returns if value < 0)
            zero = len(returns) - positive - negative
            count = len(returns)
            stdev = statistics.pstdev(returns) if count > 1 else 0.0
            self.conn.execute(
                """INSERT INTO research_intelligence_reaction_memory(
                    event_type,market,window,provider_id,exchange,sample_count,
                    mean_return_pct,median_return_pct,stdev_return_pct,
                    positive_count,negative_count,zero_count,positive_rate_pct,negative_rate_pct,
                    earliest_anchor_at,latest_anchor_at,mean_start_delay_seconds,mean_end_delay_seconds,
                    updated_at,memory_version
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    key[0],key[1],key[2],key[3],key[4],count,
                    statistics.fmean(returns),statistics.median(returns),stdev,
                    positive,negative,zero,positive / count * 100.0,negative / count * 100.0,
                    min(anchors),max(anchors),statistics.fmean(start_delays),statistics.fmean(end_delays),
                    current,MEMORY_VERSION,
                ),
            )
        self.conn.commit()
        return {"source_rows": len(rows), "groups": len(grouped)}

    @staticmethod
    def _decode(row: sqlite3.Row, *, now: float) -> dict[str, Any]:
        result = dict(row)
        latest = float(result.get("latest_anchor_at") or 0.0)
        result["recency_seconds"] = max(0.0, now - latest) if 0 < latest <= now else None
        result["confidence"] = None
        result["confidence_status"] = "not_promoted"
        return result

    def lookup(
        self,
        *,
        market: str,
        event_type: str = "",
        window: str = "",
        provider_id: str = "",
        exchange: str = "",
        now: float | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses = ["market=?"]
        params: list[Any] = [str(market or "").strip().upper()]
        if not params[0]:
            raise ValueError("market is required")
        if event_type:
            clauses.append("event_type=?")
            params.append(str(event_type).strip().upper())
        if window:
            clean_window = str(window).strip().lower()
            if clean_window not in REACTION_WINDOWS_SECONDS:
                raise ValueError(f"unsupported reaction window: {window!r}")
            clauses.append("window=?")
            params.append(clean_window)
        if provider_id:
            clauses.append("provider_id=?")
            params.append(str(provider_id).strip().lower())
        if exchange:
            clauses.append("exchange=?")
            params.append(str(exchange).strip().lower())
        params.append(max(1, min(2000, int(limit))))
        rows = self.conn.execute(
            f"""SELECT * FROM research_intelligence_reaction_memory
                WHERE {' AND '.join(clauses)}
                ORDER BY sample_count DESC, latest_anchor_at DESC LIMIT ?""",
            tuple(params),
        ).fetchall()
        current = float(now if now is not None else time.time())
        return [self._decode(row, now=current) for row in rows]
