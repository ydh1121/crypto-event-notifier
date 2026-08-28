from __future__ import annotations

from typing import Any, Iterable

from .dex_launch_sources import DexCandle


PRE_WINDOWS = {
    "t7d": 7 * 86400,
    "t5d": 5 * 86400,
    "t3d": 3 * 86400,
    "t1d": 86400,
    "t6h": 6 * 3600,
    "t1h": 3600,
}
POST_WINDOWS = {
    "p5m": 5 * 60,
    "p1h": 3600,
    "p6h": 6 * 3600,
    "p24h": 86400,
    "p3d": 3 * 86400,
    "p7d": 7 * 86400,
}
FEATURE_VERSION = 1


def _pct(after: float, before: float) -> float | None:
    if before <= 0 or after <= 0:
        return None
    return round((after / before - 1.0) * 100.0, 6)


def _closest(
    candles: Iterable[DexCandle],
    target: float,
    *,
    mode: str,
    tolerance: float,
) -> DexCandle | None:
    rows = [row for row in candles if row.ts > 0 and row.close > 0]
    if mode == "before":
        candidates = [row for row in rows if row.ts <= target and target - row.ts <= tolerance]
        return max(candidates, key=lambda row: row.ts) if candidates else None
    candidates = [row for row in rows if row.ts >= target and row.ts - target <= tolerance]
    return min(candidates, key=lambda row: row.ts) if candidates else None


def _point(row: DexCandle | None, target: float) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "target_ts": float(target),
        "candle_ts": float(row.ts),
        "price": float(row.open),
        "interval_seconds": int(row.interval_seconds),
    }


def _exact_minute_point(point: dict[str, Any] | None) -> bool:
    if not isinstance(point, dict):
        return False
    return bool(
        int(point.get("interval_seconds") or 0) == 60
        and abs(float(point.get("candle_ts") or 0.0) - float(point.get("target_ts") or 0.0)) <= 1.0
    )


def domestic_window_features(
    *,
    domestic_open_at: float,
    hourly: list[DexCandle],
    minute: list[DexCandle],
) -> dict[str, Any]:
    open_at = float(domestic_open_at or 0.0)
    if open_at <= 0:
        return {"status": "domestic_open_missing", "reference": None, "pre": {}, "post": {}}

    reference = _closest(minute, open_at, mode="after", tolerance=120)
    if reference is None:
        reference = _closest(hourly, open_at, mode="before", tolerance=3600)
    if reference is None:
        return {"status": "reference_missing", "reference": None, "pre": {}, "post": {}}

    reference_price = float(reference.open)
    pre: dict[str, Any] = {}
    for name, offset in PRE_WINDOWS.items():
        target = open_at - offset
        row = _closest(hourly, target, mode="before", tolerance=3600)
        pre[name] = {
            **(_point(row, target) or {}),
            "return_to_domestic_open_pct": _pct(reference_price, float(row.open)) if row else None,
        } if row else None

    post: dict[str, Any] = {}
    for name, offset in POST_WINDOWS.items():
        target = open_at + offset
        source = minute if name == "p5m" else hourly
        tolerance = 120 if name == "p5m" else 3600
        row = _closest(source, target, mode="after", tolerance=tolerance)
        post[name] = {
            **(_point(row, target) or {}),
            "return_from_domestic_open_pct": _pct(float(row.open), reference_price) if row else None,
        } if row else None

    p5m = post.get("p5m") if isinstance(post.get("p5m"), dict) else None
    return {
        "status": "collected",
        "reference": {
            "candle_ts": float(reference.ts),
            "price": reference_price,
            "interval_seconds": int(reference.interval_seconds),
        },
        "pre": pre,
        "post": post,
        "p5m_exact_minute": _exact_minute_point(p5m),
    }


def launch_window_features(
    *,
    pool_created_at: float,
    hourly: list[DexCandle],
    minute: list[DexCandle],
    domestic_open_at: float,
) -> dict[str, Any]:
    created = float(pool_created_at or 0.0)
    if created <= 0:
        return {"status": "pool_created_at_missing"}
    reference = _closest(minute, created, mode="after", tolerance=15 * 60)
    if reference is None:
        reference = _closest(hourly, created, mode="after", tolerance=3600)
    if reference is None:
        return {
            "status": "launch_ohlcv_unavailable",
            "pool_created_at": created,
            "pool_age_days_at_domestic_listing": (
                round((float(domestic_open_at) - created) / 86400.0, 4)
                if domestic_open_at and float(domestic_open_at) >= created
                else None
            ),
        }
    first = float(reference.open)
    windows: dict[str, Any] = {}
    for name, offset in {"p5m": 300, "p1h": 3600, "p6h": 21600, "p24h": 86400}.items():
        target = created + offset
        source = minute if name == "p5m" else hourly
        tolerance = 120 if name == "p5m" else 3600
        row = _closest(source, target, mode="after", tolerance=tolerance)
        windows[name] = {
            **(_point(row, target) or {}),
            "return_from_launch_pct": _pct(float(row.open), first) if row else None,
        } if row else None
    return {
        "status": "collected",
        "pool_created_at": created,
        "reference": {
            "candle_ts": float(reference.ts),
            "price": first,
            "interval_seconds": int(reference.interval_seconds),
        },
        "pool_age_days_at_domestic_listing": (
            round((float(domestic_open_at) - created) / 86400.0, 4)
            if domestic_open_at and float(domestic_open_at) >= created
            else None
        ),
        "windows": windows,
        "p5m_exact_minute": _exact_minute_point(
            windows.get("p5m") if isinstance(windows.get("p5m"), dict) else None
        ),
    }


def build_dex_features(
    *,
    domestic_open_at: float,
    pool_created_at: float,
    domestic_hourly: list[DexCandle],
    domestic_minute: list[DexCandle],
    launch_hourly: list[DexCandle],
    launch_minute: list[DexCandle],
    reserve_usd: float,
    volume_h24_usd: float,
    min_liquidity_usd: float,
    min_volume_h24_usd: float,
) -> dict[str, Any]:
    return {
        "version": FEATURE_VERSION,
        "paper_only": True,
        "shadow_only": True,
        "pool_quality": {
            "reserve_usd": float(reserve_usd or 0.0),
            "volume_h24_usd": float(volume_h24_usd or 0.0),
            "min_liquidity_usd": float(min_liquidity_usd),
            "min_volume_h24_usd": float(min_volume_h24_usd),
            "passed": bool(
                float(reserve_usd or 0.0) >= float(min_liquidity_usd)
                and float(volume_h24_usd or 0.0) >= float(min_volume_h24_usd)
            ),
        },
        "domestic_listing_window": domestic_window_features(
            domestic_open_at=domestic_open_at,
            hourly=domestic_hourly,
            minute=domestic_minute,
        ),
        "pool_launch_window": launch_window_features(
            pool_created_at=pool_created_at,
            hourly=launch_hourly,
            minute=launch_minute,
            domestic_open_at=domestic_open_at,
        ),
    }
