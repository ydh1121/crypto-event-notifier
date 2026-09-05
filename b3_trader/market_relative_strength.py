from __future__ import annotations

import math
import sqlite3
import statistics
import time
from typing import Any

DAY_SECONDS = 86400.0
HORIZON_DAYS = (1, 3, 7, 30)
BENCHMARK_MARKETS = ("KRW-BTC", "KRW-ETH")
FEATURE_VERSION = 1
MIN_BREADTH_SAMPLE = 30
MIN_BREADTH_COVERAGE_RATIO = 0.60
MAX_DAILY_ANCHOR_LAG_SECONDS = 36.0 * 3600.0


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _return_pct(
    rows: list[tuple[float, float]],
    *,
    as_of_ts: float,
    horizon_days: int,
) -> float | None:
    if not rows or as_of_ts <= 0 or horizon_days <= 0:
        return None
    anchor: tuple[float, float] | None = None
    baseline: tuple[float, float] | None = None
    target = float(as_of_ts) - float(horizon_days) * DAY_SECONDS
    for ts, close in rows:
        if ts <= as_of_ts:
            anchor = (ts, close)
        if ts <= target:
            baseline = (ts, close)
        if ts > as_of_ts:
            break
    if anchor is None or baseline is None:
        return None
    if as_of_ts - anchor[0] > MAX_DAILY_ANCHOR_LAG_SECONDS:
        return None
    if target - baseline[0] > MAX_DAILY_ANCHOR_LAG_SECONDS:
        return None
    if baseline[1] <= 0 or anchor[1] <= 0:
        return None
    return (anchor[1] / baseline[1] - 1.0) * 100.0


