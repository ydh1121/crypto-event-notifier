from __future__ import annotations

import json
import math
import sqlite3
import time
from typing import Any, Iterable

HORIZONS: tuple[tuple[str, int], ...] = (
    ("15m", 15 * 60),
    ("1h", 60 * 60),
    ("4h", 4 * 60 * 60),
    ("1d", 24 * 60 * 60),
)

DEFAULT_BENCHMARKS: tuple[tuple[str, str], ...] = (
    ("bithumb", "KRW-BTC"),
    ("upbit", "KRW-BTC"),
    ("bithumb", "KRW-ETH"),
    ("upbit", "KRW-ETH"),
)

OFFICIAL_EVENT_SOURCES = (
    "us_bls_release_calendar",
    "us_bea_release_schedule",
    "us_fed_fomc_calendar",
    "us_sec_press_releases",
    "us_cftc_press_releases",
)

# The FOMC meeting calendar intentionally preserves date-only meeting evidence.
# A date without the statement/release clock must never be turned into a price
# reaction anchor. Statement/minutes/projections rows remain eligible when they
# carry an actual source timestamp.
EXCLUDED_EVENT_TYPES = {"FOMC_MEETING"}

PROVIDER_ID = "local_public_exchange_trade_stream"
DATA_RIGHTS = "public_exchange_market_data_internal_research"
OBSERVATION_TOLERANCE_SECONDS = 120.0
EVENT_LOOKBACK_SECONDS = 3 * 24 * 60 * 60
MAX_EVENTS = 80
SCHEMA_VERSION = 1


