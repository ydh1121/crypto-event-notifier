from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .exchange_public import PublicExchangeAdapter
from .market_ohlcv_store import MarketOhlcvStore


@dataclass(frozen=True)
class TimeframeSpec:
    name: str
    seconds: int
    minute_unit: int | None


TIMEFRAMES = (
    TimeframeSpec("1m", 60, 1),
    TimeframeSpec("5m", 300, 5),
    TimeframeSpec("15m", 900, 15),
    TimeframeSpec("1h", 3600, 60),
    TimeframeSpec("4h", 14400, 240),
    TimeframeSpec("1d", 86400, None),
)
MAX_FETCH_COUNT = 200
MIN_FETCH_COUNT = 2
REQUEST_GAP_SECONDS = 0.12
MAX_SOURCE_ATTEMPTS = 3
RATE_LIMIT_RETRY_SECONDS = 1.05
MAX_RATE_LIMIT_RETRY_SECONDS = 3.0


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _http_status(exc: Exception) -> int:
    response = getattr(exc, "response", None)
    try:
        return int(getattr(response, "status_code", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _rate_limit_retry_delay(exc: Exception, attempt: int) -> float:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    retry_after = None
    if headers is not None:
        try:
            retry_after = _num(headers.get("Retry-After"))
        except (AttributeError, TypeError):
            retry_after = None
    if retry_after is not None and retry_after > 0:
        return min(MAX_RATE_LIMIT_RETRY_SECONDS, max(RATE_LIMIT_RETRY_SECONDS, retry_after))
    return min(MAX_RATE_LIMIT_RETRY_SECONDS, RATE_LIMIT_RETRY_SECONDS * max(1, int(attempt)))


def candle_ts(row: dict[str, Any]) -> float | None:
    text = str(row.get("candle_date_time_utc") or "").strip()
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).timestamp()
        except ValueError:
            pass
    raw = _num(row.get("timestamp"))
    if raw is None or raw <= 0:
        return None
    return raw / 1000.0 if raw > 10_000_000_000 else raw


def normalize_candles(
    rows: list[dict[str, Any]],
    *,
    exchange: str,
    market: str,
    timeframe: TimeframeSpec,
    now: float,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        ts = candle_ts(row)
        open_price = _num(row.get("opening_price"))
        high_price = _num(row.get("high_price"))
        low_price = _num(row.get("low_price"))
        close_price = _num(row.get("trade_price"))
        base_volume = _num(row.get("candle_acc_trade_volume"))
        quote_volume = _num(row.get("candle_acc_trade_price"))
        if (
            ts is None
            or open_price is None
            or high_price is None
            or low_price is None
            or close_price is None
            or min(open_price, high_price, low_price, close_price) <= 0
        ):
            continue
        normalized.append(
            {
                "exchange": str(exchange),
                "market": str(market),
                "timeframe": timeframe.name,
                "candle_ts": ts,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "base_volume": max(0.0, float(base_volume or 0.0)),
                "quote_volume": max(0.0, float(quote_volume or 0.0)),
                "is_closed": bool(now >= ts + timeframe.seconds),
                "source": "public_rest",
                "received_at": now,
                "schema_version": 1,
            }
        )
    normalized.sort(key=lambda item: float(item["candle_ts"]))
    return normalized


class MarketOhlcvCollector:
    """Fetch a small bridge window and keep each market/timeframe bounded locally."""

    def __init__(
        self,
        store: MarketOhlcvStore,
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.sleep_fn = sleep_fn
        self.monotonic_fn = monotonic_fn
        self._last_request_at = 0.0

    def _pace(self) -> None:
        now = self.monotonic_fn()
        wait = REQUEST_GAP_SECONDS - (now - self._last_request_at)
        if self._last_request_at > 0 and wait > 0:
            self.sleep_fn(wait)
        self._last_request_at = self.monotonic_fn()

    @staticmethod
    def fetch_count(*, latest_ts: float, now: float, seconds: int) -> int:
        if latest_ts <= 0:
            return MAX_FETCH_COUNT
        missing = int(math.ceil(max(0.0, float(now) - float(latest_ts)) / max(1, int(seconds)))) + 2
        return max(MIN_FETCH_COUNT, min(MAX_FETCH_COUNT, missing))

    def _fetch_once(
        self,
        adapter: PublicExchangeAdapter,
        market: str,
        spec: TimeframeSpec,
        count: int,
    ) -> list[dict[str, Any]]:
        self._pace()
        if spec.minute_unit is None:
            return adapter.candles_days(market, count=count)
        return adapter.candles_minutes(market, unit=spec.minute_unit, count=count)

    def collect_market(
        self,
        adapter: PublicExchangeAdapter,
        market: str,
        *,
        now: float | None = None,
    ) -> dict[str, Any]:
        collected_at = float(now or time.time())
        result: dict[str, Any] = {
            "exchange": adapter.exchange,
            "market": market,
            "requests": 0,
            "rate_limit_retries": 0,
            "rows_written": 0,
            "rows_pruned": 0,
            "failures": 0,
            "timeframes": {},
        }
        for spec in TIMEFRAMES:
            latest = self.store.latest_ts(adapter.exchange, market, spec.name)
            count = self.fetch_count(latest_ts=latest, now=collected_at, seconds=spec.seconds)
            attempts = 0
            rate_limit_retries = 0
            try:
                raw: list[dict[str, Any]] = []
                for attempt in range(1, MAX_SOURCE_ATTEMPTS + 1):
                    attempts += 1
                    result["requests"] += 1
                    try:
                        raw = self._fetch_once(adapter, market, spec, count)
                        break
                    except Exception as exc:
                        if _http_status(exc) == 429 and attempt < MAX_SOURCE_ATTEMPTS:
                            rate_limit_retries += 1
                            result["rate_limit_retries"] += 1
                            self.sleep_fn(_rate_limit_retry_delay(exc, attempt))
                            continue
                        raise
                rows = normalize_candles(
                    raw if isinstance(raw, list) else [],
                    exchange=adapter.exchange,
                    market=market,
                    timeframe=spec,
                    now=collected_at,
                )
                written = self.store.upsert_rows(rows)
                pruned = self.store.prune(adapter.exchange, market, spec.name)
                result["rows_written"] += written
                result["rows_pruned"] += pruned
                result["timeframes"][spec.name] = {
                    "status": "collected" if rows else "no_candles",
                    "requested": count,
                    "attempts": attempts,
                    "rate_limit_retries": rate_limit_retries,
                    "received": len(raw) if isinstance(raw, list) else 0,
                    "stored": written,
                    "pruned": pruned,
                    "latest_before": latest,
                    "latest_after": max([float(row["candle_ts"]) for row in rows], default=latest),
                }
            except Exception as exc:
                result["failures"] += 1
                result["timeframes"][spec.name] = {
                    "status": "source_error",
                    "requested": count,
                    "attempts": attempts,
                    "rate_limit_retries": rate_limit_retries,
                    "http_status": _http_status(exc) or None,
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                    "latest_before": latest,
                }
        result["ok"] = result["failures"] == 0
        result["paper_only"] = True
        result["can_place_orders"] = False
        return result
