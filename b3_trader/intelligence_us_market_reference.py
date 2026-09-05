from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

SERIES_BY_SOURCE = {
    "us_nasdaq_composite": "NASDAQ_COMPOSITE",
    "us_sp500": "SP500",
    "us_cboe_vix": "VIX",
}

_ALLOWED_SESSION_STATES = {"pre_market", "regular", "after_hours", "closed", "unknown"}
_ALLOWED_LATENCY_CLASSES = {"realtime", "delayed", "end_of_day", "unknown"}
DEFAULT_RETENTION_SECONDS = 180 * 86400


def _finite(value: Any, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _https_url(value: str, *, name: str) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{name} must be an https URL")
    return text


@dataclass(frozen=True)
class UsMarketReferenceObservation:
    observation_id: str
    source_id: str
    series: str
    observed_at: float
    received_at: float
    value: float
    change_pct: float | None
    session_state: str
    latency_class: str
    delayed_seconds: float | None
    provider_id: str
    provider_url: str
    data_rights: str
    attributes: dict[str, Any]
    version: int = 1

    def freshness_seconds(self, *, now: float | None = None) -> float | None:
        current = float(now if now is not None else time.time())
        if self.observed_at <= 0 or self.observed_at > current:
            return None
        return max(0.0, current - self.observed_at)


def normalize_us_market_reference_observation(
    *,
    source_id: str,
    observed_at: float,
    value: float,
    provider_id: str,
    provider_url: str,
    data_rights: str,
    received_at: float | None = None,
    change_pct: float | None = None,
    session_state: str = "unknown",
    latency_class: str = "unknown",
    delayed_seconds: float | None = None,
    attributes: dict[str, Any] | None = None,
    version: int = 1,
) -> UsMarketReferenceObservation:
    clean_source = str(source_id or "").strip().lower()
    series = SERIES_BY_SOURCE.get(clean_source)
    if not series:
        raise ValueError(f"unsupported US market reference source: {source_id!r}")
    observed = _finite(observed_at, name="observed_at")
    if observed <= 0:
        raise ValueError("observed_at must be positive")
    received = _finite(received_at if received_at is not None else time.time(), name="received_at")
    if received <= 0:
        raise ValueError("received_at must be positive")
    level = _finite(value, name="value")
    if level <= 0:
        raise ValueError("value must be positive")
    clean_provider = str(provider_id or "").strip().lower()
    if not clean_provider:
        raise ValueError("provider_id is required")
    clean_rights = str(data_rights or "").strip()
    if not clean_rights:
        raise ValueError("data_rights is required; do not ingest an unreviewed market feed")
    provider_link = _https_url(provider_url, name="provider_url")
    clean_session = str(session_state or "unknown").strip().lower()
    if clean_session not in _ALLOWED_SESSION_STATES:
        raise ValueError(f"invalid session_state: {session_state!r}")
    clean_latency = str(latency_class or "unknown").strip().lower()
    if clean_latency not in _ALLOWED_LATENCY_CLASSES:
        raise ValueError(f"invalid latency_class: {latency_class!r}")
    normalized_change = None if change_pct is None else _finite(change_pct, name="change_pct")
    normalized_delay = None if delayed_seconds is None else _finite(delayed_seconds, name="delayed_seconds")
    if normalized_delay is not None and normalized_delay < 0:
        raise ValueError("delayed_seconds must be >= 0")
    normalized_version = int(version)
    if normalized_version < 1:
        raise ValueError("version must be >= 1")
    observed_ms = int(round(observed * 1000.0))
    observation_id = f"{clean_source}:{clean_provider}:{observed_ms}"
    return UsMarketReferenceObservation(
        observation_id=observation_id,
        source_id=clean_source,
        series=series,
        observed_at=observed,
        received_at=received,
        value=level,
        change_pct=normalized_change,
        session_state=clean_session,
        latency_class=clean_latency,
        delayed_seconds=normalized_delay,
        provider_id=clean_provider,
        provider_url=provider_link,
        data_rights=clean_rights,
        attributes=dict(attributes or {}),
        version=normalized_version,
    )


class UsMarketReferenceStore:
    """Local time-series store for Nasdaq/S&P 500/VIX reference observations.

    No HTTP fetcher is owned here. A future provider adapter must supply explicit
    provider identity, timestamp semantics and data-rights metadata.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_us_market_reference (
                observation_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                series TEXT NOT NULL,
                observed_at REAL NOT NULL,
                received_at REAL NOT NULL,
                value REAL NOT NULL,
                change_pct REAL,
                session_state TEXT NOT NULL,
                latency_class TEXT NOT NULL,
                delayed_seconds REAL,
                provider_id TEXT NOT NULL,
                provider_url TEXT NOT NULL,
                data_rights TEXT NOT NULL,
                attributes_json TEXT NOT NULL DEFAULT '{}',
                version INTEGER NOT NULL DEFAULT 1,
                first_seen_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_research_us_market_reference_series_ts
                ON research_us_market_reference(source_id, observed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_research_us_market_reference_provider_ts
                ON research_us_market_reference(provider_id, observed_at DESC);
            """
        )
        self.conn.commit()

    def ingest(
        self,
        observations: Iterable[UsMarketReferenceObservation],
        *,
        seen_at: float | None = None,
        retention_seconds: float = DEFAULT_RETENTION_SECONDS,
    ) -> dict[str, int]:
        now = float(seen_at if seen_at is not None else time.time())
        received = 0
        inserted = 0
        updated = 0
        for item in observations:
            if SERIES_BY_SOURCE.get(item.source_id) != item.series:
                raise ValueError(f"series/source mismatch: {item.source_id} / {item.series}")
            received += 1
            exists = self.conn.execute(
                "SELECT 1 FROM research_us_market_reference WHERE observation_id=?",
                (item.observation_id,),
            ).fetchone()
            self.conn.execute(
                """INSERT INTO research_us_market_reference(
                    observation_id,source_id,series,observed_at,received_at,value,change_pct,
                    session_state,latency_class,delayed_seconds,provider_id,provider_url,data_rights,
                    attributes_json,version,first_seen_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(observation_id) DO UPDATE SET
                    received_at=excluded.received_at,value=excluded.value,
                    change_pct=excluded.change_pct,session_state=excluded.session_state,
                    latency_class=excluded.latency_class,delayed_seconds=excluded.delayed_seconds,
                    provider_url=excluded.provider_url,data_rights=excluded.data_rights,
                    attributes_json=excluded.attributes_json,
                    version=CASE WHEN excluded.version>research_us_market_reference.version THEN excluded.version ELSE research_us_market_reference.version END,
                    updated_at=excluded.updated_at""",
                (
                    item.observation_id,
                    item.source_id,
                    item.series,
                    item.observed_at,
                    item.received_at,
                    item.value,
                    item.change_pct,
                    item.session_state,
                    item.latency_class,
                    item.delayed_seconds,
                    item.provider_id,
                    item.provider_url,
                    item.data_rights,
                    json.dumps(item.attributes, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str),
                    item.version,
                    now,
                    now,
                ),
            )
            if exists:
                updated += 1
            else:
                inserted += 1
        cutoff = now - max(0.0, float(retention_seconds))
        if cutoff > 0:
            self.conn.execute(
                "DELETE FROM research_us_market_reference WHERE observed_at<?",
                (cutoff,),
            )
        self.conn.commit()
        return {"received": received, "inserted": inserted, "updated": updated}

    @staticmethod
    def _decode(row: sqlite3.Row, *, now: float) -> dict[str, Any]:
        result = dict(row)
        try:
            result["attributes"] = json.loads(str(result.pop("attributes_json") or "{}"))
        except (json.JSONDecodeError, TypeError, ValueError):
            result["attributes"] = {}
        observed = float(result.get("observed_at") or 0.0)
        result["freshness_seconds"] = max(0.0, now - observed) if 0 < observed <= now else None
        return result

    def latest(
        self,
        source_id: str,
        *,
        now: float | None = None,
        max_age_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        current = float(now if now is not None else time.time())
        row = self.conn.execute(
            """SELECT * FROM research_us_market_reference
               WHERE source_id=? ORDER BY observed_at DESC LIMIT 1""",
            (str(source_id or "").strip().lower(),),
        ).fetchone()
        if row is None:
            return None
        result = self._decode(row, now=current)
        freshness = result.get("freshness_seconds")
        if max_age_seconds is not None and (
            freshness is None or float(freshness) > max(0.0, float(max_age_seconds))
        ):
            return None
        return result

    def nearest(
        self,
        source_id: str,
        target_ts: float,
        *,
        max_skew_seconds: float = 120.0,
        provider_id: str = "",
        now: float | None = None,
    ) -> dict[str, Any] | None:
        target = float(target_ts)
        skew = max(0.0, float(max_skew_seconds))
        clean_source = str(source_id or "").strip().lower()
        clean_provider = str(provider_id or "").strip().lower()
        if clean_provider:
            row = self.conn.execute(
                """SELECT * FROM research_us_market_reference
                   WHERE source_id=? AND provider_id=? AND observed_at BETWEEN ? AND ?
                   ORDER BY ABS(observed_at-?), observed_at LIMIT 1""",
                (clean_source, clean_provider, target - skew, target + skew, target),
            ).fetchone()
        else:
            row = self.conn.execute(
                """SELECT * FROM research_us_market_reference
                   WHERE source_id=? AND observed_at BETWEEN ? AND ?
                   ORDER BY ABS(observed_at-?), observed_at LIMIT 1""",
                (clean_source, target - skew, target + skew, target),
            ).fetchone()
        if row is None:
            return None
        return self._decode(row, now=float(now if now is not None else time.time()))

    def window(
        self,
        source_id: str,
        start_ts: float,
        end_ts: float,
        *,
        limit: int = 5000,
        provider_id: str = "",
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        start = float(start_ts)
        end = float(end_ts)
        if end < start:
            start, end = end, start
        clean_source = str(source_id or "").strip().lower()
        clean_provider = str(provider_id or "").strip().lower()
        if clean_provider:
            rows = self.conn.execute(
                """SELECT * FROM research_us_market_reference
                   WHERE source_id=? AND provider_id=? AND observed_at BETWEEN ? AND ?
                   ORDER BY observed_at LIMIT ?""",
                (clean_source, clean_provider, start, end, max(1, min(20000, int(limit)))),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM research_us_market_reference
                   WHERE source_id=? AND observed_at BETWEEN ? AND ?
                   ORDER BY observed_at LIMIT ?""",
                (clean_source, start, end, max(1, min(20000, int(limit)))),
            ).fetchall()
        current = float(now if now is not None else time.time())
        return [self._decode(row, now=current) for row in rows]

    def aligned_return(
        self,
        source_id: str,
        start_ts: float,
        end_ts: float,
        *,
        max_skew_seconds: float = 120.0,
        provider_id: str = "",
        now: float | None = None,
    ) -> dict[str, Any] | None:
        clean_provider = str(provider_id or "").strip().lower()
        start = self.nearest(
            source_id,
            start_ts,
            max_skew_seconds=max_skew_seconds,
            provider_id=clean_provider,
            now=now,
        )
        if not start:
            return None
        selected_provider = clean_provider or str(start.get("provider_id") or "").strip().lower()
        if not selected_provider:
            return None
        end = self.nearest(
            source_id,
            end_ts,
            max_skew_seconds=max_skew_seconds,
            provider_id=selected_provider,
            now=now,
        )
        if not end or str(end.get("provider_id") or "").strip().lower() != selected_provider:
            return None
        start_value = float(start.get("value") or 0.0)
        end_value = float(end.get("value") or 0.0)
        if start_value <= 0 or end_value <= 0:
            return None
        return {
            "source_id": str(source_id or "").strip().lower(),
            "series": start.get("series"),
            "start_observed_at": float(start["observed_at"]),
            "end_observed_at": float(end["observed_at"]),
            "start_value": start_value,
            "end_value": end_value,
            "return_pct": (end_value / start_value - 1.0) * 100.0,
            "start_skew_seconds": abs(float(start["observed_at"]) - float(start_ts)),
            "end_skew_seconds": abs(float(end["observed_at"]) - float(end_ts)),
            "provider_id": selected_provider,
            "latency_class_start": start.get("latency_class"),
            "latency_class_end": end.get("latency_class"),
        }
