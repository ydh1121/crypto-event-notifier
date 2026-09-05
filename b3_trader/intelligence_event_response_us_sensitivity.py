from __future__ import annotations

import hashlib
import math
import sqlite3
import statistics
import time
from collections import defaultdict
from typing import Any, Iterable

from .intelligence_event_response import PROVIDER_ID as EVENT_RESPONSE_PROVIDER_ID
from .intelligence_us_market_path_quality import assess_us_market_reference_path
from .intelligence_us_market_reference import SERIES_BY_SOURCE

DEFAULT_REFERENCE_SOURCES = tuple(SERIES_BY_SOURCE)
DEFAULT_MAX_REFERENCE_SKEW_SECONDS = 120.0
DEFAULT_MAX_RESPONSES = 2000
QUALITY_GATED_REFERENCE_PROVIDERS = {"massive_indices_1m"}
PAIR_VERSION = 1
SENSITIVITY_VERSION = 1
MIN_EXPLORATORY_SAMPLES = 5
MIN_DESCRIPTIVE_SAMPLES = 20
_EPSILON = 1e-12


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _response_id(row: sqlite3.Row) -> str:
    payload = "\x1f".join(
        (
            _clean(row["event_id"]),
            _clean(row["exchange"]).lower(),
            _clean(row["market"]).upper(),
            _clean(row["horizon_label"]).lower(),
            _clean(row["provider_id"]).lower(),
        )
    )
    return "ier:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _pair_id(*, response_id: str, reference_source_id: str, reference_provider_id: str) -> str:
    payload = "\x1f".join((response_id, reference_source_id, reference_provider_id))
    return "ierusp:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _readiness(sample_count: int) -> str:
    count = max(0, int(sample_count))
    if count >= MIN_DESCRIPTIVE_SAMPLES:
        return "descriptive_ready"
    if count >= MIN_EXPLORATORY_SAMPLES:
        return "exploratory"
    return "insufficient_sample"


