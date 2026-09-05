from __future__ import annotations

import math
import os
import sqlite3
import time
from typing import Any

import requests

from .intelligence_us_market_reference import (
    UsMarketReferenceObservation,
    UsMarketReferenceStore,
    normalize_us_market_reference_observation,
)

MASSIVE_INDICES_SNAPSHOT_URL = "https://api.massive.com/v3/snapshot/indices"
MASSIVE_PROVIDER_ID = "massive_indices_snapshot"
MASSIVE_DATA_RIGHTS = "provider_subscription_indices_internal_research_only_unless_plan_allows_distribution"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_ATTEMPTS = 2
DELAYED_SECONDS = 15 * 60.0
FUTURE_TOLERANCE_SECONDS = 60.0

REQUIRED_TICKERS = {
    "I:COMP": ("us_nasdaq_composite", "Nasdaq"),
    "I:SPX": ("us_sp500", "Cboe"),
    "I:VIX": ("us_cboe_vix", "Cboe"),
}

_SESSION_STATE = {
    "regular_trading": "regular",
    "early_trading": "pre_market",
    "late_trading": "after_hours",
    "closed": "closed",
}

_LATENCY = {
    "REAL-TIME": ("realtime", 0.0),
    "DELAYED": ("delayed", DELAYED_SECONDS),
}


