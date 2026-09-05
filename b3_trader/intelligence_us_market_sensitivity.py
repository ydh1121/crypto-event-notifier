from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import statistics
import time
from collections import defaultdict
from typing import Any, Iterable

from .intelligence_us_market_path_quality import assess_us_market_reference_path
from .intelligence_us_market_reference import SERIES_BY_SOURCE

DEFAULT_REFERENCE_SOURCES = tuple(SERIES_BY_SOURCE)
DEFAULT_MAX_REFERENCE_SKEW_SECONDS = 120.0
DEFAULT_MAX_REACTIONS = 1000
QUALITY_GATED_REFERENCE_PROVIDERS = {"massive_indices_1m"}
PAIR_VERSION = 1
SENSITIVITY_VERSION = 1
_EPSILON = 1e-12


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _pair_id(*, reaction_id: str, reference_source_id: str, reference_provider_id: str) -> str:
    payload = json.dumps(
        [reaction_id, reference_source_id, reference_provider_id],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "iusp:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class IntelligenceUsMarketSensitivityStore:
    """Pair event-conditioned coin reactions with US equity/risk references.

    The stored reference return is raw. VIX is not inverted and no series is
    promoted into EventScore/RegimeScore/RelativeStrength here. Provider identity,
    timing skew, latency and data-rights evidence remain explicit so later gates
    can decide which samples are eligible for scoring.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_intelligence_us_reference_pairs (
                pair_id TEXT PRIMARY KEY,
                reaction_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                market TEXT NOT NULL,
                window TEXT NOT NULL,
                horizon_seconds INTEGER NOT NULL,
                anchor_at REAL NOT NULL,
                coin_provider_id TEXT NOT NULL,
                exchange TEXT NOT NULL,
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
                UNIQUE(reaction_id, reference_source_id, reference_provider_id)
            );
            CREATE INDEX IF NOT EXISTS idx_intelligence_us_pairs_market
                ON research_intelligence_us_reference_pairs(market,event_type,window,anchor_at DESC);
            CREATE INDEX IF NOT EXISTS idx_intelligence_us_pairs_reference
                ON research_intelligence_us_reference_pairs(reference_source_id,reference_provider_id,anchor_at DESC);

            CREATE TABLE IF NOT EXISTS research_intelligence_us_sensitivity (
                event_type TEXT NOT NULL,
                market TEXT NOT NULL,
                window TEXT NOT NULL,
                coin_provider_id TEXT NOT NULL,
                exchange TEXT NOT NULL,
                reference_source_id TEXT NOT NULL,
                reference_series TEXT NOT NULL,
                reference_provider_id TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
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
                earliest_anchor_at REAL NOT NULL,
                latest_anchor_at REAL NOT NULL,
                mean_start_skew_seconds REAL NOT NULL,
                mean_end_skew_seconds REAL NOT NULL,
                updated_at REAL NOT NULL,
                sensitivity_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(
                    event_type,market,window,coin_provider_id,exchange,
                    reference_source_id,reference_provider_id
                )
            );
            CREATE INDEX IF NOT EXISTS idx_intelligence_us_sensitivity_lookup
                ON research_intelligence_us_sensitivity(market,event_type,window,sample_count DESC);
            """
        )
        self.conn.commit()

    def _tables(self) -> set[str]:
        return {
            str(row[0])
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

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
               WHERE source_id=? AND provider_id=? AND observed_at>=? AND observed_at<=?
               ORDER BY observed_at ASC LIMIT 1""",
            (source_id, provider_id, target, target + max_skew_seconds),
        ).fetchone()

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
        return [str(row[0]).strip().lower() for row in rows if str(row[0] or "").strip()]

    def build_pairs(
        self,
        *,
        source_ids: Iterable[str] = DEFAULT_REFERENCE_SOURCES,
        max_reference_skew_seconds: float = DEFAULT_MAX_REFERENCE_SKEW_SECONDS,
        max_reactions: int = DEFAULT_MAX_REACTIONS,
        seen_at: float | None = None,
    ) -> dict[str, Any]:
        now = float(seen_at if seen_at is not None else time.time())
        skew = float(max_reference_skew_seconds)
        if now <= 0:
            raise ValueError("seen_at must be positive")
        if not math.isfinite(skew) or skew < 0:
            raise ValueError("max_reference_skew_seconds must be finite and >= 0")
        tables = self._tables()
        if "research_intelligence_reactions" not in tables or "research_us_market_reference" not in tables:
            return {"reactions_considered": 0, "providers_considered": 0, "pairs_ready": 0, "inserted": 0, "updated": 0}

        clean_sources: list[str] = []
        for value in source_ids:
            source_id = _clean(value).lower()
            if source_id not in SERIES_BY_SOURCE:
                raise ValueError(f"unsupported US market reference source: {value!r}")
            if source_id not in clean_sources:
                clean_sources.append(source_id)

        reactions = self.conn.execute(
            """SELECT reaction_id,event_id,event_type,market,window,horizon_seconds,anchor_at,
                      provider_id,exchange,forward_return_pct
               FROM research_intelligence_reactions
               ORDER BY anchor_at DESC,reaction_id LIMIT ?""",
            (max(1, min(10000, int(max_reactions))),),
        ).fetchall()
        providers_considered = 0
        quality_rejected = 0
        quality_rejection_reasons: dict[str, int] = defaultdict(int)
        ready: list[tuple[Any, ...]] = []

        for reaction in reactions:
            anchor = float(reaction["anchor_at"])
            horizon = int(reaction["horizon_seconds"])
            target_end = anchor + horizon
            for source_id in clean_sources:
                for reference_provider in self._providers_at_or_after(
                    source_id=source_id,
                    target=anchor,
                    max_skew_seconds=skew,
                ):
                    providers_considered += 1
                    start = self._first_reference_at_or_after(
                        source_id=source_id,
                        provider_id=reference_provider,
                        target=anchor,
                        max_skew_seconds=skew,
                    )
                    end = self._first_reference_at_or_after(
                        source_id=source_id,
                        provider_id=reference_provider,
                        target=target_end,
                        max_skew_seconds=skew,
                    )
                    if start is None or end is None:
                        continue
                    if reference_provider in QUALITY_GATED_REFERENCE_PROVIDERS:
                        quality = assess_us_market_reference_path(
                            self.conn,
                            source_id=source_id,
                            provider_id=reference_provider,
                            start_at=anchor,
                            end_at=target_end,
                            max_endpoint_skew_seconds=skew,
                        )
                        if not bool(quality.get("eligible_for_pairing")):
                            quality_rejected += 1
                            reasons = quality.get("reasons")
                            if isinstance(reasons, list) and reasons:
                                for reason in reasons:
                                    clean_reason = _clean(reason).lower() or "unknown"
                                    quality_rejection_reasons[clean_reason] += 1
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
                    pair_id = _pair_id(
                        reaction_id=str(reaction["reaction_id"]),
                        reference_source_id=source_id,
                        reference_provider_id=reference_provider,
                    )
                    ready.append(
                        (
                            pair_id,
                            str(reaction["reaction_id"]),
                            str(reaction["event_id"]),
                            str(reaction["event_type"]),
                            str(reaction["market"]),
                            str(reaction["window"]),
                            horizon,
                            anchor,
                            str(reaction["provider_id"]),
                            str(reaction["exchange"]),
                            float(reaction["forward_return_pct"]),
                            source_id,
                            str(start["series"]),
                            reference_provider,
                            reference_return,
                            float(start["observed_at"]),
                            float(end["observed_at"]),
                            start_value,
                            end_value,
                            float(start["observed_at"]) - anchor,
                            float(end["observed_at"]) - target_end,
                            str(start["session_state"]),
                            str(end["session_state"]),
                            str(start["latency_class"]),
                            str(end["latency_class"]),
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
                "SELECT 1 FROM research_intelligence_us_reference_pairs WHERE pair_id=?",
                (values[0],),
            ).fetchone()
            self.conn.execute(
                """INSERT INTO research_intelligence_us_reference_pairs(
                    pair_id,reaction_id,event_id,event_type,market,window,horizon_seconds,anchor_at,
                    coin_provider_id,exchange,coin_return_pct,reference_source_id,reference_series,
                    reference_provider_id,reference_return_pct,reference_start_at,reference_end_at,
                    reference_start_value,reference_end_value,start_skew_seconds,end_skew_seconds,
                    start_session_state,end_session_state,start_latency_class,end_latency_class,
                    start_delayed_seconds,end_delayed_seconds,start_data_rights,end_data_rights,
                    pair_version,first_seen_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    pair_version=CASE WHEN excluded.pair_version>research_intelligence_us_reference_pairs.pair_version
                                      THEN excluded.pair_version ELSE research_intelligence_us_reference_pairs.pair_version END,
                    updated_at=excluded.updated_at""",
                (*values, now, now),
            )
            if exists:
                updated += 1
            else:
                inserted += 1
        self.conn.commit()
        result: dict[str, Any] = {
            "reactions_considered": len(reactions),
            "providers_considered": providers_considered,
            "pairs_ready": len(ready),
            "inserted": inserted,
            "updated": updated,
        }
        if quality_rejected:
            result["quality_rejected"] = quality_rejected
            result["quality_rejection_reasons"] = dict(sorted(quality_rejection_reasons.items()))
        return result

    def refresh_sensitivity(self, *, now: float | None = None) -> dict[str, int]:
        current = float(now if now is not None else time.time())
        if current <= 0:
            raise ValueError("now must be positive")
        if "research_intelligence_us_reference_pairs" not in self._tables():
            return {"source_pairs": 0, "groups": 0}
        rows = self.conn.execute(
            """SELECT * FROM research_intelligence_us_reference_pairs
               ORDER BY anchor_at,pair_id"""
        ).fetchall()
        grouped: dict[tuple[str, ...], list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            key = (
                str(row["event_type"]),
                str(row["market"]),
                str(row["window"]),
                str(row["coin_provider_id"]),
                str(row["exchange"]),
                str(row["reference_source_id"]),
                str(row["reference_series"]),
                str(row["reference_provider_id"]),
            )
            grouped[key].append(row)

        self.conn.execute("DELETE FROM research_intelligence_us_sensitivity")
        for key, group in grouped.items():
            coin = [float(row["coin_return_pct"]) for row in group]
            reference = [float(row["reference_return_pct"]) for row in group]
            count = len(group)
            mean_coin = statistics.fmean(coin)
            mean_reference = statistics.fmean(reference)
            coin_centered = [value - mean_coin for value in coin]
            reference_centered = [value - mean_reference for value in reference]
            covariance = statistics.fmean(
                [left * right for left, right in zip(coin_centered, reference_centered)]
            )
            variance_coin = statistics.fmean([value * value for value in coin_centered])
            variance_reference = statistics.fmean([value * value for value in reference_centered])
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
            anchors = [float(row["anchor_at"]) for row in group]
            start_skews = [float(row["start_skew_seconds"]) for row in group]
            end_skews = [float(row["end_skew_seconds"]) for row in group]
            self.conn.execute(
                """INSERT INTO research_intelligence_us_sensitivity(
                    event_type,market,window,coin_provider_id,exchange,
                    reference_source_id,reference_series,reference_provider_id,
                    sample_count,mean_coin_return_pct,mean_reference_return_pct,
                    stdev_coin_return_pct,stdev_reference_return_pct,covariance,beta,correlation,
                    same_direction_count,same_direction_rate_pct,
                    reference_positive_count,reference_negative_count,reference_zero_count,
                    mean_coin_when_reference_positive,mean_coin_when_reference_negative,
                    earliest_anchor_at,latest_anchor_at,mean_start_skew_seconds,mean_end_skew_seconds,
                    updated_at,sensitivity_version
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    *key,
                    count,
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
                    min(anchors),
                    max(anchors),
                    statistics.fmean(start_skews),
                    statistics.fmean(end_skews),
                    current,
                    SENSITIVITY_VERSION,
                ),
            )
        self.conn.commit()
        return {"source_pairs": len(rows), "groups": len(grouped)}

    @staticmethod
    def _decode_sensitivity(row: sqlite3.Row, *, now: float) -> dict[str, Any]:
        result = dict(row)
        latest = float(result.get("latest_anchor_at") or 0.0)
        result["recency_seconds"] = max(0.0, now - latest) if 0 < latest <= now else None
        result["confidence"] = None
        result["confidence_status"] = "not_promoted"
        result["reference_direction_semantics"] = "raw_not_inverted"
        return result

    def sensitivity(
        self,
        *,
        market: str,
        event_type: str = "",
        window: str = "",
        reference_source_id: str = "",
        now: float | None = None,
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
        if window:
            clauses.append("window=?")
            params.append(_clean(window).lower())
        if reference_source_id:
            clean_source = _clean(reference_source_id).lower()
            if clean_source not in SERIES_BY_SOURCE:
                raise ValueError(f"unsupported US market reference source: {reference_source_id!r}")
            clauses.append("reference_source_id=?")
            params.append(clean_source)
        params.append(max(1, min(2000, int(limit))))
        rows = self.conn.execute(
            f"""SELECT * FROM research_intelligence_us_sensitivity
                WHERE {' AND '.join(clauses)}
                ORDER BY sample_count DESC,latest_anchor_at DESC LIMIT ?""",
            tuple(params),
        ).fetchall()
        current = float(now if now is not None else time.time())
        return [self._decode_sensitivity(row, now=current) for row in rows]

    def run(
        self,
        *,
        source_ids: Iterable[str] = DEFAULT_REFERENCE_SOURCES,
        max_reference_skew_seconds: float = DEFAULT_MAX_REFERENCE_SKEW_SECONDS,
        max_reactions: int = DEFAULT_MAX_REACTIONS,
        now: float | None = None,
    ) -> dict[str, Any]:
        current = float(now if now is not None else time.time())
        pairs = self.build_pairs(
            source_ids=source_ids,
            max_reference_skew_seconds=max_reference_skew_seconds,
            max_reactions=max_reactions,
            seen_at=current,
        )
        sensitivity = self.refresh_sensitivity(now=current)
        return {"pairs": pairs, "sensitivity": sensitivity}
