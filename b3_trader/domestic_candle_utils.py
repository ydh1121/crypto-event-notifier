from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


def parse_candle_ts(row: dict[str, Any]) -> float:
    raw = str(row.get("candle_date_time_utc") or "").strip()
    if not raw:
        return 0.0
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        try:
            return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return 0.0


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
