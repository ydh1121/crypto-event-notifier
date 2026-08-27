from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


PRE_LISTING_WINDOWS: tuple[tuple[str, int], ...] = (
    ("t7d", 7 * 24 * 3600),
    ("t5d", 5 * 24 * 3600),
    ("t3d", 3 * 24 * 3600),
    ("t1d", 24 * 3600),
    ("t6h", 6 * 3600),
    ("t1h", 3600),
)
POST_LISTING_WINDOWS: tuple[tuple[str, int], ...] = (
    ("p5m", 5 * 60),
    ("p1h", 3600),
    ("p6h", 6 * 3600),
    ("p24h", 24 * 3600),
    ("p3d", 3 * 24 * 3600),
    ("p7d", 7 * 24 * 3600),
)


@dataclass(frozen=True)
class ListingCandle:
    ts: float
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    quote_volume: float = 0.0
    interval_seconds: int = 3600
    confirmed: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ListingCandle":
        def num(key: str, default: float = 0.0) -> float:
            try:
                return float(payload.get(key) or default)
            except (TypeError, ValueError):
                return default

        return cls(
            ts=num("ts"),
            open=num("open"),
            high=num("high"),
            low=num("low"),
            close=num("close"),
            volume=num("volume"),
            quote_volume=num("quote_volume"),
            interval_seconds=max(60, int(num("interval_seconds", 3600))),
            confirmed=bool(payload.get("confirmed", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "quote_volume": self.quote_volume,
            "interval_seconds": self.interval_seconds,
            "confirmed": self.confirmed,
        }


def _pct(current: float, base: float) -> float | None:
    if base <= 0 or current <= 0:
        return None
    return (current / base - 1.0) * 100.0


def _valid_candles(candles: Iterable[ListingCandle]) -> list[ListingCandle]:
    return sorted(
        (
            row
            for row in candles
            if row.confirmed
            and row.ts > 0
            and row.open > 0
            and row.high > 0
            and row.low > 0
            and row.close > 0
        ),
        key=lambda row: row.ts,
    )


def price_at_or_before(
    candles: Iterable[ListingCandle],
    target_ts: float,
    *,
    max_lag_seconds: int = 3 * 3600,
) -> dict[str, Any] | None:
    rows = _valid_candles(candles)
    candidate: ListingCandle | None = None
    for row in rows:
        if row.ts > target_ts:
            break
        candidate = row
    if candidate is None:
        return None
    lag = max(0.0, target_ts - candidate.ts)
    if lag > max(60, int(max_lag_seconds)):
        return None
    return {
        "target_ts": float(target_ts),
        "candle_ts": candidate.ts,
        "price": candidate.close,
        "lag_seconds": lag,
        "interval_seconds": candidate.interval_seconds,
    }


def price_at_or_after(
    candles: Iterable[ListingCandle],
    target_ts: float,
    *,
    max_lead_seconds: int = 3 * 3600,
) -> dict[str, Any] | None:
    rows = _valid_candles(candles)
    for row in rows:
        if row.ts < target_ts:
            continue
        lead = max(0.0, row.ts - target_ts)
        if lead > max(60, int(max_lead_seconds)):
            return None
        return {
            "target_ts": float(target_ts),
            "candle_ts": row.ts,
            "price": row.open,
            "lead_seconds": lead,
            "interval_seconds": row.interval_seconds,
        }
    return None


def prelisting_features(
    candles: Iterable[ListingCandle],
    *,
    domestic_open_at: float,
    domestic_open_price: float,
    foreign_listing_at: float = 0.0,
    foreign_first_price: float = 0.0,
) -> dict[str, Any]:
    """Build pre-KRW price windows from normalized confirmed candles.

    The feature domain never fetches an exchange and never guesses identity or
    launch provenance. Missing windows and unknown historical launch data remain
    null instead of becoming zero-return observations or T-8d pseudo-launches.
    """

    rows = _valid_candles(candles)
    before_open = [row for row in rows if row.ts < domestic_open_at]
    windows: dict[str, Any] = {}
    for key, seconds in PRE_LISTING_WINDOWS:
        point = price_at_or_before(rows, domestic_open_at - seconds)
        windows[key] = point
        windows[f"{key}_price"] = point["price"] if point else None
        windows[f"{key}_to_domestic_pct"] = (
            _pct(domestic_open_price, float(point["price"])) if point else None
        )

    pre_high = max((row.high for row in before_open), default=0.0)
    pre_low = min((row.low for row in before_open), default=0.0)
    first = float(foreign_first_price or 0.0)
    first_ts = float(foreign_listing_at or 0.0)

    return {
        "domestic_open_at": float(domestic_open_at),
        "domestic_open_price": float(domestic_open_price),
        "foreign_listing_at": first_ts if first_ts > 0 else None,
        "foreign_first_price": first if first > 0 else None,
        "foreign_first_to_domestic_pct": _pct(domestic_open_price, first),
        "pre_domestic_ath": pre_high or None,
        "pre_domestic_atl": pre_low or None,
        "domestic_vs_pre_ath_pct": _pct(domestic_open_price, pre_high),
        "domestic_vs_pre_atl_pct": _pct(domestic_open_price, pre_low),
        "windows": windows,
        "candle_count": len(rows),
        "pre_domestic_candle_count": len(before_open),
    }


def postlisting_features(
    candles: Iterable[ListingCandle],
    *,
    domestic_open_at: float,
    domestic_open_price: float,
) -> dict[str, Any]:
    rows = _valid_candles(candles)
    windows: dict[str, Any] = {}
    for key, seconds in POST_LISTING_WINDOWS:
        point = price_at_or_after(rows, domestic_open_at + seconds)
        windows[key] = point
        windows[f"{key}_price"] = point["price"] if point else None
        windows[f"{key}_return_pct"] = (
            _pct(float(point["price"]), domestic_open_price) if point else None
        )
    return {
        "domestic_open_at": float(domestic_open_at),
        "domestic_open_price": float(domestic_open_price),
        "windows": windows,
        "candle_count": len(rows),
    }
