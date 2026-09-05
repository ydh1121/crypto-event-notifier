from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .intelligence_us_index_intraday import (
    TWELVE_DATA_AUTHORITY,
    TWELVE_DATA_DATA_RIGHTS,
    TWELVE_DATA_PROVIDER_ID,
    TWELVE_DATA_TIME_SERIES_URL,
    IndexBar,
    TwelveDataIndexClient,
)
from .intelligence_us_market_reference import (
    UsMarketReferenceObservation,
    UsMarketReferenceStore,
    normalize_us_market_reference_observation,
)

MARKET_TO_SOURCE_ID = {
    "SP500": "us_sp500",
    "NASDAQ_COMPOSITE": "us_nasdaq_composite",
    "VIX": "us_cboe_vix",
}
DEFAULT_INTERVAL = "1min"
DEFAULT_OUTPUTSIZE = 32


def _bar_timestamp(bar: IndexBar) -> float:
    stamp = str(bar.datetime or "").strip()
    if not stamp:
        raise ValueError("Twelve Data bar datetime is missing")
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid Twelve Data bar datetime: {stamp!r}") from exc

    if parsed.tzinfo is None:
        zone_name = str(bar.exchange_timezone or "").strip()
        if not zone_name:
            raise ValueError("naive Twelve Data bar datetime requires exchange_timezone")
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(zone_name))
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown Twelve Data exchange_timezone: {zone_name!r}") from exc
    return parsed.timestamp()


def _observation_from_bar(bar: IndexBar, *, received_at: float) -> UsMarketReferenceObservation:
    market_id = str(bar.market_id or "").strip().upper()
    source_id = MARKET_TO_SOURCE_ID.get(market_id)
    if not source_id:
        raise ValueError(f"unsupported Twelve Data market_id: {bar.market_id!r}")

    observed_at = _bar_timestamp(bar)
    if observed_at > float(received_at) + 120.0:
        raise ValueError("Twelve Data bar timestamp is unexpectedly in the future")

    return normalize_us_market_reference_observation(
        source_id=source_id,
        observed_at=observed_at,
        received_at=received_at,
        value=bar.close,
        provider_id=TWELVE_DATA_PROVIDER_ID,
        provider_url=TWELVE_DATA_TIME_SERIES_URL,
        data_rights=TWELVE_DATA_DATA_RIGHTS,
        change_pct=None,
        session_state="unknown",
        latency_class="unknown",
        delayed_seconds=None,
        attributes={
            "authority": TWELVE_DATA_AUTHORITY,
            "market_id": market_id,
            "requested_symbol": bar.requested_symbol,
            "provider_symbol": bar.provider_symbol,
            "interval": bar.interval,
            "bar_datetime": bar.datetime,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "exchange": bar.exchange,
            "exchange_timezone": bar.exchange_timezone,
            "instrument_type": bar.instrument_type,
            "missing_values_coerced_to_zero": False,
            "score_authority": False,
            "promotion_eligible": False,
        },
    )


class UsMarketReferenceCaptureService:
    """Persist bounded real U.S. index bars for Phase 5 shadow research.

    Construction initializes the reference table even when no external credential
    is configured. Missing credentials never trigger network access and are not a
    Phase 5 source failure. Real provider failures are surfaced as partial so the
    caller can fail closed without affecting order paths.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        client: TwelveDataIndexClient | Any | None = None,
        interval: str = DEFAULT_INTERVAL,
        outputsize: int = DEFAULT_OUTPUTSIZE,
    ) -> None:
        self.conn = conn
        self.store = UsMarketReferenceStore(conn)
        self.client = client or TwelveDataIndexClient()
        self.interval = str(interval or "").strip().lower()
        self.outputsize = max(1, min(32, int(outputsize)))

    def run_once(
        self,
        *,
        now: float | None = None,
        network_enabled: bool = False,
    ) -> dict[str, Any]:
        current = float(now if now is not None else time.time())
        result: dict[str, Any] = {
            "ok": True,
            "status": "not_requested",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "score_authority": False,
            "promotion_eligible": False,
            "missing_values_coerced_to_zero": False,
            "provider_id": TWELVE_DATA_PROVIDER_ID,
            "credential_status": str(getattr(self.client, "credential_status", "missing")),
            "credential_exposed": False,
            "interval": self.interval,
            "outputsize": self.outputsize,
            "network_requests": 0,
            "markets_requested": list(MARKET_TO_SOURCE_ID),
            "markets_succeeded": [],
            "bars_received": 0,
            "observations_received": 0,
            "inserted": 0,
            "updated": 0,
            "capture_failures": 0,
            "errors": {},
        }
        if not network_enabled:
            result["status"] = "network_disabled"
            return result

        if result["credential_status"] != "ready":
            result["status"] = "credential_missing"
            return result

        observations: list[UsMarketReferenceObservation] = []
        errors: dict[str, str] = {}
        succeeded: list[str] = []
        for market_id in MARKET_TO_SOURCE_ID:
            result["network_requests"] = int(result["network_requests"]) + 1
            try:
                bars = list(
                    self.client.fetch_time_series(
                        market_id,
                        interval=self.interval,
                        outputsize=self.outputsize,
                    )
                )
                normalized = [_observation_from_bar(bar, received_at=current) for bar in bars]
            except Exception as exc:
                errors[market_id] = f"{type(exc).__name__}: {exc}"[:300]
                result["capture_failures"] = int(result["capture_failures"]) + 1
                continue
            observations.extend(normalized)
            succeeded.append(market_id)
            result["bars_received"] = int(result["bars_received"]) + len(bars)

        ingest = self.store.ingest(observations, seen_at=current)
        result["markets_succeeded"] = succeeded
        result["observations_received"] = int(ingest["received"])
        result["inserted"] = int(ingest["inserted"])
        result["updated"] = int(ingest["updated"])
        result["errors"] = errors
        if int(result["capture_failures"]) > 0:
            result["ok"] = False
            result["status"] = "partial"
        else:
            result["status"] = "ok"
        return result