class IntelligenceEventResponseUsSensitivityStore:
    """Correlate strict Phase 6 crypto event responses with U.S. market references.

    Input crypto responses retain exchange, market, horizon and provider identity.
    Reference observations are required at/after the event and exact target time;
    missing observations stay missing. Outputs are descriptive research evidence
    only and have no EventScore, PAPER decision, sizing or order authority.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=10000")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_intelligence_event_response_us_pairs (
                pair_id TEXT PRIMARY KEY,
                response_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_source_id TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                horizon_seconds REAL NOT NULL,
                event_ts REAL NOT NULL,
                target_ts REAL NOT NULL,
                coin_provider_id TEXT NOT NULL,
                coin_return_pct REAL NOT NULL,
                reference_source_id TEXT NOT NULL,
                reference_series TEXT NOT NULL,
                reference_provider_id TEXT NOT NULL,
                reference_return_pct REAL NOT NULL,
                reference_start_at REAL NOT NULL,
                reference_end_at REAL NOT NULL,
                reference_start_value REAL NOT NULL,
                reference_end_value REAL NOT NULL,
                start_skew_seconds REAL NOT NULL,
                end_skew_seconds REAL NOT NULL,
                start_session_state TEXT NOT NULL,
                end_session_state TEXT NOT NULL,
                start_latency_class TEXT NOT NULL,
                end_latency_class TEXT NOT NULL,
                start_delayed_seconds REAL,
                end_delayed_seconds REAL,
                start_data_rights TEXT NOT NULL,
                end_data_rights TEXT NOT NULL,
                pair_version INTEGER NOT NULL DEFAULT 1,
                first_seen_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(
                    event_id,exchange,market,horizon_label,coin_provider_id,
                    reference_source_id,reference_provider_id
                )
            );
            CREATE INDEX IF NOT EXISTS idx_event_response_us_pairs_lookup
                ON research_intelligence_event_response_us_pairs(
                    event_type,exchange,market,horizon_seconds,event_ts DESC
                );
            CREATE INDEX IF NOT EXISTS idx_event_response_us_pairs_reference
                ON research_intelligence_event_response_us_pairs(
                    reference_source_id,reference_provider_id,event_ts DESC
                );

            CREATE TABLE IF NOT EXISTS research_intelligence_event_response_us_sensitivity (
                event_type TEXT NOT NULL,
                event_source_id TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                coin_provider_id TEXT NOT NULL,
                reference_source_id TEXT NOT NULL,
                reference_series TEXT NOT NULL,
                reference_provider_id TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                distinct_event_count INTEGER NOT NULL,
                mean_coin_return_pct REAL NOT NULL,
                mean_reference_return_pct REAL NOT NULL,
                stdev_coin_return_pct REAL NOT NULL,
                stdev_reference_return_pct REAL NOT NULL,
                covariance REAL NOT NULL,
                beta REAL,
                correlation REAL,
                same_direction_count INTEGER NOT NULL,
                same_direction_rate_pct REAL NOT NULL,
                reference_positive_count INTEGER NOT NULL,
                reference_negative_count INTEGER NOT NULL,
                reference_zero_count INTEGER NOT NULL,
                mean_coin_when_reference_positive REAL,
                mean_coin_when_reference_negative REAL,
                mean_abs_coin_return_pct REAL NOT NULL,
                earliest_event_ts REAL NOT NULL,
                latest_event_ts REAL NOT NULL,
                mean_start_skew_seconds REAL NOT NULL,
                mean_end_skew_seconds REAL NOT NULL,
                readiness TEXT NOT NULL,
                score_authority INTEGER NOT NULL DEFAULT 0,
                promotion_eligible INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                sensitivity_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(
                    event_type,event_source_id,exchange,market,horizon_label,coin_provider_id,
                    reference_source_id,reference_provider_id
                )
            );
            CREATE INDEX IF NOT EXISTS idx_event_response_us_sensitivity_lookup
                ON research_intelligence_event_response_us_sensitivity(
                    exchange,market,event_type,horizon_label,sample_count DESC
                );
            """
        )
        self.conn.commit()

    def _tables(self) -> set[str]:
        return {
            str(row[0])
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    def _providers_at_or_after(
        self,
        *,
        source_id: str,
        target: float,
        max_skew_seconds: float,
    ) -> list[str]:
        rows = self.conn.execute(
            """SELECT DISTINCT provider_id FROM research_us_market_reference
               WHERE source_id=? AND observed_at>=? AND observed_at<=?
               ORDER BY provider_id""",
            (source_id, target, target + max_skew_seconds),
        ).fetchall()
        return [
            _clean(row[0]).lower()
            for row in rows
            if _clean(row[0])
        ]

    def _first_reference_at_or_after(
        self,
        *,
        source_id: str,
        provider_id: str,
        target: float,
        max_skew_seconds: float,
    ) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT * FROM research_us_market_reference
               WHERE source_id=? AND provider_id=?
                 AND observed_at>=? AND observed_at<=?
               ORDER BY observed_at ASC LIMIT 1""",
            (source_id, provider_id, target, target + max_skew_seconds),
        ).fetchone()

    def build_pairs(
        self,
        *,
        source_ids: Iterable[str] = DEFAULT_REFERENCE_SOURCES,
        max_reference_skew_seconds: float = DEFAULT_MAX_REFERENCE_SKEW_SECONDS,
        max_responses: int = DEFAULT_MAX_RESPONSES,
        seen_at: float | None = None,
    ) -> dict[str, Any]:
        now = float(seen_at if seen_at is not None else time.time())
        skew = float(max_reference_skew_seconds)
        if now <= 0:
            raise ValueError("seen_at must be positive")
        if not math.isfinite(skew) or skew < 0:
            raise ValueError("max_reference_skew_seconds must be finite and >= 0")

        tables = self._tables()
        if "research_intelligence_event_responses" not in tables:
            return {
                "status": "waiting_for_event_response_table",
                "responses_considered": 0,
                "providers_considered": 0,
                "pairs_ready": 0,
                "inserted": 0,
                "updated": 0,
                "missing_reference_start": 0,
                "missing_reference_end": 0,
                "quality_rejected": 0,
            }
        if "research_us_market_reference" not in tables:
            return {
                "status": "waiting_for_us_market_reference_table",
                "responses_considered": 0,
                "providers_considered": 0,
                "pairs_ready": 0,
                "inserted": 0,
                "updated": 0,
                "missing_reference_start": 0,
                "missing_reference_end": 0,
                "quality_rejected": 0,
            }

        clean_sources: list[str] = []
        for value in source_ids:
            source_id = _clean(value).lower()
            if source_id not in SERIES_BY_SOURCE:
                raise ValueError(f"unsupported US market reference source: {value!r}")
            if source_id not in clean_sources:
                clean_sources.append(source_id)

        responses = self.conn.execute(
            """SELECT event_id,event_type,source_id,exchange,market,horizon_label,
                      horizon_seconds,event_ts,target_ts,return_pct,provider_id
               FROM research_intelligence_event_responses
               WHERE provider_id=?
               ORDER BY event_ts DESC,event_id,exchange,market,horizon_seconds
               LIMIT ?""",
            (EVENT_RESPONSE_PROVIDER_ID, max(1, min(20000, int(max_responses)))),
        ).fetchall()

        providers_considered = 0
        missing_start = 0
        missing_end = 0
        quality_rejected = 0
        quality_rejection_reasons: dict[str, int] = defaultdict(int)
        ready: list[tuple[Any, ...]] = []

        for response in responses:
            event_ts = float(response["event_ts"])
            target_ts = float(response["target_ts"])
            horizon = float(response["horizon_seconds"])
            coin_return = float(response["return_pct"])
            if (
                event_ts <= 0
                or target_ts < event_ts
                or horizon <= 0
                or not math.isfinite(coin_return)
            ):
                continue
            response_id = _response_id(response)
            for source_id in clean_sources:
                providers = self._providers_at_or_after(
                    source_id=source_id,
                    target=event_ts,
                    max_skew_seconds=skew,
                )
                if not providers:
                    missing_start += 1
                    continue
                for reference_provider in providers:
                    providers_considered += 1
                    start = self._first_reference_at_or_after(
                        source_id=source_id,
                        provider_id=reference_provider,
                        target=event_ts,
                        max_skew_seconds=skew,
                    )
                    if start is None:
                        missing_start += 1
                        continue
                    end = self._first_reference_at_or_after(
                        source_id=source_id,
                        provider_id=reference_provider,
                        target=target_ts,
                        max_skew_seconds=skew,
                    )
                    if end is None:
                        missing_end += 1
                        continue
                    if reference_provider in QUALITY_GATED_REFERENCE_PROVIDERS:
                        quality = assess_us_market_reference_path(
                            self.conn,
                            source_id=source_id,
                            provider_id=reference_provider,
                            start_at=event_ts,
                            end_at=target_ts,
                            max_endpoint_skew_seconds=skew,
                        )
                        if not bool(quality.get("eligible_for_pairing")):
                            quality_rejected += 1
                            reasons = quality.get("reasons")
                            if isinstance(reasons, list) and reasons:
                                for reason in reasons:
                                    quality_rejection_reasons[_clean(reason).lower() or "unknown"] += 1
                            else:
                                quality_rejection_reasons["unknown"] += 1
                            continue

                    start_value = float(start["value"])
                    end_value = float(end["value"])
                    if start_value <= 0 or end_value <= 0:
                        continue
                    start_rights = _clean(start["data_rights"])
                    end_rights = _clean(end["data_rights"])
                    if not start_rights or not end_rights:
                        continue
                    reference_return = (end_value / start_value - 1.0) * 100.0
                    if not math.isfinite(reference_return):
                        continue
                    pair_id = _pair_id(
                        response_id=response_id,
                        reference_source_id=source_id,
                        reference_provider_id=reference_provider,
                    )
                    ready.append(
                        (
                            pair_id,
                            response_id,
                            _clean(response["event_id"]),
                            _clean(response["event_type"]).upper(),
                            _clean(response["source_id"]).lower(),
                            _clean(response["exchange"]).lower(),
                            _clean(response["market"]).upper(),
                            _clean(response["horizon_label"]).lower(),
                            horizon,
                            event_ts,
                            target_ts,
                            _clean(response["provider_id"]).lower(),
                            coin_return,
                            source_id,
                            _clean(start["series"]),
                            reference_provider,
                            reference_return,
                            float(start["observed_at"]),
                            float(end["observed_at"]),
                            start_value,
                            end_value,
                            float(start["observed_at"]) - event_ts,
                            float(end["observed_at"]) - target_ts,
                            _clean(start["session_state"]),
                            _clean(end["session_state"]),
                            _clean(start["latency_class"]),
                            _clean(end["latency_class"]),
                            None if start["delayed_seconds"] is None else float(start["delayed_seconds"]),
                            None if end["delayed_seconds"] is None else float(end["delayed_seconds"]),
                            start_rights,
                            end_rights,
                            PAIR_VERSION,
                        )
                    )

        inserted = 0
        updated = 0
        for values in ready:
            exists = self.conn.execute(
                "SELECT 1 FROM research_intelligence_event_response_us_pairs WHERE pair_id=?",
                (values[0],),
            ).fetchone()
            self.conn.execute(
                """INSERT INTO research_intelligence_event_response_us_pairs(
                    pair_id,response_id,event_id,event_type,event_source_id,exchange,market,
                    horizon_label,horizon_seconds,event_ts,target_ts,coin_provider_id,coin_return_pct,
                    reference_source_id,reference_series,reference_provider_id,reference_return_pct,
                    reference_start_at,reference_end_at,reference_start_value,reference_end_value,
                    start_skew_seconds,end_skew_seconds,start_session_state,end_session_state,
                    start_latency_class,end_latency_class,start_delayed_seconds,end_delayed_seconds,
                    start_data_rights,end_data_rights,pair_version,first_seen_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(pair_id) DO UPDATE SET
                    coin_return_pct=excluded.coin_return_pct,
                    reference_return_pct=excluded.reference_return_pct,
                    reference_start_at=excluded.reference_start_at,
                    reference_end_at=excluded.reference_end_at,
                    reference_start_value=excluded.reference_start_value,
                    reference_end_value=excluded.reference_end_value,
                    start_skew_seconds=excluded.start_skew_seconds,
                    end_skew_seconds=excluded.end_skew_seconds,
                    start_session_state=excluded.start_session_state,
                    end_session_state=excluded.end_session_state,
                    start_latency_class=excluded.start_latency_class,
                    end_latency_class=excluded.end_latency_class,
                    start_delayed_seconds=excluded.start_delayed_seconds,
                    end_delayed_seconds=excluded.end_delayed_seconds,
                    start_data_rights=excluded.start_data_rights,
                    end_data_rights=excluded.end_data_rights,
                    updated_at=excluded.updated_at""",
                (*values, now, now),
            )
            if exists:
                updated += 1
            else:
                inserted += 1
        self.conn.commit()
        result: dict[str, Any] = {
            "status": "ok",
            "responses_considered": len(responses),
            "providers_considered": providers_considered,
            "pairs_ready": len(ready),
            "inserted": inserted,
            "updated": updated,
            "missing_reference_start": missing_start,
            "missing_reference_end": missing_end,
            "quality_rejected": quality_rejected,
        }
        if quality_rejection_reasons:
            result["quality_rejection_reasons"] = dict(sorted(quality_rejection_reasons.items()))
        return result

    def refresh_sensitivity(self, *, now: float | None = None) -> dict[str, int]:
        current = float(now if now is not None else time.time())
        if current <= 0:
            raise ValueError("now must be positive")
        rows = self.conn.execute(
            """SELECT * FROM research_intelligence_event_response_us_pairs
               ORDER BY event_ts,pair_id"""
        ).fetchall()
        grouped: dict[tuple[str, ...], list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            key = (
                _clean(row["event_type"]).upper(),
                _clean(row["event_source_id"]).lower(),
                _clean(row["exchange"]).lower(),
                _clean(row["market"]).upper(),
                _clean(row["horizon_label"]).lower(),
                _clean(row["coin_provider_id"]).lower(),
                _clean(row["reference_source_id"]).lower(),
                _clean(row["reference_series"]),
                _clean(row["reference_provider_id"]).lower(),
            )
            grouped[key].append(row)

        self.conn.execute("DELETE FROM research_intelligence_event_response_us_sensitivity")
        for key, group in grouped.items():
            coin = [float(row["coin_return_pct"]) for row in group]
            reference = [float(row["reference_return_pct"]) for row in group]
            count = len(group)
            mean_coin = statistics.fmean(coin)
            mean_reference = statistics.fmean(reference)
            coin_centered = [value - mean_coin for value in coin]
            reference_centered = [value - mean_reference for value in reference]
            covariance = statistics.fmean(
                left * right for left, right in zip(coin_centered, reference_centered)
            )
            variance_coin = statistics.fmean(value * value for value in coin_centered)
            variance_reference = statistics.fmean(value * value for value in reference_centered)
            stdev_coin = math.sqrt(max(0.0, variance_coin))
            stdev_reference = math.sqrt(max(0.0, variance_reference))
            beta = covariance / variance_reference if count >= 2 and variance_reference > _EPSILON else None
            correlation = (
                covariance / math.sqrt(variance_coin * variance_reference)
                if count >= 2 and variance_coin > _EPSILON and variance_reference > _EPSILON
                else None
            )
            same_direction = sum(1 for c, r in zip(coin, reference) if c * r > 0)
            positive_coin = [c for c, r in zip(coin, reference) if r > 0]
            negative_coin = [c for c, r in zip(coin, reference) if r < 0]
            ref_positive = len(positive_coin)
            ref_negative = len(negative_coin)
            ref_zero = count - ref_positive - ref_negative
            event_ids = {_clean(row["event_id"]) for row in group}
            event_times = [float(row["event_ts"]) for row in group]
            start_skews = [float(row["start_skew_seconds"]) for row in group]
            end_skews = [float(row["end_skew_seconds"]) for row in group]
            self.conn.execute(
                """INSERT INTO research_intelligence_event_response_us_sensitivity(
                    event_type,event_source_id,exchange,market,horizon_label,coin_provider_id,
                    reference_source_id,reference_series,reference_provider_id,sample_count,
                    distinct_event_count,mean_coin_return_pct,mean_reference_return_pct,
                    stdev_coin_return_pct,stdev_reference_return_pct,covariance,beta,correlation,
                    same_direction_count,same_direction_rate_pct,reference_positive_count,
                    reference_negative_count,reference_zero_count,mean_coin_when_reference_positive,
                    mean_coin_when_reference_negative,mean_abs_coin_return_pct,earliest_event_ts,
                    latest_event_ts,mean_start_skew_seconds,mean_end_skew_seconds,readiness,
                    score_authority,promotion_eligible,updated_at,sensitivity_version
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    *key,
                    count,
                    len(event_ids),
                    mean_coin,
                    mean_reference,
                    stdev_coin,
                    stdev_reference,
                    covariance,
                    beta,
                    correlation,
                    same_direction,
                    same_direction / count * 100.0,
                    ref_positive,
                    ref_negative,
                    ref_zero,
                    statistics.fmean(positive_coin) if positive_coin else None,
                    statistics.fmean(negative_coin) if negative_coin else None,
                    statistics.fmean(abs(value) for value in coin),
                    min(event_times),
                    max(event_times),
                    statistics.fmean(start_skews),
                    statistics.fmean(end_skews),
                    _readiness(count),
                    0,
                    0,
                    current,
                    SENSITIVITY_VERSION,
                ),
            )
        self.conn.commit()
        return {"source_pairs": len(rows), "groups": len(grouped)}

    def sensitivity(
        self,
        *,
        market: str,
        event_type: str = "",
        horizon_label: str = "",
        reference_source_id: str = "",
        exchange: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clean_market = _clean(market).upper()
        if not clean_market:
            raise ValueError("market is required")
        clauses = ["market=?"]
        params: list[Any] = [clean_market]
        if event_type:
            clauses.append("event_type=?")
            params.append(_clean(event_type).upper())
        if horizon_label:
            clauses.append("horizon_label=?")
            params.append(_clean(horizon_label).lower())
        if exchange:
            clauses.append("exchange=?")
            params.append(_clean(exchange).lower())
        if reference_source_id:
            source_id = _clean(reference_source_id).lower()
            if source_id not in SERIES_BY_SOURCE:
                raise ValueError(f"unsupported US market reference source: {reference_source_id!r}")
            clauses.append("reference_source_id=?")
            params.append(source_id)
        params.append(max(1, min(2000, int(limit))))
        rows = self.conn.execute(
            f"""SELECT * FROM research_intelligence_event_response_us_sensitivity
                WHERE {' AND '.join(clauses)}
                ORDER BY sample_count DESC,latest_event_ts DESC LIMIT ?""",
            tuple(params),
        ).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["score_authority"] = False
            item["promotion_eligible"] = False
            item["confidence"] = None
            item["confidence_status"] = "not_promoted"
            item["reference_direction_semantics"] = "raw_not_inverted"
            output.append(item)
        return output

    def run(
        self,
        *,
        source_ids: Iterable[str] = DEFAULT_REFERENCE_SOURCES,
        max_reference_skew_seconds: float = DEFAULT_MAX_REFERENCE_SKEW_SECONDS,
        max_responses: int = DEFAULT_MAX_RESPONSES,
        now: float | None = None,
    ) -> dict[str, Any]:
        current = float(now if now is not None else time.time())
        pairs = self.build_pairs(
            source_ids=source_ids,
            max_reference_skew_seconds=max_reference_skew_seconds,
            max_responses=max_responses,
            seen_at=current,
        )
        sensitivity = self.refresh_sensitivity(now=current)
        return {
            "ok": True,
            "status": str(pairs.get("status") or "ok"),
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "network_requests": 0,
            "missing_values_coerced_to_zero": False,
            "pairs": pairs,
            "sensitivity": sensitivity,
        }
