from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from typing import Iterable, Mapping, Any

DAY_SECONDS = 86400.0
DEFAULT_MAX_SAMPLE_GAP_SECONDS = 6 * 3600.0
PRIOR_DAY_COUNT = 5
CUMULATIVE_RETURN_DAYS = (1, 3, 5, 7, 30)


@dataclass(frozen=True)
class PricePoint:
    ts: float
    price: float


def _points(rows: Iterable[Mapping[str, Any] | PricePoint]) -> list[PricePoint]:
    result: list[PricePoint] = []
    for row in rows:
        if isinstance(row, PricePoint):
            ts, price = row.ts, row.price
        else:
            try:
                ts = float(row.get("ts") or row.get("signal_ts") or 0.0)
                price = float(row.get("price") or 0.0)
            except (TypeError, ValueError):
                continue
        if ts > 0 and price > 0:
            result.append(PricePoint(ts=ts, price=price))
    result.sort(key=lambda item: item.ts)
    return result


def _nearest(points: list[PricePoint], target: float, max_gap: float) -> PricePoint | None:
    if not points:
        return None
    timestamps = [item.ts for item in points]
    index = bisect_left(timestamps, target)
    candidates: list[PricePoint] = []
    if index < len(points):
        candidates.append(points[index])
    if index > 0:
        candidates.append(points[index - 1])
    if not candidates:
        return None
    best = min(candidates, key=lambda item: abs(item.ts - target))
    return best if abs(best.ts - target) <= max_gap else None


def prior_daily_returns(
    rows: Iterable[Mapping[str, Any] | PricePoint],
    *,
    as_of_ts: float | None = None,
    max_sample_gap_seconds: float = DEFAULT_MAX_SAMPLE_GAP_SECONDS,
) -> dict[str, Any]:
    """Return completed prior 24h windows D-1..D-5.

    D-1 is the interval from T-2d to T-1d. The current T-1d→T interval is
    already represented by the exchange's live 24H change and is intentionally
    not duplicated here.
    """
    points = _points(rows)
    if not points:
        return {"as_of_ts": 0.0, "coverage": 0, **{f"d{day}_pct": None for day in range(1, PRIOR_DAY_COUNT + 1)}}
    anchor = float(as_of_ts or points[-1].ts)
    samples: dict[int, PricePoint | None] = {
        day: _nearest(points, anchor - day * DAY_SECONDS, max_sample_gap_seconds)
        for day in range(1, PRIOR_DAY_COUNT + 2)
    }
    result: dict[str, Any] = {"as_of_ts": anchor}
    coverage = 0
    for day in range(1, PRIOR_DAY_COUNT + 1):
        newer = samples.get(day)
        older = samples.get(day + 1)
        value = None
        if newer is not None and older is not None and older.price > 0:
            value = round((newer.price / older.price - 1.0) * 100.0, 6)
            coverage += 1
        result[f"d{day}_pct"] = value
    result["coverage"] = coverage
    return result


def cumulative_returns(
    rows: Iterable[Mapping[str, Any] | PricePoint],
    *,
    as_of_ts: float | None = None,
    max_sample_gap_seconds: float = DEFAULT_MAX_SAMPLE_GAP_SECONDS,
) -> dict[str, Any]:
    """Return T-Nd → T cumulative returns for 1/3/5/7/30 day horizons.

    These values are intentionally separate from D-1..D-5, which represent
    completed historical 24h buckets. Missing or stale anchor/history samples
    remain null instead of being approximated from another horizon.
    """
    points = _points(rows)
    empty = {
        "cumulative_coverage": 0,
        **{f"cum_{day}d_pct": None for day in CUMULATIVE_RETURN_DAYS},
    }
    if not points:
        return {"as_of_ts": 0.0, **empty}

    anchor = float(as_of_ts or points[-1].ts)
    current = _nearest(points, anchor, max_sample_gap_seconds)
    result: dict[str, Any] = {"as_of_ts": anchor}
    coverage = 0
    for day in CUMULATIVE_RETURN_DAYS:
        older = _nearest(points, anchor - day * DAY_SECONDS, max_sample_gap_seconds)
        value = None
        if current is not None and older is not None and older.price > 0:
            value = round((current.price / older.price - 1.0) * 100.0, 6)
            coverage += 1
        result[f"cum_{day}d_pct"] = value
    result["cumulative_coverage"] = coverage
    return result


def market_return_windows(
    rows: Iterable[Mapping[str, Any] | PricePoint],
    *,
    as_of_ts: float | None = None,
    max_sample_gap_seconds: float = DEFAULT_MAX_SAMPLE_GAP_SECONDS,
) -> dict[str, Any]:
    """Build the combined completed-daily and cumulative return projection."""
    points = _points(rows)
    result = prior_daily_returns(
        points,
        as_of_ts=as_of_ts,
        max_sample_gap_seconds=max_sample_gap_seconds,
    )
    result.update(
        cumulative_returns(
            points,
            as_of_ts=as_of_ts,
            max_sample_gap_seconds=max_sample_gap_seconds,
        )
    )
    return result
