from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Iterable

from .intelligence_event import IntelligenceEvent, normalize_intelligence_event
from .intelligence_reaction import (
    REACTION_WINDOWS_SECONDS,
    compute_event_reaction,
    event_reaction_anchor,
    normalize_reaction_price_observation,
)
from .intelligence_reaction_memory import IntelligenceReactionMemoryStore
from .intelligence_reaction_store import IntelligenceReactionStore

REACTION_SOURCE = {
    "15m": ("1m", 60),
    "1h": ("1m", 60),
    "4h": ("1m", 60),
    "1d": ("5m", 5 * 60),
}
DEFAULT_MAX_EVENTS = 50
DEFAULT_MAX_PAIRS = 40
DEFAULT_MAX_REACTIONS = 1000


def _json(value: Any, fallback: Any) -> Any:
    try:
        decoded = json.loads(str(value or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        return fallback
    return decoded


def _event_from_row(row: sqlite3.Row) -> IntelligenceEvent:
    return normalize_intelligence_event(
        source_id=str(row["source_id"]),
        source_family=str(row["source_family"]),
        event_type=str(row["event_type"]),
        title=str(row["title"]),
        source_url=str(row["source_url"]),
        external_id=str(row["external_id"] or ""),
        published_at=float(row["published_at"] or 0.0),
        scheduled_at=float(row["scheduled_at"] or 0.0),
        observed_at=float(row["observed_at"] or 0.0),
        received_at=float(row["received_at"]),
        entities=_json(row["entities_json"], []),
        market_scope=_json(row["market_scope_json"], []),
        raw_text=str(row["raw_text"] or ""),
        summary_ko=str(row["summary_ko"] or ""),
        attributes=_json(row["attributes_json"], {}),
        confidence=None if row["confidence"] is None else float(row["confidence"]),
        version=int(row["version"] or 1),
    )


class IntelligenceReactionBuilder:
    """Build bounded forward-only event reactions from closed OHLCV evidence.

    Candle timestamps are treated as candle-open clocks. The price observation
    time is therefore `candle_ts + interval`. The first completed candle close
    on/after the event anchor and on/after the horizon target is selected. The
    allowed post-target delay equals one source interval, so tolerance is derived
    from data cadence rather than a trading heuristic. The entire source path
    between the two endpoints must be contiguous and closed.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        reaction_store: IntelligenceReactionStore | None = None,
        memory_store: IntelligenceReactionMemoryStore | None = None,
    ) -> None:
        self.conn = conn
        self.reaction_store = reaction_store or IntelligenceReactionStore(conn)
        self.memory_store = memory_store or IntelligenceReactionMemoryStore(conn)

    def _tables(self) -> set[str]:
        return {
            str(row[0])
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

    def _events(self, *, now: float, limit: int) -> list[IntelligenceEvent]:
        if "research_intelligence_events" not in self._tables():
            return []
        rows = self.conn.execute(
            """SELECT * FROM research_intelligence_events
               WHERE (published_at>0 OR observed_at>0 OR scheduled_at>0)
                 AND (CASE WHEN published_at>0 THEN published_at
                           WHEN observed_at>0 THEN observed_at ELSE scheduled_at END)<=?
               ORDER BY (CASE WHEN published_at>0 THEN published_at
                              WHEN observed_at>0 THEN observed_at ELSE scheduled_at END) DESC,
                        event_id
               LIMIT ?""",
            (now, max(1, min(1000, int(limit)))),
        ).fetchall()
        return [_event_from_row(row) for row in rows]

    def _pairs(
        self,
        pairs: Iterable[tuple[str, str]] | None,
        *,
        limit: int,
    ) -> list[tuple[str, str]]:
        if pairs is not None:
            seen: set[tuple[str, str]] = set()
            output: list[tuple[str, str]] = []
            for exchange, market in pairs:
                pair = (str(exchange or "").strip().lower(), str(market or "").strip().upper())
                if not pair[0] or not pair[1] or pair in seen:
                    continue
                seen.add(pair)
                output.append(pair)
                if len(output) >= max(1, int(limit)):
                    break
            return output
        if "research_market_ohlcv_mx" not in self._tables():
            return []
        rows = self.conn.execute(
            """SELECT exchange,market,MAX(candle_ts) AS latest_ts
               FROM research_market_ohlcv_mx
               WHERE is_closed=1
               GROUP BY exchange,market
               ORDER BY latest_ts DESC,exchange,market LIMIT ?""",
            (max(1, min(500, int(limit))),),
        ).fetchall()
        return [(str(row["exchange"]).lower(), str(row["market"]).upper()) for row in rows]

    def _first_close_at_or_after(
        self,
        *,
        exchange: str,
        market: str,
        timeframe: str,
        interval: int,
        target: float,
        source: str = "",
    ) -> sqlite3.Row | None:
        # candle_ts is the open clock; close observation is candle_ts + interval.
        min_candle_ts = target - interval
        max_candle_ts = target  # one interval of post-target tolerance
        if source:
            return self.conn.execute(
                """SELECT exchange,market,timeframe,candle_ts,close,source,received_at
                   FROM research_market_ohlcv_mx
                   WHERE exchange=? AND market=? AND timeframe=? AND is_closed=1 AND source=?
                     AND candle_ts>=? AND candle_ts<=?
                   ORDER BY candle_ts ASC LIMIT 1""",
                (exchange, market, timeframe, source, min_candle_ts, max_candle_ts),
            ).fetchone()
        return self.conn.execute(
            """SELECT exchange,market,timeframe,candle_ts,close,source,received_at
               FROM research_market_ohlcv_mx
               WHERE exchange=? AND market=? AND timeframe=? AND is_closed=1
                 AND candle_ts>=? AND candle_ts<=?
               ORDER BY candle_ts ASC LIMIT 1""",
            (exchange, market, timeframe, min_candle_ts, max_candle_ts),
        ).fetchone()

    def _contiguous_path(
        self,
        *,
        exchange: str,
        market: str,
        timeframe: str,
        interval: int,
        source: str,
        start_candle_ts: float,
        end_candle_ts: float,
    ) -> bool:
        if end_candle_ts < start_candle_ts:
            return False
        span = end_candle_ts - start_candle_ts
        steps = int(round(span / interval))
        if abs(span - steps * interval) > 1e-6:
            return False
        rows = self.conn.execute(
            """SELECT candle_ts FROM research_market_ohlcv_mx
               WHERE exchange=? AND market=? AND timeframe=? AND source=? AND is_closed=1
                 AND candle_ts>=? AND candle_ts<=?
               ORDER BY candle_ts ASC""",
            (exchange, market, timeframe, source, start_candle_ts, end_candle_ts),
        ).fetchall()
        if len(rows) != steps + 1:
            return False
        for index, row in enumerate(rows):
            expected = start_candle_ts + index * interval
            if abs(float(row["candle_ts"]) - expected) > 1e-6:
                return False
        return True

    @staticmethod
    def _observation(row: sqlite3.Row, *, interval: int):
        exchange = str(row["exchange"]).strip().lower()
        market = str(row["market"]).strip().upper()
        timeframe = str(row["timeframe"]).strip().lower()
        source = str(row["source"] or "public_rest").strip()
        candle_ts = float(row["candle_ts"])
        close_ts = candle_ts + interval
        provider_id = f"{exchange}:{source}:{timeframe}".lower()
        return normalize_reaction_price_observation(
            market=market,
            observed_at=close_ts,
            price=float(row["close"]),
            provider_id=provider_id,
            exchange=exchange,
            source=source,
            received_at=float(row["received_at"] or close_ts),
            evidence={
                "timeframe": timeframe,
                "candle_ts": candle_ts,
                "close_observed_at": close_ts,
                "source_interval_seconds": interval,
                "source": source,
                "is_closed": True,
            },
        )

    def run(
        self,
        *,
        now: float | None = None,
        pairs: Iterable[tuple[str, str]] | None = None,
        windows: Iterable[str] = tuple(REACTION_WINDOWS_SECONDS),
        max_events: int = DEFAULT_MAX_EVENTS,
        max_pairs: int = DEFAULT_MAX_PAIRS,
        max_reactions: int = DEFAULT_MAX_REACTIONS,
        refresh_memory: bool = True,
    ) -> dict[str, Any]:
        current = float(now if now is not None else time.time())
        if current <= 0:
            raise ValueError("now must be positive")
        if "research_market_ohlcv_mx" not in self._tables():
            memory = self.memory_store.refresh(now=current) if refresh_memory else {"source_rows": 0, "groups": 0}
            return {
                "events_considered": 0,
                "pairs_considered": 0,
                "due_candidates": 0,
                "reactions_ready": 0,
                "missing_price_alignment": 0,
                "missing_contiguous_path": 0,
                "ingest": {"received": 0, "inserted": 0, "updated": 0},
                "memory": memory,
            }

        clean_windows: list[str] = []
        for value in windows:
            label = str(value or "").strip().lower()
            if label not in REACTION_WINDOWS_SECONDS:
                raise ValueError(f"unsupported reaction window: {value!r}")
            if label not in clean_windows:
                clean_windows.append(label)
        events = self._events(now=current, limit=max_events)
        selected_pairs = self._pairs(pairs, limit=max_pairs)
        reactions = []
        due = 0
        missing_alignment = 0
        missing_path = 0
        cap = max(1, int(max_reactions))

        for event in events:
            anchor = event_reaction_anchor(event)
            if anchor is None:
                continue
            _, anchor_at = anchor
            for exchange, market in selected_pairs:
                for window in clean_windows:
                    horizon = REACTION_WINDOWS_SECONDS[window]
                    if current < anchor_at + horizon:
                        continue
                    due += 1
                    timeframe, interval = REACTION_SOURCE[window]
                    start_row = self._first_close_at_or_after(
                        exchange=exchange,
                        market=market,
                        timeframe=timeframe,
                        interval=interval,
                        target=anchor_at,
                    )
                    if start_row is None:
                        missing_alignment += 1
                        continue
                    source = str(start_row["source"] or "public_rest")
                    end_row = self._first_close_at_or_after(
                        exchange=exchange,
                        market=market,
                        timeframe=timeframe,
                        interval=interval,
                        target=anchor_at + horizon,
                        source=source,
                    )
                    if end_row is None:
                        missing_alignment += 1
                        continue
                    if not self._contiguous_path(
                        exchange=exchange,
                        market=market,
                        timeframe=timeframe,
                        interval=interval,
                        source=source,
                        start_candle_ts=float(start_row["candle_ts"]),
                        end_candle_ts=float(end_row["candle_ts"]),
                    ):
                        missing_path += 1
                        continue
                    reaction = compute_event_reaction(
                        event,
                        market=market,
                        window=window,
                        start=self._observation(start_row, interval=interval),
                        end=self._observation(end_row, interval=interval),
                        max_observation_delay_seconds=float(interval),
                    )
                    if reaction is not None:
                        reactions.append(reaction)
                    if len(reactions) >= cap:
                        break
                if len(reactions) >= cap:
                    break
            if len(reactions) >= cap:
                break

        ingest = self.reaction_store.ingest(reactions, seen_at=current) if reactions else {
            "received": 0,
            "inserted": 0,
            "updated": 0,
        }
        memory = self.memory_store.refresh(now=current) if refresh_memory else {"source_rows": 0, "groups": 0}
        return {
            "events_considered": len(events),
            "pairs_considered": len(selected_pairs),
            "due_candidates": due,
            "reactions_ready": len(reactions),
            "missing_price_alignment": missing_alignment,
            "missing_contiguous_path": missing_path,
            "ingest": ingest,
            "memory": memory,
        }