class IntelligenceEventResponseCollector:
    """Accumulate point-in-time crypto reactions to stored Phase 5 events.

    Baseline semantics are strictly backward-looking: the last public trade at
    or before the event timestamp. Target semantics are the first public trade
    at or after the exact 15m/1h/4h/1d target timestamp. Both observations must
    fall inside a small bounded tolerance. Missing observations remain missing;
    they are never converted to a zero return.

    This collector reads only the local public market-flow stream and writes
    research evidence. It has no scoring, PAPER decision, sizing or order path.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        benchmarks: Iterable[tuple[str, str]] | None = None,
        observation_tolerance_seconds: float = OBSERVATION_TOLERANCE_SECONDS,
        event_lookback_seconds: float = EVENT_LOOKBACK_SECONDS,
        max_events: int = MAX_EVENTS,
    ) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=10000")
        source = tuple(benchmarks or DEFAULT_BENCHMARKS)
        cleaned: list[tuple[str, str]] = []
        for exchange, market in source:
            item = (str(exchange or "").strip().lower(), str(market or "").strip().upper())
            if not item[0] or not item[1] or item in cleaned:
                continue
            cleaned.append(item)
        if not cleaned:
            raise ValueError("at least one event-response benchmark is required")
        self.benchmarks = tuple(cleaned)
        self.observation_tolerance_seconds = max(
            15.0, min(10 * 60.0, float(observation_tolerance_seconds))
        )
        self.event_lookback_seconds = max(
            60 * 60.0, min(7 * 24 * 60 * 60.0, float(event_lookback_seconds))
        )
        self.max_events = max(1, min(500, int(max_events)))
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_intelligence_event_responses (
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                horizon_seconds REAL NOT NULL,
                event_ts REAL NOT NULL,
                baseline_trade_ts REAL NOT NULL,
                baseline_price REAL NOT NULL,
                target_ts REAL NOT NULL,
                target_trade_ts REAL NOT NULL,
                target_price REAL NOT NULL,
                return_pct REAL NOT NULL,
                provider_id TEXT NOT NULL,
                data_rights TEXT NOT NULL,
                observation_tolerance_seconds REAL NOT NULL,
                captured_at REAL NOT NULL,
                attributes_json TEXT NOT NULL DEFAULT '{}',
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(event_id,exchange,market,horizon_label,provider_id)
            );
            CREATE INDEX IF NOT EXISTS idx_intelligence_event_responses_event
                ON research_intelligence_event_responses(event_id,horizon_seconds,exchange,market);
            CREATE INDEX IF NOT EXISTS idx_intelligence_event_responses_type
                ON research_intelligence_event_responses(event_type,horizon_seconds,captured_at DESC);
            CREATE INDEX IF NOT EXISTS idx_intelligence_event_responses_market
                ON research_intelligence_event_responses(exchange,market,horizon_seconds,captured_at DESC);
            """
        )
        self.conn.commit()

    def _table_exists(self, name: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (str(name),),
        ).fetchone()
        return row is not None

    def _eligible_events(self, now: float) -> list[sqlite3.Row]:
        placeholders = ",".join("?" for _ in OFFICIAL_EVENT_SOURCES)
        params: list[Any] = [*OFFICIAL_EVENT_SOURCES, now - self.event_lookback_seconds, now]
        return self.conn.execute(
            f"""SELECT event_id,event_type,source_id,title,source_ts
                FROM research_intelligence_events
                WHERE source_id IN ({placeholders})
                  AND source_ts>=? AND source_ts<=?
                ORDER BY source_ts DESC,event_id
                LIMIT ?""",
            (*params, self.max_events),
        ).fetchall()

    def _existing(self, event_id: str, exchange: str, market: str, horizon_label: str) -> bool:
        row = self.conn.execute(
            """SELECT 1 FROM research_intelligence_event_responses
               WHERE event_id=? AND exchange=? AND market=? AND horizon_label=? AND provider_id=?""",
            (event_id, exchange, market, horizon_label, PROVIDER_ID),
        ).fetchone()
        return row is not None

    def _baseline_trade(self, exchange: str, market: str, event_ts: float) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT sequential_id,trade_ts,trade_price
               FROM research_market_trade_flow_mx
               WHERE exchange=? AND market=?
                 AND trade_ts<=? AND trade_ts>=?
                 AND trade_price>0
               ORDER BY trade_ts DESC,sequential_id DESC
               LIMIT 1""",
            (
                exchange,
                market,
                float(event_ts),
                float(event_ts) - self.observation_tolerance_seconds,
            ),
        ).fetchone()

    def _target_trade(self, exchange: str, market: str, target_ts: float) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT sequential_id,trade_ts,trade_price
               FROM research_market_trade_flow_mx
               WHERE exchange=? AND market=?
                 AND trade_ts>=? AND trade_ts<=?
                 AND trade_price>0
               ORDER BY trade_ts ASC,sequential_id ASC
               LIMIT 1""",
            (
                exchange,
                market,
                float(target_ts),
                float(target_ts) + self.observation_tolerance_seconds,
            ),
        ).fetchone()

    def run_once(self, *, now: float | None = None) -> dict[str, Any]:
        current = float(now if now is not None else time.time())
        result: dict[str, Any] = {
            "ok": True,
            "status": "starting",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "network_requests": 0,
            "provider_id": PROVIDER_ID,
            "horizons": [label for label, _ in HORIZONS],
            "benchmarks": [f"{exchange}:{market}" for exchange, market in self.benchmarks],
            "events_considered": 0,
            "events_excluded_imprecise": 0,
            "due_observations": 0,
            "future_observations": 0,
            "samples_inserted": 0,
            "already_captured": 0,
            "missing_baseline": 0,
            "missing_target": 0,
        }

        if not self._table_exists("research_intelligence_events"):
            result["status"] = "waiting_for_intelligence_events"
            return result
        if not self._table_exists("research_market_trade_flow_mx"):
            result["status"] = "waiting_for_market_flow"
            return result

        events = self._eligible_events(current)
        result["events_considered"] = len(events)
        if not events:
            result["status"] = "idle"
            return result

        for event in events:
            event_type = str(event["event_type"] or "").strip().upper()
            if event_type in EXCLUDED_EVENT_TYPES:
                result["events_excluded_imprecise"] += 1
                continue
            event_id = str(event["event_id"])
            source_id = str(event["source_id"])
            title = str(event["title"] or "")
            event_ts = float(event["source_ts"] or 0.0)
            if event_ts <= 0 or event_ts > current:
                continue

            for horizon_label, horizon_seconds in HORIZONS:
                target_ts = event_ts + float(horizon_seconds)
                if target_ts > current:
                    result["future_observations"] += len(self.benchmarks)
                    continue

                for exchange, market in self.benchmarks:
                    if self._existing(event_id, exchange, market, horizon_label):
                        result["already_captured"] += 1
                        continue
                    result["due_observations"] += 1

                    baseline = self._baseline_trade(exchange, market, event_ts)
                    if baseline is None:
                        result["missing_baseline"] += 1
                        continue
                    target = self._target_trade(exchange, market, target_ts)
                    if target is None:
                        result["missing_target"] += 1
                        continue

                    baseline_ts = float(baseline["trade_ts"])
                    target_trade_ts = float(target["trade_ts"])
                    baseline_price = float(baseline["trade_price"])
                    target_price = float(target["trade_price"])
                    if (
                        baseline_price <= 0
                        or target_price <= 0
                        or baseline_ts > event_ts
                        or target_trade_ts < target_ts
                    ):
                        # Preserve absence semantics rather than coercing an
                        # invalid observation into a numeric response.
                        result["missing_target"] += 1
                        continue
                    return_pct = (target_price / baseline_price - 1.0) * 100.0
                    if not math.isfinite(return_pct):
                        result["missing_target"] += 1
                        continue

                    attrs = {
                        "event_title": title,
                        "event_time_semantics": "stored_official_source_ts",
                        "baseline_semantics": "last_public_trade_at_or_before_event",
                        "target_semantics": "first_public_trade_at_or_after_exact_horizon",
                        "baseline_lag_seconds": event_ts - baseline_ts,
                        "target_lag_seconds": target_trade_ts - target_ts,
                        "baseline_sequential_id": str(baseline["sequential_id"] or ""),
                        "target_sequential_id": str(target["sequential_id"] or ""),
                        "score_authority": False,
                        "point_in_time_backfill_used": False,
                        "missing_values_coerced_to_zero": False,
                    }
                    cursor = self.conn.execute(
                        """INSERT OR IGNORE INTO research_intelligence_event_responses(
                               event_id,event_type,source_id,exchange,market,horizon_label,
                               horizon_seconds,event_ts,baseline_trade_ts,baseline_price,target_ts,
                               target_trade_ts,target_price,return_pct,provider_id,data_rights,
                               observation_tolerance_seconds,captured_at,attributes_json,schema_version
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            event_id,
                            event_type,
                            source_id,
                            exchange,
                            market,
                            horizon_label,
                            float(horizon_seconds),
                            event_ts,
                            baseline_ts,
                            baseline_price,
                            target_ts,
                            target_trade_ts,
                            target_price,
                            return_pct,
                            PROVIDER_ID,
                            DATA_RIGHTS,
                            self.observation_tolerance_seconds,
                            current,
                            json.dumps(attrs, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                            SCHEMA_VERSION,
                        ),
                    )
                    if int(cursor.rowcount or 0) > 0:
                        result["samples_inserted"] += 1
                    else:
                        result["already_captured"] += 1

        self.conn.commit()
        result["status"] = "ok"
        return result

    def recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT * FROM research_intelligence_event_responses
               ORDER BY captured_at DESC,event_ts DESC,horizon_seconds,exchange,market
               LIMIT ?""",
            (max(1, min(1000, int(limit))),),
        ).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["attributes"] = json.loads(str(item.pop("attributes_json") or "{}"))
            except (json.JSONDecodeError, TypeError, ValueError):
                item["attributes"] = {}
            output.append(item)
        return output
