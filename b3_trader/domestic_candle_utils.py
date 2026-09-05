from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

KST = timezone(timedelta(hours=9))


def _parse_clock(raw: str, *, tz: timezone) -> float:
    text = str(raw or "").strip()
    if not text:
        return 0.0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tz)
        return parsed.timestamp()
    except ValueError:
        try:
            return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=tz).timestamp()
        except ValueError:
            return 0.0


def parse_candle_ts(row: dict[str, Any]) -> float:
    """Parse the candle start time from either UTC or KST quotation shapes."""
    utc_value = _parse_clock(str(row.get("candle_date_time_utc") or ""), tz=timezone.utc)
    if utc_value > 0:
        return utc_value
    # Bithumb-compatible quotation responses may expose the KST field even when
    # the UTC field is absent/blank. Treat a naive KST clock explicitly as KST.
    return _parse_clock(str(row.get("candle_date_time_kst") or ""), tz=KST)


def opening_price_at_or_after(
    candles: Iterable[dict[str, Any]],
    *,
    target_ts: float,
    max_delay_seconds: int = 1200,
) -> dict[str, Any]:
    """Return the first traded minute candle at/after a scheduled market open."""
    candidates: list[tuple[float, dict[str, Any]]] = []
    for row in candles:
        if not isinstance(row, dict):
            continue
        ts = parse_candle_ts(row)
        if ts <= 0 or ts < float(target_ts):
            continue
        try:
            opening = float(row.get("opening_price") or 0.0)
        except (TypeError, ValueError):
            opening = 0.0
        if opening <= 0:
            continue
        delay = ts - float(target_ts)
        if delay > max(60, int(max_delay_seconds)):
            continue
        candidates.append(
            (
                ts,
                {
                    "price": opening,
                    "candle_ts": ts,
                    "distance_seconds": delay,
                    "price_basis": "first_opening_price_at_or_after_trade_open",
                },
            )
        )
    if not candidates:
        return {"found": False, "price": 0.0, "candle_ts": 0.0, "distance_seconds": None}
    candidates.sort(key=lambda item: item[0])
    return {"found": True, **candidates[0][1]}


def nearest_opening_price(
    candles: Iterable[dict[str, Any]],
    *,
    target_ts: float,
    tolerance_seconds: int = 180,
) -> dict[str, Any]:
    candidates: list[tuple[float, dict[str, Any]]] = []
    for row in candles:
        if not isinstance(row, dict):
            continue
        ts = parse_candle_ts(row)
        if ts <= 0:
            continue
        try:
            opening = float(row.get("opening_price") or 0.0)
        except (TypeError, ValueError):
            opening = 0.0
        if opening <= 0:
            continue
        distance = abs(ts - float(target_ts))
        if distance <= max(60, int(tolerance_seconds)):
            candidates.append(
                (
                    distance,
                    {
                        "price": opening,
                        "candle_ts": ts,
                        "distance_seconds": distance,
                        "price_basis": "opening_price",
                    },
                )
            )
    if not candidates:
        return {"found": False, "price": 0.0, "candle_ts": 0.0, "distance_seconds": None}
    candidates.sort(key=lambda item: (item[0], item[1]["candle_ts"]))
    return {"found": True, **candidates[0][1]}


def quote_rate_at_or_before(
    candles: Iterable[dict[str, Any]],
    *,
    target_ts: float,
    max_lag_seconds: int = 180,
) -> dict[str, Any]:
    """Read a quote/KRW rate without using a candle timestamp after target_ts."""

    candidate: tuple[float, float, str] | None = None
    for row in candles:
        if not isinstance(row, dict):
            continue
        ts = parse_candle_ts(row)
        if ts <= 0 or ts > target_ts:
            continue
        price = 0.0
        basis = ""
        for key in ("trade_price", "opening_price"):
            try:
                price = float(row.get(key) or 0.0)
            except (TypeError, ValueError):
                price = 0.0
            if price > 0:
                basis = key
                break
        if price <= 0:
            continue
        if candidate is None or ts > candidate[0]:
            candidate = (ts, price, basis)
    if candidate is None:
        return {"found": False, "rate": 0.0, "candle_ts": 0.0, "lag_seconds": None}
    lag = max(0.0, float(target_ts) - candidate[0])
    if lag > max(60, int(max_lag_seconds)):
        return {"found": False, "rate": 0.0, "candle_ts": candidate[0], "lag_seconds": lag}
    return {
        "found": True,
        "rate": candidate[1],
        "candle_ts": candidate[0],
        "lag_seconds": lag,
        "price_basis": candidate[2],
    }