def _finite(value: object, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _observed_at_ns(value: object) -> float:
    try:
        raw = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Massive last_updated must be an integer nanosecond timestamp") from exc
    if raw <= 0:
        raise ValueError("Massive last_updated must be positive")
    return raw / 1_000_000_000.0


class MassiveIndicesSnapshotClient:
    """Minimal Massive indices snapshot client with header-only credential use."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        session: Any | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        attempts: int = DEFAULT_ATTEMPTS,
    ) -> None:
        configured = api_key if api_key is not None else os.getenv("MASSIVE_API_KEY", "")
        self.api_key = str(configured or "").strip()
        self.session = session or requests.Session()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.attempts = max(1, min(3, int(attempts)))

    @property
    def credential_status(self) -> str:
        return "ready" if self.api_key else "missing"

    def fetch_snapshot(self, ticker: str) -> dict[str, Any]:
        clean_ticker = str(ticker or "").strip().upper()
        if clean_ticker not in REQUIRED_TICKERS:
            raise ValueError(f"unsupported required Massive index ticker: {ticker!r}")
        if self.credential_status != "ready":
            raise ValueError("Massive API credential is missing")

        response = None
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = self.session.get(
                    MASSIVE_INDICES_SNAPSHOT_URL,
                    params={"ticker": clean_ticker, "limit": 1},
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "User-Agent": "crypto-event-notifier-phase5/1.0",
                        "Accept": "application/json",
                    },
                    timeout=self.timeout_seconds,
                )
                status_code = int(getattr(response, "status_code", 200))
                if status_code in {409, 429, 500, 502, 503, 504}:
                    last_error = RuntimeError(f"Massive indices API transient HTTP {status_code}")
                    if attempt + 1 < self.attempts:
                        time.sleep(0.25 * (attempt + 1))
                        continue
                response.raise_for_status()
                break
            except (requests.ConnectionError, requests.Timeout, RuntimeError) as exc:
                last_error = exc
                if attempt + 1 >= self.attempts:
                    raise
                time.sleep(0.25 * (attempt + 1))
        else:
            if last_error is not None:
                raise last_error
            raise RuntimeError("Massive indices API request failed")

        if response is None:
            raise RuntimeError("Massive indices API returned no response")
        body = response.json()
        if not isinstance(body, dict) or str(body.get("status") or "").upper() != "OK":
            raise ValueError("Massive indices snapshot response status is not OK")
        rows = body.get("results")
        if not isinstance(rows, list):
            raise ValueError("Massive indices snapshot response is missing results")
        matches = [row for row in rows if isinstance(row, dict) and str(row.get("ticker") or "") == clean_ticker]
        if len(matches) != 1:
            raise ValueError(f"Massive indices snapshot must return exactly one row for {clean_ticker}")
        row = dict(matches[0])
        if row.get("error") or row.get("message"):
            raise ValueError(
                f"Massive indices snapshot rejected {clean_ticker}: "
                f"{str(row.get('error') or '')} {str(row.get('message') or '')}".strip()
            )
        return row


def normalize_massive_snapshot(
    row: dict[str, Any],
    *,
    received_at: float,
) -> UsMarketReferenceObservation:
    ticker = str(row.get("ticker") or "").strip().upper()
    mapping = REQUIRED_TICKERS.get(ticker)
    if mapping is None:
        raise ValueError(f"unexpected Massive index ticker: {ticker!r}")
    source_id, feed = mapping
    timeframe = str(row.get("timeframe") or "").strip().upper()
    latency = _LATENCY.get(timeframe)
    if latency is None:
        raise ValueError(f"unsupported Massive index timeframe: {timeframe!r}")
    latency_class, delayed_seconds = latency
    market_status = str(row.get("market_status") or "").strip().lower()
    session_state = _SESSION_STATE.get(market_status)
    if session_state is None:
        raise ValueError(f"unsupported Massive index market_status: {market_status!r}")

    observed_at = _observed_at_ns(row.get("last_updated"))
    received = _finite(received_at, name="received_at")
    if received <= 0:
        raise ValueError("received_at must be positive")
    if observed_at > received + FUTURE_TOLERANCE_SECONDS:
        raise ValueError("Massive last_updated is implausibly ahead of received_at")
    value = _finite(row.get("value"), name="value")
    if value <= 0:
        raise ValueError("Massive index value must be positive")

    session = row.get("session")
    session_dict = dict(session) if isinstance(session, dict) else {}
    raw_change = session_dict.get("change_percent")
    change_pct = None if raw_change is None else _finite(raw_change, name="session.change_percent")

    return normalize_us_market_reference_observation(
        source_id=source_id,
        observed_at=observed_at,
        received_at=received,
        value=value,
        change_pct=change_pct,
        session_state=session_state,
        latency_class=latency_class,
        delayed_seconds=delayed_seconds,
        provider_id=MASSIVE_PROVIDER_ID,
        provider_url=MASSIVE_INDICES_SNAPSHOT_URL,
        data_rights=MASSIVE_DATA_RIGHTS,
        attributes={
            "ticker": ticker,
            "name": str(row.get("name") or ""),
            "feed": feed,
            "provider_timeframe": timeframe,
            "provider_market_status": market_status,
            "provider_last_updated_ns": int(row.get("last_updated")),
            "session": session_dict,
            "credential_exposed": False,
            "score_authority": False,
            "provider_contract": "massive_indices_snapshot_v3",
        },
    )


class MassiveUsMarketReferenceCaptureService:
    """Atomically capture COMP/SPX/VIX snapshots into the Phase 5 reference store."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        client: MassiveIndicesSnapshotClient | None = None,
    ) -> None:
        self.conn = conn
        self.client = client or MassiveIndicesSnapshotClient()
        self.store = UsMarketReferenceStore(conn)

    def run_once(self, *, now: float | None = None, network_enabled: bool = False) -> dict[str, Any]:
        current = float(now if now is not None else time.time())
        result: dict[str, Any] = {
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "network_enabled": bool(network_enabled),
            "credential_status": self.client.credential_status,
            "credential_exposed": False,
            "required_tickers": list(REQUIRED_TICKERS),
            "network_requests": 0,
            "observations_received": 0,
            "observations_inserted": 0,
            "observations_updated": 0,
            "capture_failures": 0,
        }
        if not network_enabled:
            result["status"] = "network_disabled"
            return result
        if self.client.credential_status != "ready":
            result["status"] = "credential_missing"
            return result

        observations: list[UsMarketReferenceObservation] = []
        try:
            for ticker in REQUIRED_TICKERS:
                result["network_requests"] += 1
                row = self.client.fetch_snapshot(ticker)
                observations.append(normalize_massive_snapshot(row, received_at=current))
            if {item.source_id for item in observations} != {value[0] for value in REQUIRED_TICKERS.values()}:
                raise ValueError("Massive snapshot set is incomplete")
        except Exception as exc:
            result["capture_failures"] = 1
            result["status"] = "partial"
            result["error"] = f"{type(exc).__name__}: {exc}"[:300]
            return result

        ingest = self.store.ingest(observations, seen_at=current)
        result["observations_received"] = int(ingest["received"])
        result["observations_inserted"] = int(ingest["inserted"])
        result["observations_updated"] = int(ingest["updated"])
        result["status"] = "ok"
        return result
