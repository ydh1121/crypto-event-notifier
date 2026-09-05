from __future__ import annotations

import json
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

    def relative_strength(self, *, exchange: str, market: str) -> dict[str, Any]:
        try:
            exists = self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_relative_strength_mx'"
            ).fetchone()
        except sqlite3.Error:
            exists = None
        if not exists:
            return {"feature_version": 0, "exchange": exchange, "market": market, "horizons": {}}
        try:
            rows = self.conn.execute(
                """SELECT horizon_days,as_of_ts,asset_return_pct,btc_return_pct,eth_return_pct,
                          vs_btc_pp,vs_eth_pp,breadth_positive_pct,breadth_median_return_pct,
                          vs_breadth_median_pp,breadth_sample_count,breadth_universe_count,
                          breadth_coverage_pct,breadth_ready,source_timeframe,source_table,
                          source_ts,received_at,feature_version
                   FROM research_market_relative_strength_mx
                   WHERE exchange=? AND market=? ORDER BY horizon_days ASC""",
                (str(exchange), str(market)),
            ).fetchall()
        except sqlite3.Error:
            rows = []
        horizons: dict[str, Any] = {}
        version = 0
        for row in rows:
            item = dict(row)
            version = max(version, int(item.get("feature_version") or 0))
            item["breadth_ready"] = bool(item.get("breadth_ready"))
            horizons[str(int(item.get("horizon_days") or 0))] = item
        return {
            "feature_version": version,
            "exchange": str(exchange),
            "market": str(market),
            "horizons": horizons,
        }

    def cross_exchange_gap(self, *, market: str) -> dict[str, Any]:
        try:
            exists = self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_cross_exchange_gap_mx'"
            ).fetchone()
        except sqlite3.Error:
            exists = None
        if not exists:
            return {"feature_version": 0, "market": str(market), "gap_ready": False}
        try:
            row = self.conn.execute(
                """SELECT market,symbol,bithumb_market,upbit_market,bithumb_name,upbit_name,
                          identity_verified,identity_basis,bithumb_price,upbit_price,
                          bithumb_source_ts,upbit_source_ts,source_skew_seconds,
                          upbit_vs_bithumb_pct,absolute_gap_pct,gap_ready,source_timeframe,
                          source_table,received_at,feature_version
                   FROM research_market_cross_exchange_gap_mx WHERE market=?""",
                (str(market),),
            ).fetchone()
        except sqlite3.Error:
            row = None
        if not row:
            return {"feature_version": 0, "market": str(market), "gap_ready": False}
        result = dict(row)
        result["identity_verified"] = bool(result.get("identity_verified"))
        result["gap_ready"] = bool(result.get("gap_ready"))
        result["paper_only"] = True
        result["score_wired"] = False
        return result

    def domestic_premium(self, *, market: str) -> dict[str, Any]:
        try:
            exists = self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_domestic_premium_mx'"
            ).fetchone()
        except sqlite3.Error:
            exists = None
        if not exists:
            return {"feature_version": 0, "market": str(market), "status": "not_available"}
        try:
            row = self.conn.execute(
                """SELECT market,symbol,provider,provider_id,identity_verified,status,
                          bithumb_price_krw,upbit_price_krw,reference_exchange,reference_market,
                          reference_quote_asset,reference_price_quote,quote_to_krw,reference_price_krw,
                          reference_source_ts,bithumb_premium_pct,upbit_premium_pct,
                          foreign_verified_sources,foreign_price_gap_pct,source_evidence_json,
                          received_at,feature_version
                   FROM research_market_domestic_premium_mx WHERE market=?""",
                (str(market),),
            ).fetchone()
        except sqlite3.Error:
            row = None
        if not row:
            return {"feature_version": 0, "market": str(market), "status": "not_available"}
        result = dict(row)
        result["identity_verified"] = bool(result.get("identity_verified"))
        try:
            result["source_evidence"] = json.loads(str(result.pop("source_evidence_json") or "[]"))
        except json.JSONDecodeError:
            result["source_evidence"] = []
        result["paper_only"] = True
        result["score_wired"] = False
        return result

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
        detail["relative_strength"] = self.relative_strength(exchange=exchange, market=market)
        detail["cross_exchange_gap"] = self.cross_exchange_gap(market=market)
        detail["domestic_premium"] = self.domestic_premium(market=market)
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
