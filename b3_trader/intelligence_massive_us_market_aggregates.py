from __future__ import annotations

import math
import os
import sqlite3
import time
from typing import Any

import requests

from .intelligence_massive_us_market_reference import REQUIRED_TICKERS
from .intelligence_us_market_reference import (
    UsMarketReferenceObservation,
    UsMarketReferenceStore,
    normalize_us_market_reference_observation,
)

MASSIVE_AGGREGATE_URL_TEMPLATE = (
    "https://api.massive.com/v2/aggs/ticker/{ticker}/range/1/minute/{from_ms}/{to_ms}"
)
MASSIVE_AGGREGATE_PROVIDER_ID = "massive_indices_1m"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_ATTEMPTS = 2
DEFAULT_LIMIT = 5000
MAX_LIMIT = 10000
MAX_WINDOW_SECONDS = 48 * 3600.0
BAR_SECONDS = 60.0
FUTURE_TOLERANCE_SECONDS = 60.0

_PLAN_LATENCY = {
    "basic": ("end_of_day", None),
    "starter": ("delayed", 15 * 60.0),
    "advanced": ("realtime", 0.0),
}


def _finite(value: object, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _plan(value: object) -> str:
    clean = str(value or "").strip().lower()
    return clean if clean in _PLAN_LATENCY else ""


def _bar_start_seconds(value: object) -> float:
    try:
        raw = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Massive aggregate t must be an integer millisecond timestamp") from exc
    if raw <= 0:
        raise ValueError("Massive aggregate t must be positive")
    if raw % 60_000 != 0:
        raise ValueError("Massive 1m aggregate t must be minute-aligned")
    return raw / 1000.0


class MassiveIndicesAggregateClient:
    """Bounded Massive indices 1-minute aggregate REST client.

    The plan is explicit because the aggregate payload itself does not carry the
    subscription latency class. We never infer real-time entitlement from the
    mere presence of an API key.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        plan: str | None = None,
        session: Any | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        attempts: int = DEFAULT_ATTEMPTS,
        limit: int = DEFAULT_LIMIT,
    ) -> None:
        configured_key = api_key if api_key is not None else os.getenv("MASSIVE_API_KEY", "")
        configured_plan = plan if plan is not None else os.getenv("MASSIVE_INDICES_PLAN", "")
        self.api_key = str(configured_key or "").strip()
        self.plan = _plan(configured_plan)
        self.session = session or requests.Session()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.attempts = max(1, min(3, int(attempts)))
        self.limit = max(1, min(MAX_LIMIT, int(limit)))

    @property
    def credential_status(self) -> str:
        return "ready" if self.api_key else "missing"

    @property
    def plan_status(self) -> str:
        return "ready" if self.plan else "missing_or_invalid"

    @property
    def latency_contract(self) -> tuple[str, float | None]:
        if not self.plan:
            raise ValueError("Massive indices plan is missing or invalid")
        return _PLAN_LATENCY[self.plan]

    def fetch_1m(self, ticker: str, *, start_at: float, end_at: float) -> list[dict[str, Any]]:
        clean_ticker = str(ticker or "").strip().upper()
        if clean_ticker not in REQUIRED_TICKERS:
            raise ValueError(f"unsupported required Massive index ticker: {ticker!r}")
        if self.credential_status != "ready":
            raise ValueError("Massive API credential is missing")
        if self.plan_status != "ready":
            raise ValueError("Massive indices plan is missing or invalid")

        start = _finite(start_at, name="start_at")
        end = _finite(end_at, name="end_at")
        if start <= 0 or end <= 0 or end < start:
            raise ValueError("start_at/end_at must be positive and ordered")
        if end - start > MAX_WINDOW_SECONDS:
            raise ValueError("Massive 1m aggregate request exceeds bounded 48-hour window")

        from_ms = int(math.floor(start * 1000.0))
        to_ms = int(math.floor(end * 1000.0))
        url = MASSIVE_AGGREGATE_URL_TEMPLATE.format(
            ticker=clean_ticker,
            from_ms=from_ms,
            to_ms=to_ms,
        )
        response = None
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = self.session.get(
                    url,
                    params={"sort": "asc", "limit": self.limit},
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "User-Agent": "crypto-event-notifier-phase5/1.0",
                        "Accept": "application/json",
                    },
                    timeout=self.timeout_seconds,
                )
                status_code = int(getattr(response, "status_code", 200))
                if status_code in {409, 429, 500, 502, 503, 504}:
                    last_error = RuntimeError(f"Massive indices aggregate transient HTTP {status_code}")
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
            raise RuntimeError("Massive indices aggregate request failed")

        if response is None:
            raise RuntimeError("Massive indices aggregate API returned no response")
        body = response.json()
        if not isinstance(body, dict) or str(body.get("status") or "").upper() != "OK":
            raise ValueError("Massive indices aggregate response status is not OK")
        if str(body.get("ticker") or "").strip().upper() != clean_ticker:
            raise ValueError("Massive indices aggregate ticker mismatch")
        rows = body.get("results")
        if rows is None:
            return []
        if not isinstance(rows, list):
            raise ValueError("Massive indices aggregate response results must be a list")
        if len(rows) > self.limit:
            raise ValueError("Massive indices aggregate response exceeded requested limit")
        return [dict(row) for row in rows if isinstance(row, dict)]


def normalize_massive_1m_bar(
    ticker: str,
    row: dict[str, Any],
    *,
    received_at: float,
    plan: str,
) -> UsMarketReferenceObservation:
    clean_ticker = str(ticker or "").strip().upper()
    mapping = REQUIRED_TICKERS.get(clean_ticker)
    if mapping is None:
        raise ValueError(f"unexpected Massive index ticker: {ticker!r}")
    source_id, feed = mapping
    clean_plan = _plan(plan)
    if not clean_plan:
        raise ValueError("Massive indices plan is missing or invalid")
    latency_class, delayed_seconds = _PLAN_LATENCY[clean_plan]

    bar_start_at = _bar_start_seconds(row.get("t"))
    bar_end_at = bar_start_at + BAR_SECONDS
    received = _finite(received_at, name="received_at")
    if received <= 0:
        raise ValueError("received_at must be positive")
    if bar_end_at > received + FUTURE_TOLERANCE_SECONDS:
        raise ValueError("Massive aggregate bar close is implausibly ahead of received_at")

    open_value = _finite(row.get("o"), name="o")
    high_value = _finite(row.get("h"), name="h")
    low_value = _finite(row.get("l"), name="l")
    close_value = _finite(row.get("c"), name="c")
    if min(open_value, high_value, low_value, close_value) <= 0:
        raise ValueError("Massive aggregate OHLC values must be positive")
    if low_value > min(open_value, close_value) or high_value < max(open_value, close_value):
        raise ValueError("Massive aggregate OHLC ordering is invalid")
    if high_value < low_value:
        raise ValueError("Massive aggregate high must be >= low")

    available_at = None
    if delayed_seconds is not None:
        available_at = bar_end_at + float(delayed_seconds)

    provider_url = MASSIVE_AGGREGATE_URL_TEMPLATE.format(
        ticker=clean_ticker,
        from_ms="{from_ms}",
        to_ms="{to_ms}",
    )
    data_rights = (
        f"provider_subscription_indices_{clean_plan}_internal_research_only_unless_plan_allows_distribution"
    )
    return normalize_us_market_reference_observation(
        source_id=source_id,
        observed_at=bar_end_at,
        received_at=received,
        value=close_value,
        change_pct=None,
        session_state="unknown",
        latency_class=latency_class,
        delayed_seconds=delayed_seconds,
        provider_id=MASSIVE_AGGREGATE_PROVIDER_ID,
        provider_url=provider_url,
        data_rights=data_rights,
        attributes={
            "ticker": clean_ticker,
            "feed": feed,
            "provider_plan": clean_plan,
            "bar_timespan": "1m",
            "bar_start_at": bar_start_at,
            "bar_end_at": bar_end_at,
            "available_at": available_at,
            "open": open_value,
            "high": high_value,
            "low": low_value,
            "close": close_value,
            "provider_timestamp_ms": int(row.get("t")),
            "credential_exposed": False,
            "score_authority": False,
            "provider_contract": "massive_indices_custom_bars_v2_1m",
        },
    )


class MassiveUsMarketAggregateCaptureService:
    """Atomically capture bounded 1-minute COMP/SPX/VIX reference paths."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        client: MassiveIndicesAggregateClient | None = None,
    ) -> None:
        self.conn = conn
        self.client = client or MassiveIndicesAggregateClient()
        self.store = UsMarketReferenceStore(conn)

    def run_window(
        self,
        *,
        start_at: float,
        end_at: float,
        now: float | None = None,
        network_enabled: bool = False,
    ) -> dict[str, Any]:
        current = float(now if now is not None else time.time())
        start = _finite(start_at, name="start_at")
        end = _finite(end_at, name="end_at")
        result: dict[str, Any] = {
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "network_enabled": bool(network_enabled),
            "credential_status": self.client.credential_status,
            "plan_status": self.client.plan_status,
            "provider_plan": self.client.plan,
            "credential_exposed": False,
            "required_tickers": list(REQUIRED_TICKERS),
            "window_start_at": start,
            "window_end_at": end,
            "network_requests": 0,
            "bars_received": 0,
            "observations_inserted": 0,
            "observations_updated": 0,
            "capture_failures": 0,
        }
        if start <= 0 or end <= 0 or end < start:
            result["status"] = "invalid_window"
            return result
        if end - start > MAX_WINDOW_SECONDS:
            result["status"] = "window_too_large"
            return result
        if not network_enabled:
            result["status"] = "network_disabled"
            return result
        if self.client.credential_status != "ready":
            result["status"] = "credential_missing"
            return result
        if self.client.plan_status != "ready":
            result["status"] = "plan_missing_or_invalid"
            return result

        observations: list[UsMarketReferenceObservation] = []
        try:
            for ticker in REQUIRED_TICKERS:
                result["network_requests"] += 1
                rows = self.client.fetch_1m(ticker, start_at=start, end_at=end)
                for row in rows:
                    observations.append(
                        normalize_massive_1m_bar(
                            ticker,
                            row,
                            received_at=current,
                            plan=self.client.plan,
                        )
                    )
        except Exception as exc:
            result["capture_failures"] = 1
            result["status"] = "partial"
            result["error"] = f"{type(exc).__name__}: {exc}"[:300]
            return result

        ingest = self.store.ingest(observations, seen_at=current)
        result["bars_received"] = int(ingest["received"])
        result["observations_inserted"] = int(ingest["inserted"])
        result["observations_updated"] = int(ingest["updated"])
        result["status"] = "ok" if observations else "ok_no_bars"
        return result

    def run_recent(
        self,
        *,
        now: float | None = None,
        lookback_seconds: float = 3600.0,
        network_enabled: bool = False,
    ) -> dict[str, Any]:
        current = float(now if now is not None else time.time())
        lookback = max(BAR_SECONDS, min(MAX_WINDOW_SECONDS, float(lookback_seconds)))
        # End on the last fully closed minute. This avoids storing an in-progress
        # bar even when a provider endpoint happens to expose one.
        end_at = math.floor((current - BAR_SECONDS) / BAR_SECONDS) * BAR_SECONDS
        start_at = max(BAR_SECONDS, end_at - lookback)
        return self.run_window(
            start_at=start_at,
            end_at=end_at,
            now=current,
            network_enabled=network_enabled,
        )
