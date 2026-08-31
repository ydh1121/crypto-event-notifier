from __future__ import annotations

import sqlite3
from typing import Any

from .market_return_windows import CUMULATIVE_RETURN_DAYS, DAY_SECONDS, market_return_windows, prior_daily_returns


class MarketFeatureStore:
    """Read shared local market history and derive reusable feature projections."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _market_memory_rows(
        self,
        *,
        exchange: str,
        market: str,
        strategy: str,
        as_of_ts: float,
        lookback_days: float,
    ) -> list[dict[str, Any]]:
        start_ts = float(as_of_ts) - max(0.0, float(lookback_days)) * DAY_SECONDS
        rows = self.conn.execute(
            """SELECT signal_ts AS ts,price
               FROM research_market_memory_mx
               WHERE exchange=? AND market=? AND strategy=? AND signal_ts>=? AND signal_ts<=?
               ORDER BY signal_ts ASC""",
            (exchange, market, strategy, start_ts, float(as_of_ts)),
        ).fetchall()
        return [dict(row) for row in rows]

    def prior_day_returns(
        self,
        *,
        exchange: str,
        market: str,
        strategy: str,
        as_of_ts: float,
    ) -> dict[str, Any]:
        rows = self._market_memory_rows(
            exchange=exchange,
            market=market,
            strategy=strategy,
            as_of_ts=as_of_ts,
            lookback_days=6.25,
        )
        return prior_daily_returns(rows, as_of_ts=as_of_ts)

    def return_windows(
        self,
        *,
        exchange: str,
        market: str,
        strategy: str,
        as_of_ts: float,
    ) -> dict[str, Any]:
        rows = self._market_memory_rows(
            exchange=exchange,
            market=market,
            strategy=strategy,
            as_of_ts=as_of_ts,
            lookback_days=max(CUMULATIVE_RETURN_DAYS) + 0.25,
        )
        return market_return_windows(rows, as_of_ts=as_of_ts)

    def enrich_market_detail(
        self,
        detail: dict[str, Any],
        *,
        exchange: str,
        market: str,
        strategy: str,
    ) -> dict[str, Any]:
        if not detail:
            return detail
        signal = detail.get("signal") if isinstance(detail.get("signal"), dict) else {}
        summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else {}
        try:
            as_of_ts = float(signal.get("ts") or summary.get("signal_ts") or 0.0)
        except (TypeError, ValueError):
            as_of_ts = 0.0
        if as_of_ts <= 0:
            detail["return_windows"] = {"as_of_ts": 0.0, "coverage": 0, "cumulative_coverage": 0}
            return detail
        detail["return_windows"] = self.return_windows(
            exchange=exchange,
            market=market,
            strategy=strategy,
            as_of_ts=as_of_ts,
        )
        return detail
