from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from typing import Any, Iterable

from .market_lifecycle import CAUTION, NEW_LISTING, NORMAL, TERMINATED, decide_lifecycle_state

MIN_EXISTING_COVERAGE_RATIO = 0.75


class MarketLifecycleStore:
    """Additive lifecycle registry backed by the existing local SQLite connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS market_lifecycle (
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                state TEXT NOT NULL,
                warning INTEGER NOT NULL DEFAULT 0,
                baseline INTEGER NOT NULL DEFAULT 0,
                first_seen_at REAL NOT NULL,
                last_seen_at REAL NOT NULL,
                first_missing_at REAL NOT NULL DEFAULT 0,
                missing_observations INTEGER NOT NULL DEFAULT 0,
                state_updated_at REAL NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(exchange, market)
            );
            CREATE INDEX IF NOT EXISTS idx_market_lifecycle_exchange_state
                ON market_lifecycle(exchange, state, market);

            CREATE TABLE IF NOT EXISTS market_lifecycle_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                previous_state TEXT NOT NULL,
                new_state TEXT NOT NULL,
                reason TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_market_lifecycle_events_scope_ts
                ON market_lifecycle_events(exchange, market, ts DESC);
            """
        )
        self.conn.commit()

    @staticmethod
    def _market_fields(source: Any) -> tuple[str, str, str, bool]:
        market = str(getattr(source, "market", "") or "").upper()
        symbol = str(getattr(source, "symbol", "") or market.removeprefix("KRW-")).upper()
        name = str(getattr(source, "name", "") or symbol)
        warning = bool(getattr(source, "warning", False))
        return market, symbol, name, warning

    def _rows(self, exchange: str) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM market_lifecycle WHERE exchange=?",
            (exchange,),
        ).fetchall()
        return {str(row["market"]): dict(row) for row in rows}

    def _record_event(
        self,
        *,
        ts: float,
        exchange: str,
        market: str,
        previous_state: str,
        new_state: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO market_lifecycle_events(
                ts,exchange,market,previous_state,new_state,reason,metadata_json)
                VALUES(?,?,?,?,?,?,?)""",
            (
                ts,
                exchange,
                market,
                previous_state,
                new_state,
                reason,
                json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":")),
            ),
        )

    def _observation_is_safe(self, existing_count: int, current_count: int) -> tuple[bool, float]:
        if existing_count <= 0:
            return current_count > 0, 1.0 if current_count > 0 else 0.0
        ratio = current_count / existing_count
        return current_count > 0 and ratio >= MIN_EXISTING_COVERAGE_RATIO, ratio

    def observe_markets(
        self,
        exchange: str,
        markets: Iterable[Any],
        *,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        exchange = str(exchange or "").strip().lower()
        if not exchange:
            raise ValueError("exchange is required")
        now = float(observed_at or time.time())
        existing = self._rows(exchange)
        baseline_run = not existing
        current: dict[str, tuple[str, str, bool]] = {}
        transitions: list[dict[str, Any]] = []

        for source in markets:
            market, symbol, name, warning = self._market_fields(source)
            if market.startswith("KRW-"):
                current[market] = (symbol, name, warning)

        safe, coverage_ratio = self._observation_is_safe(len(existing), len(current))
        if not safe:
            snapshot = self.snapshot(exchange)
            snapshot.update(
                {
                    "baseline_run": baseline_run,
                    "transitions": [],
                    "observation_rejected": True,
                    "observed_market_count": len(current),
                    "coverage_ratio": coverage_ratio,
                }
            )
            return snapshot

        for market, (symbol, name, warning) in current.items():
            previous = existing.get(market)
            if previous is None:
                baseline = baseline_run
                decision = decide_lifecycle_state(
                    previous_state="",
                    warning=warning,
                    first_seen_at=now,
                    now=now,
                    missing_observations=0,
                    baseline=baseline,
                )
                self.conn.execute(
                    """INSERT INTO market_lifecycle(
                        exchange,market,symbol,name,state,warning,baseline,first_seen_at,last_seen_at,
                        first_missing_at,missing_observations,state_updated_at,metadata_json)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        exchange,
                        market,
                        symbol,
                        name,
                        decision.state,
                        int(warning),
                        int(baseline),
                        now,
                        now,
                        0.0,
                        0,
                        now,
                        "{}",
                    ),
                )
                if not baseline or decision.state == CAUTION:
                    self._record_event(
                        ts=now,
                        exchange=exchange,
                        market=market,
                        previous_state="",
                        new_state=decision.state,
                        reason=decision.reason,
                    )
                    transitions.append({"market": market, "from": "", "to": decision.state, "reason": decision.reason})
                continue

            previous_state = str(previous.get("state") or NORMAL)
            baseline = bool(previous.get("baseline"))
            decision = decide_lifecycle_state(
                previous_state=previous_state,
                warning=warning,
                first_seen_at=float(previous.get("first_seen_at") or now),
                now=now,
                missing_observations=0,
                baseline=baseline,
            )
            state_updated_at = now if decision.state != previous_state else float(previous.get("state_updated_at") or now)
            self.conn.execute(
                """UPDATE market_lifecycle SET
                    symbol=?,name=?,state=?,warning=?,last_seen_at=?,first_missing_at=0,
                    missing_observations=0,state_updated_at=?
                    WHERE exchange=? AND market=?""",
                (
                    symbol,
                    name,
                    decision.state,
                    int(warning),
                    now,
                    state_updated_at,
                    exchange,
                    market,
                ),
            )
            if decision.state != previous_state:
                self._record_event(
                    ts=now,
                    exchange=exchange,
                    market=market,
                    previous_state=previous_state,
                    new_state=decision.state,
                    reason=decision.reason,
                )
                transitions.append({"market": market, "from": previous_state, "to": decision.state, "reason": decision.reason})

        for market, previous in existing.items():
            if market in current:
                continue
            missing = int(previous.get("missing_observations") or 0) + 1
            first_missing = float(previous.get("first_missing_at") or 0.0) or now
            previous_state = str(previous.get("state") or NORMAL)
            decision = decide_lifecycle_state(
                previous_state=previous_state,
                warning=bool(previous.get("warning")),
                first_seen_at=float(previous.get("first_seen_at") or now),
                now=now,
                missing_observations=missing,
                baseline=bool(previous.get("baseline")),
            )
            state_updated_at = now if decision.state != previous_state else float(previous.get("state_updated_at") or now)
            self.conn.execute(
                """UPDATE market_lifecycle SET
                    state=?,first_missing_at=?,missing_observations=?,state_updated_at=?
                    WHERE exchange=? AND market=?""",
                (decision.state, first_missing, missing, state_updated_at, exchange, market),
            )
            if decision.state != previous_state:
                self._record_event(
                    ts=now,
                    exchange=exchange,
                    market=market,
                    previous_state=previous_state,
                    new_state=decision.state,
                    reason=decision.reason,
                )
                transitions.append({"market": market, "from": previous_state, "to": decision.state, "reason": decision.reason})

        self.conn.commit()
        snapshot = self.snapshot(exchange)
        snapshot.update(
            {
                "baseline_run": baseline_run,
                "transitions": transitions,
                "observation_rejected": False,
                "observed_market_count": len(current),
                "coverage_ratio": coverage_ratio,
            }
        )
        return snapshot

    def snapshot(self, exchange: str) -> dict[str, Any]:
        exchange = str(exchange or "").strip().lower()
        rows = [dict(row) for row in self.conn.execute(
            """SELECT exchange,market,symbol,name,state,warning,baseline,first_seen_at,last_seen_at,
                      first_missing_at,missing_observations,state_updated_at
               FROM market_lifecycle WHERE exchange=? ORDER BY market""",
            (exchange,),
        ).fetchall()]
        counts = Counter(str(row.get("state") or NORMAL) for row in rows)
        attention = [
            row for row in rows
            if str(row.get("state") or NORMAL) in {NEW_LISTING, CAUTION, TERMINATED}
        ]
        return {
            "exchange": exchange,
            "market_count": len(rows),
            "counts": dict(sorted(counts.items())),
            "attention": attention,
            "states": {str(row["market"]): str(row["state"]) for row in rows},
        }
