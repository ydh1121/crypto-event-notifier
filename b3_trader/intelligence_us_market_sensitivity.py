from __future__ import annotations

import json
import math
import sqlite3
import statistics
import time
from collections import defaultdict
from typing import Any

from .intelligence_event_response import PROVIDER_ID as EVENT_RESPONSE_PROVIDER_ID

STATS_PROVIDER_ID = "phase5_us_market_sensitivity_v1"
STATS_VERSION = 1
MIN_EXPLORATORY_SAMPLES = 5
MIN_DESCRIPTIVE_SAMPLES = 20
FLAT_EPSILON_PCT = 1e-12


class UsMarketSensitivityAccumulator:
    """Build descriptive sensitivity statistics from point-in-time event responses.

    The accumulator only reads the vetted local event-response evidence table and
    writes derived research statistics. It performs no network requests and has
    no scoring, PAPER decision, sizing or order authority.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=10000")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_us_market_sensitivity_stats (
                event_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                horizon_seconds REAL NOT NULL,
                response_provider_id TEXT NOT NULL,
                stats_provider_id TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                distinct_event_count INTEGER NOT NULL,
                positive_count INTEGER NOT NULL,
                negative_count INTEGER NOT NULL,
                flat_count INTEGER NOT NULL,
                positive_rate_pct REAL NOT NULL,
                mean_return_pct REAL NOT NULL,
                median_return_pct REAL NOT NULL,
                mean_abs_return_pct REAL NOT NULL,
                stddev_return_pct REAL,
                min_return_pct REAL NOT NULL,
                max_return_pct REAL NOT NULL,
                first_event_ts REAL NOT NULL,
                last_event_ts REAL NOT NULL,
                readiness TEXT NOT NULL,
                calculated_at REAL NOT NULL,
                attributes_json TEXT NOT NULL DEFAULT '{}',
                stats_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(
                    event_type,source_id,exchange,market,horizon_label,
                    response_provider_id,stats_provider_id
                )
            );
            CREATE INDEX IF NOT EXISTS idx_us_market_sensitivity_type
                ON research_us_market_sensitivity_stats(
                    event_type,horizon_seconds,market,exchange
                );
            CREATE INDEX IF NOT EXISTS idx_us_market_sensitivity_readiness
                ON research_us_market_sensitivity_stats(
                    readiness,sample_count DESC,last_event_ts DESC
                );
            """
        )
        self.conn.commit()

    def _table_exists(self, name: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (str(name),),
        ).fetchone()
        return row is not None

    @staticmethod
    def readiness_for(sample_count: int) -> str:
        count = max(0, int(sample_count))
        if count >= MIN_DESCRIPTIVE_SAMPLES:
            return "descriptive_ready"
        if count >= MIN_EXPLORATORY_SAMPLES:
            return "exploratory"
        return "insufficient_sample"

    def _source_rows(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT event_id,event_type,source_id,exchange,market,horizon_label,
                      horizon_seconds,event_ts,return_pct,provider_id
               FROM research_intelligence_event_responses
               WHERE provider_id=?
               ORDER BY event_type,source_id,exchange,market,horizon_seconds,event_ts,event_id""",
            (EVENT_RESPONSE_PROVIDER_ID,),
        ).fetchall()

    @staticmethod
    def _group_key(row: sqlite3.Row) -> tuple[str, str, str, str, str, float]:
        return (
            str(row["event_type"] or "").strip().upper(),
            str(row["source_id"] or "").strip().lower(),
            str(row["exchange"] or "").strip().lower(),
            str(row["market"] or "").strip().upper(),
            str(row["horizon_label"] or "").strip().lower(),
            float(row["horizon_seconds"]),
        )

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
            "response_provider_id": EVENT_RESPONSE_PROVIDER_ID,
            "stats_provider_id": STATS_PROVIDER_ID,
            "samples_considered": 0,
            "groups_written": 0,
            "invalid_rows": 0,
            "readiness_counts": {
                "insufficient_sample": 0,
                "exploratory": 0,
                "descriptive_ready": 0,
            },
        }

        if not self._table_exists("research_intelligence_event_responses"):
            result["status"] = "waiting_for_event_response_table"
            return result

        rows = self._source_rows()
        result["samples_considered"] = len(rows)
        if not rows:
            with self.conn:
                self.conn.execute(
                    "DELETE FROM research_us_market_sensitivity_stats WHERE stats_provider_id=?",
                    (STATS_PROVIDER_ID,),
                )
            result["status"] = "waiting_for_event_response_samples"
            return result

        grouped: dict[
            tuple[str, str, str, str, str, float],
            list[tuple[str, float, float]],
        ] = defaultdict(list)
        for row in rows:
            try:
                event_id = str(row["event_id"] or "").strip()
                event_ts = float(row["event_ts"])
                return_pct = float(row["return_pct"])
                key = self._group_key(row)
            except (TypeError, ValueError):
                result["invalid_rows"] = int(result["invalid_rows"]) + 1
                continue
            if (
                not event_id
                or not all(key[:5])
                or key[5] <= 0
                or event_ts <= 0
                or not math.isfinite(event_ts)
                or not math.isfinite(return_pct)
            ):
                result["invalid_rows"] = int(result["invalid_rows"]) + 1
                continue
            grouped[key].append((event_id, event_ts, return_pct))

        if int(result["invalid_rows"]) > 0:
            result["ok"] = False
            result["status"] = "invalid_event_response_rows"
            return result
        if not grouped:
            result["ok"] = False
            result["status"] = "no_valid_event_response_rows"
            return result

        derived: list[tuple[Any, ...]] = []
        readiness_counts = dict(result["readiness_counts"])
        for key, samples in grouped.items():
            event_type, source_id, exchange, market, horizon_label, horizon_seconds = key
            returns = [value[2] for value in samples]
            event_ids = {value[0] for value in samples}
            event_times = [value[1] for value in samples]
            sample_count = len(returns)
            positive_count = sum(value > FLAT_EPSILON_PCT for value in returns)
            negative_count = sum(value < -FLAT_EPSILON_PCT for value in returns)
            flat_count = sample_count - positive_count - negative_count
            readiness = self.readiness_for(sample_count)
            readiness_counts[readiness] = int(readiness_counts.get(readiness) or 0) + 1
            mean_return = statistics.fmean(returns)
            median_return = statistics.median(returns)
            mean_abs_return = statistics.fmean(abs(value) for value in returns)
            stddev_return = statistics.stdev(returns) if sample_count >= 2 else None
            attributes = {
                "descriptive_only": True,
                "score_authority": False,
                "promotion_eligible": False,
                "minimum_exploratory_samples": MIN_EXPLORATORY_SAMPLES,
                "minimum_descriptive_samples": MIN_DESCRIPTIVE_SAMPLES,
                "flat_epsilon_pct": FLAT_EPSILON_PCT,
                "missing_values_coerced_to_zero": False,
                "grouping": [
                    "event_type",
                    "source_id",
                    "exchange",
                    "market",
                    "horizon_label",
                    "response_provider_id",
                ],
            }
            derived.append(
                (
                    event_type,
                    source_id,
                    exchange,
                    market,
                    horizon_label,
                    horizon_seconds,
                    EVENT_RESPONSE_PROVIDER_ID,
                    STATS_PROVIDER_ID,
                    sample_count,
                    len(event_ids),
                    positive_count,
                    negative_count,
                    flat_count,
                    positive_count / sample_count * 100.0,
                    mean_return,
                    median_return,
                    mean_abs_return,
                    stddev_return,
                    min(returns),
                    max(returns),
                    min(event_times),
                    max(event_times),
                    readiness,
                    current,
                    json.dumps(
                        attributes,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    STATS_VERSION,
                )
            )

        with self.conn:
            self.conn.execute(
                "DELETE FROM research_us_market_sensitivity_stats WHERE stats_provider_id=?",
                (STATS_PROVIDER_ID,),
            )
            self.conn.executemany(
                """INSERT INTO research_us_market_sensitivity_stats(
                       event_type,source_id,exchange,market,horizon_label,horizon_seconds,
                       response_provider_id,stats_provider_id,sample_count,distinct_event_count,
                       positive_count,negative_count,flat_count,positive_rate_pct,mean_return_pct,
                       median_return_pct,mean_abs_return_pct,stddev_return_pct,min_return_pct,
                       max_return_pct,first_event_ts,last_event_ts,readiness,calculated_at,
                       attributes_json,stats_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                derived,
            )

        result["groups_written"] = len(derived)
        result["readiness_counts"] = readiness_counts
        result["status"] = "ok"
        return result

    def recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT * FROM research_us_market_sensitivity_stats
               WHERE stats_provider_id=?
               ORDER BY sample_count DESC,last_event_ts DESC,horizon_seconds,event_type,exchange,market
               LIMIT ?""",
            (STATS_PROVIDER_ID, max(1, min(1000, int(limit)))),
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