class MarketRelativeStrengthEngine:
    """Derive bounded relative-strength features from local 1d OHLCV.

    The engine writes latest-only research features. It does not mutate PAPER
    state or scores. Breadth remains unavailable until enough of the live KRW
    universe has valid daily history, preventing a tiny bootstrap sample from
    being presented as the whole market.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_market_relative_strength_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                horizon_days INTEGER NOT NULL,
                as_of_ts REAL NOT NULL,
                asset_return_pct REAL,
                btc_return_pct REAL,
                eth_return_pct REAL,
                vs_btc_pp REAL,
                vs_eth_pp REAL,
                breadth_positive_pct REAL,
                breadth_median_return_pct REAL,
                vs_breadth_median_pp REAL,
                breadth_sample_count INTEGER NOT NULL DEFAULT 0,
                breadth_universe_count INTEGER NOT NULL DEFAULT 0,
                breadth_coverage_pct REAL NOT NULL DEFAULT 0,
                breadth_ready INTEGER NOT NULL DEFAULT 0,
                source_timeframe TEXT NOT NULL DEFAULT '1d',
                source_table TEXT NOT NULL DEFAULT 'research_market_ohlcv_mx',
                source_ts REAL NOT NULL,
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,horizon_days)
            );
            CREATE INDEX IF NOT EXISTS idx_research_market_relative_strength_mx_lookup
            ON research_market_relative_strength_mx(exchange,market,horizon_days);
            CREATE INDEX IF NOT EXISTS idx_research_market_relative_strength_mx_received
            ON research_market_relative_strength_mx(received_at DESC);
            """
        )
        self.conn.commit()

    def _benchmark_as_of(self, exchange: str) -> tuple[float, dict[str, float]]:
        rows = self.conn.execute(
            """SELECT market,MAX(candle_ts) AS latest_ts
               FROM research_market_ohlcv_mx
               WHERE exchange=? AND timeframe='1d' AND market IN (?,?)
               GROUP BY market""",
            (str(exchange), BENCHMARK_MARKETS[0], BENCHMARK_MARKETS[1]),
        ).fetchall()
        latest = {str(row["market"]): float(row["latest_ts"] or 0.0) for row in rows}
        if any(latest.get(market, 0.0) <= 0 for market in BENCHMARK_MARKETS):
            return 0.0, latest
        return min(latest[market] for market in BENCHMARK_MARKETS), latest

    def _series(self, exchange: str, *, as_of_ts: float) -> dict[str, list[tuple[float, float]]]:
        start_ts = float(as_of_ts) - (max(HORIZON_DAYS) + 2.0) * DAY_SECONDS
        rows = self.conn.execute(
            """SELECT market,candle_ts,close
               FROM research_market_ohlcv_mx
               WHERE exchange=? AND timeframe='1d' AND candle_ts>=? AND candle_ts<=?
               ORDER BY market ASC,candle_ts ASC""",
            (str(exchange), start_ts, float(as_of_ts)),
        ).fetchall()
        result: dict[str, list[tuple[float, float]]] = {}
        for row in rows:
            close = _finite(row["close"])
            ts = _finite(row["candle_ts"])
            if close is None or ts is None or close <= 0 or ts <= 0:
                continue
            result.setdefault(str(row["market"]), []).append((ts, close))
        return result

    def compute_exchange(self, exchange: str, *, universe_count: int) -> dict[str, Any]:
        started = time.time()
        as_of_ts, benchmark_latest = self._benchmark_as_of(exchange)
        if as_of_ts <= 0:
            return {
                "ok": True,
                "status": "waiting_for_benchmarks",
                "exchange": str(exchange),
                "benchmarks": benchmark_latest,
                "horizons": list(HORIZON_DAYS),
                "features_written": 0,
                "breadth_ready_horizons": 0,
                "paper_only": True,
                "can_place_orders": False,
                "elapsed_seconds": round(time.time() - started, 4),
            }

        series = self._series(exchange, as_of_ts=as_of_ts)
        returns_by_horizon: dict[int, dict[str, float]] = {}
        breadth_by_horizon: dict[int, dict[str, Any]] = {}
        universe = max(0, int(universe_count))

        for horizon in HORIZON_DAYS:
            values: dict[str, float] = {}
            for market, rows in series.items():
                value = _return_pct(rows, as_of_ts=as_of_ts, horizon_days=horizon)
                if value is not None:
                    values[market] = value
            returns_by_horizon[horizon] = values
            sample_count = len(values)
            coverage = (sample_count / universe) if universe > 0 else 0.0
            ready = bool(
                sample_count >= MIN_BREADTH_SAMPLE
                and universe > 0
                and coverage >= MIN_BREADTH_COVERAGE_RATIO
            )
            sample_values = list(values.values())
            breadth_by_horizon[horizon] = {
                "sample_count": sample_count,
                "universe_count": universe,
                "coverage_pct": coverage * 100.0,
                "ready": ready,
                "positive_pct": (
                    100.0 * sum(1 for value in sample_values if value > 0) / sample_count
                    if ready and sample_count
                    else None
                ),
                "median_return_pct": statistics.median(sample_values) if ready and sample_values else None,
            }

        received_at = time.time()
        prepared: list[tuple[Any, ...]] = []
        all_markets = sorted(series.keys())
        for market in all_markets:
            for horizon in HORIZON_DAYS:
                values = returns_by_horizon[horizon]
                breadth = breadth_by_horizon[horizon]
                asset_return = values.get(market)
                btc_return = values.get(BENCHMARK_MARKETS[0])
                eth_return = values.get(BENCHMARK_MARKETS[1])
                median_return = _finite(breadth.get("median_return_pct"))
                prepared.append(
                    (
                        str(exchange),
                        market,
                        int(horizon),
                        float(as_of_ts),
                        asset_return,
                        btc_return,
                        eth_return,
                        (asset_return - btc_return) if asset_return is not None and btc_return is not None else None,
                        (asset_return - eth_return) if asset_return is not None and eth_return is not None else None,
                        breadth.get("positive_pct"),
                        median_return,
                        (asset_return - median_return) if asset_return is not None and median_return is not None else None,
                        int(breadth["sample_count"]),
                        int(breadth["universe_count"]),
                        float(breadth["coverage_pct"]),
                        1 if breadth["ready"] else 0,
                        "1d",
                        "research_market_ohlcv_mx",
                        float(as_of_ts),
                        received_at,
                        FEATURE_VERSION,
                    )
                )

        if prepared:
            self.conn.executemany(
                """INSERT INTO research_market_relative_strength_mx(
                       exchange,market,horizon_days,as_of_ts,asset_return_pct,
                       btc_return_pct,eth_return_pct,vs_btc_pp,vs_eth_pp,
                       breadth_positive_pct,breadth_median_return_pct,vs_breadth_median_pp,
                       breadth_sample_count,breadth_universe_count,breadth_coverage_pct,
                       breadth_ready,source_timeframe,source_table,source_ts,received_at,feature_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(exchange,market,horizon_days) DO UPDATE SET
                       as_of_ts=excluded.as_of_ts,
                       asset_return_pct=excluded.asset_return_pct,
                       btc_return_pct=excluded.btc_return_pct,
                       eth_return_pct=excluded.eth_return_pct,
                       vs_btc_pp=excluded.vs_btc_pp,
                       vs_eth_pp=excluded.vs_eth_pp,
                       breadth_positive_pct=excluded.breadth_positive_pct,
                       breadth_median_return_pct=excluded.breadth_median_return_pct,
                       vs_breadth_median_pp=excluded.vs_breadth_median_pp,
                       breadth_sample_count=excluded.breadth_sample_count,
                       breadth_universe_count=excluded.breadth_universe_count,
                       breadth_coverage_pct=excluded.breadth_coverage_pct,
                       breadth_ready=excluded.breadth_ready,
                       source_timeframe=excluded.source_timeframe,
                       source_table=excluded.source_table,
                       source_ts=excluded.source_ts,
                       received_at=excluded.received_at,
                       feature_version=excluded.feature_version""",
                prepared,
            )
            self.conn.commit()

        return {
            "ok": True,
            "status": "computed",
            "exchange": str(exchange),
            "as_of_ts": as_of_ts,
            "benchmarks": benchmark_latest,
            "horizons": list(HORIZON_DAYS),
            "features_written": len(prepared),
            "markets_with_daily_history": len(series),
            "breadth_ready_horizons": sum(1 for value in breadth_by_horizon.values() if value["ready"]),
            "breadth": {str(key): value for key, value in breadth_by_horizon.items()},
            "feature_version": FEATURE_VERSION,
            "paper_only": True,
            "can_place_orders": False,
            "elapsed_seconds": round(time.time() - started, 4),
        }

    def read_market(self, exchange: str, market: str) -> dict[str, Any]:
        rows = self.conn.execute(
            """SELECT * FROM research_market_relative_strength_mx
               WHERE exchange=? AND market=? ORDER BY horizon_days ASC""",
            (str(exchange), str(market)),
        ).fetchall()
        return {
            "feature_version": FEATURE_VERSION,
            "exchange": str(exchange),
            "market": str(market),
            "horizons": {str(int(row["horizon_days"])): dict(row) for row in rows},
        }

    def audit(self) -> dict[str, Any]:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_relative_strength_mx'"
        ).fetchone()
        if not exists:
            return {"table_exists": False, "row_count": 0, "exchanges": {}}
        rows = self.conn.execute(
            """SELECT exchange,COUNT(*) AS rows,COUNT(DISTINCT market) AS markets,
                      SUM(CASE WHEN breadth_ready=1 THEN 1 ELSE 0 END) AS breadth_ready_rows,
                      MAX(received_at) AS received_at,MAX(as_of_ts) AS as_of_ts
               FROM research_market_relative_strength_mx GROUP BY exchange ORDER BY exchange"""
        ).fetchall()
        return {
            "table_exists": True,
            "row_count": sum(int(row["rows"] or 0) for row in rows),
            "exchanges": {
                str(row["exchange"]): {
                    "rows": int(row["rows"] or 0),
                    "markets": int(row["markets"] or 0),
                    "breadth_ready_rows": int(row["breadth_ready_rows"] or 0),
                    "received_at": float(row["received_at"] or 0.0),
                    "as_of_ts": float(row["as_of_ts"] or 0.0),
                }
                for row in rows
            },
            "feature_version": FEATURE_VERSION,
            "paper_only": True,
            "can_place_orders": False,
        }
