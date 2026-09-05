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


def _candle_price_without_lookahead(row: ListingCandle, target_ts: float) -> tuple[float, float]:
    """Return a price known by target_ts and the timestamp that price represents.

    CEX kline timestamps are normally candle-open timestamps. A candle close is
    only safe once the whole interval has completed. While target_ts is inside
    a candle, use that candle's opening price instead of its future close/high.
    """

    candle_end = row.ts + max(60, int(row.interval_seconds))
    if candle_end <= target_ts:
        return float(row.close), float(candle_end)
    return float(row.open), float(row.ts)


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
    price, observed_at = _candle_price_without_lookahead(candidate, target_ts)
    lag = max(0.0, target_ts - observed_at)
    if lag > max(60, int(max_lag_seconds)):
        return None
    return {
        "target_ts": float(target_ts),
        "candle_ts": candidate.ts,
        "observed_at": observed_at,
        "price": price,
        "lag_seconds": lag,
        "interval_seconds": candidate.interval_seconds,
        "price_basis": "close" if observed_at > candidate.ts else "open",
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
            "price_basis": "open",
        }
    return None


def prelisting_features(
    candles: Iterable[ListingCandle],
    *,
    domestic_open_at: float,
    domestic_open_price: float,
    quote_asset: str = "",
    quote_to_krw_at_open: float = 0.0,
    foreign_listing_at: float = 0.0,
    foreign_first_price: float = 0.0,
) -> dict[str, Any]:
    """Build pre-KRW windows without comparing unlike currencies.

    T-window momentum is measured entirely inside the foreign quote currency.
    A domestic KRW premium is produced only when the foreign quote has a
    verified quote→KRW conversion at the domestic listing timestamp.
    Unknown historical launch provenance remains null; T-8d is never a proxy.
    """

    rows = _valid_candles(candles)
    completed_before_open = [
        row for row in rows
        if row.ts + max(60, int(row.interval_seconds)) <= domestic_open_at
    ]
    foreign_open = price_at_or_before(rows, domestic_open_at)
    foreign_open_price = float(foreign_open["price"]) if foreign_open else 0.0

    windows: dict[str, Any] = {}
    for key, seconds in PRE_LISTING_WINDOWS:
        point = price_at_or_before(rows, domestic_open_at - seconds)
        windows[key] = point
        windows[f"{key}_price"] = point["price"] if point else None
        windows[f"{key}_to_foreign_open_pct"] = (
            _pct(foreign_open_price, float(point["price"]))
            if point and foreign_open_price > 0
            else None
        )

    pre_high = max((row.high for row in completed_before_open), default=0.0)
    pre_low = min((row.low for row in completed_before_open), default=0.0)
    first = float(foreign_first_price or 0.0)
    first_ts = float(foreign_listing_at or 0.0)
    quote_rate = float(quote_to_krw_at_open or 0.0)
    foreign_open_krw = foreign_open_price * quote_rate if foreign_open_price > 0 and quote_rate > 0 else 0.0

    return {
        "domestic_open_at": float(domestic_open_at),
        "domestic_open_price_krw": float(domestic_open_price) if domestic_open_price > 0 else None,
        "quote_asset": str(quote_asset or "").upper(),
        "quote_to_krw_at_open": quote_rate if quote_rate > 0 else None,
        "foreign_price_at_domestic_open": foreign_open,
        "foreign_open_price": foreign_open_price if foreign_open_price > 0 else None,
        "foreign_open_price_krw": foreign_open_krw if foreign_open_krw > 0 else None,
        "domestic_listing_premium_pct": _pct(domestic_open_price, foreign_open_krw),
        "foreign_listing_at": first_ts if first_ts > 0 else None,
        "foreign_first_price": first if first > 0 else None,
        "foreign_first_to_foreign_open_pct": _pct(foreign_open_price, first),
        "pre_domestic_ath_foreign_quote": pre_high or None,
        "pre_domestic_atl_foreign_quote": pre_low or None,
        "foreign_open_vs_pre_ath_pct": _pct(foreign_open_price, pre_high),
        "foreign_open_vs_pre_atl_pct": _pct(foreign_open_price, pre_low),
        "windows": windows,
        "candle_count": len(rows),
        "completed_pre_domestic_candle_count": len(completed_before_open),
        "currency_safe": True,
    }


def reaction_features(
    candles: Iterable[ListingCandle],
    *,
    anchor_at: float,
    anchor_price: float,
    fine_candles: Iterable[ListingCandle] | None = None,
) -> dict[str, Any]:
    """Return same-currency forward reaction windows from an explicit anchor.

    The +5 minute window must use minute-resolution evidence when supplied. It
    must never be silently approximated with an hourly candle by the collector.
    Longer windows continue to use the bounded hourly history.
    """

    rows = _valid_candles(candles)
    fine_rows = _valid_candles(fine_candles) if fine_candles is not None else None
    windows: dict[str, Any] = {}
    for key, seconds in POST_LISTING_WINDOWS:
        if key == "p5m" and fine_rows is not None:
            point = price_at_or_after(fine_rows, anchor_at + seconds, max_lead_seconds=120)
        else:
            point = price_at_or_after(rows, anchor_at + seconds)
        windows[key] = point
        windows[f"{key}_price"] = point["price"] if point else None
        windows[f"{key}_return_pct"] = (
            _pct(float(point["price"]), anchor_price) if point else None
        )
    return {
        "anchor_at": float(anchor_at),
        "anchor_price": float(anchor_price) if anchor_price > 0 else None,
        "windows": windows,
        "candle_count": len(rows),
        "p5m_source_interval_seconds": (
            min((row.interval_seconds for row in fine_rows), default=0) if fine_rows is not None else None
        ),
        "p5m_exact_minute_required": fine_rows is not None,
    }


def postlisting_features(
    candles: Iterable[ListingCandle],
    *,
    domestic_open_at: float,
    domestic_open_price: float,
) -> dict[str, Any]:
    """Domestic same-KRW forward reaction wrapper kept for call-site clarity."""

    return reaction_features(
        candles,
        anchor_at=domestic_open_at,
        anchor_price=domestic_open_price,
    )
