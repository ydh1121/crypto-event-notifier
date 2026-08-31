from __future__ import annotations

import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 1
FEATURE_VERSION = 1
MAX_CANDIDATES_PER_RUN = 240
WINDOW_FEATURE_RETENTION = 2000
STRONG_DELTA_PCT = 20.0
MAX_ADVERSE_RETURN_BPS = 20.0
MIN_REPLENISHMENT_RATIO = 1.0
MIN_REPLENISHMENT_PAIRS = 5
QUOTE_NORMALIZATION_KRW = 100_000_000.0
WINDOW_SECONDS = {
    "1m": 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
    "1d": 24 * 60 * 60,
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class MarketPriceFlowDivergenceStore:
    """Fail-closed research evidence joining price, aggressive flow, and replenishment.

    The join is intentionally strict:
    - WebSocket trade-flow and orderbook windows must share the exact window.
    - Both WebSocket windows must have continuity_complete=1.
    - feature_ts must sit on the requested timeframe boundary.
    - A completed OHLCV candle must start exactly at window_start_ts.

    Candidate labels are preregistered research heuristics only. They are not an
    accumulation/distribution score and are not wired to PAPER or live orders.
    """

    def __init__(self, path: Path | str = DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=10000")
        self._ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_market_price_flow_divergence_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                window_label TEXT NOT NULL,
                window_seconds REAL NOT NULL,
                feature_ts REAL NOT NULL,
                window_start_ts REAL NOT NULL,
                window_end_ts REAL NOT NULL,
                data_ready INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                price_candle_ts REAL,
                price_open REAL,
                price_close REAL,
                price_return_pct REAL,
                price_return_bps REAL,
                trade_count INTEGER NOT NULL DEFAULT 0,
                aggressive_quote_total REAL NOT NULL DEFAULT 0,
                delta_quote REAL NOT NULL DEFAULT 0,
                delta_pct REAL,
                flow_continuity_complete INTEGER NOT NULL DEFAULT 0,
                side_coverage_pct REAL,
                bid_refill_quote REAL NOT NULL DEFAULT 0,
                bid_depletion_quote REAL NOT NULL DEFAULT 0,
                ask_refill_quote REAL NOT NULL DEFAULT 0,
                ask_depletion_quote REAL NOT NULL DEFAULT 0,
                bid_same_best_pairs INTEGER NOT NULL DEFAULT 0,
                ask_same_best_pairs INTEGER NOT NULL DEFAULT 0,
                bid_replenishment_ratio REAL,
                ask_replenishment_ratio REAL,
                orderbook_continuity_complete INTEGER NOT NULL DEFAULT 0,
                price_efficiency_bps_per_100m_quote REAL,
                flow_price_opposition INTEGER NOT NULL DEFAULT 0,
                strong_sell_pressure INTEGER NOT NULL DEFAULT 0,
                strong_buy_pressure INTEGER NOT NULL DEFAULT 0,
                price_resilient_to_sell INTEGER NOT NULL DEFAULT 0,
                price_resilient_to_buy INTEGER NOT NULL DEFAULT 0,
                passive_buy_absorption_candidate INTEGER NOT NULL DEFAULT 0,
                passive_sell_absorption_candidate INTEGER NOT NULL DEFAULT 0,
                evidence_label TEXT NOT NULL DEFAULT 'neutral',
                source TEXT NOT NULL DEFAULT 'ws_trade+ws_orderbook+rest_ohlcv',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,window_label,feature_ts)
            );
            CREATE INDEX IF NOT EXISTS idx_market_price_flow_divergence_time
            ON research_market_price_flow_divergence_mx(exchange,market,window_label,feature_ts DESC);
            CREATE INDEX IF NOT EXISTS idx_market_price_flow_divergence_ready
            ON research_market_price_flow_divergence_mx(data_ready,evidence_label,feature_ts DESC);
            """
        )
        self.conn.commit()

    def _candidate_rows(self, limit: int) -> list[dict[str, Any]]:
        tables = {
            str(row[0])
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        required = {
            "research_market_flow_window_feature_mx",
            "research_market_orderbook_window_feature_mx",
            "research_market_ohlcv_mx",
        }
        if not required.issubset(tables):
            return []
        rows = self.conn.execute(
            """SELECT
                   f.exchange,f.market,f.window_label,f.window_seconds,f.feature_ts,
                   f.window_start_ts,f.window_end_ts,f.trade_count,
                   f.buy_quote_volume,f.sell_quote_volume,f.delta_quote,f.delta_pct,
                   f.continuity_complete AS flow_continuity_complete,f.side_coverage_pct,
                   o.bid_refill_quote,o.bid_depletion_quote,o.ask_refill_quote,o.ask_depletion_quote,
                   o.bid_same_best_pairs,o.ask_same_best_pairs,o.bid_replenishment_ratio,
                   o.ask_replenishment_ratio,o.continuity_complete AS orderbook_continuity_complete
               FROM research_market_flow_window_feature_mx f
               JOIN research_market_orderbook_window_feature_mx o
                 ON o.exchange=f.exchange
                AND o.market=f.market
                AND o.window_label=f.window_label
                AND o.feature_ts=f.feature_ts
                AND o.window_start_ts=f.window_start_ts
                AND o.window_end_ts=f.window_end_ts
               LEFT JOIN research_market_price_flow_divergence_mx d
                 ON d.exchange=f.exchange
                AND d.market=f.market
                AND d.window_label=f.window_label
                AND d.feature_ts=f.feature_ts
               WHERE f.continuity_complete=1
                 AND o.continuity_complete=1
                 AND CAST(f.feature_ts AS INTEGER) % CAST(f.window_seconds AS INTEGER)=0
                 AND (d.feature_ts IS NULL OR d.data_ready=0)
               ORDER BY f.feature_ts DESC
               LIMIT ?""",
            (max(1, min(2000, int(limit))),),
        ).fetchall()
        return [dict(row) for row in rows]

    def _price_candle(self, row: dict[str, Any]) -> dict[str, Any] | None:
        price = self.conn.execute(
            """SELECT candle_ts,open,close,is_closed,received_at
               FROM research_market_ohlcv_mx
               WHERE exchange=? AND market=? AND timeframe=? AND candle_ts=? AND is_closed=1
               ORDER BY received_at DESC LIMIT 1""",
            (
                str(row["exchange"]),
                str(row["market"]),
                str(row["window_label"]),
                float(row["window_start_ts"]),
            ),
        ).fetchone()
        return dict(price) if price else None

    @staticmethod
    def _derive(row: dict[str, Any], price: dict[str, Any] | None, now: float) -> dict[str, Any]:
        buy_quote = max(0.0, float(row.get("buy_quote_volume") or 0.0))
        sell_quote = max(0.0, float(row.get("sell_quote_volume") or 0.0))
        total_quote = buy_quote + sell_quote
        delta_quote = float(row.get("delta_quote") or 0.0)
        delta_pct = _finite(row.get("delta_pct"))
        bid_ratio = _finite(row.get("bid_replenishment_ratio"))
        ask_ratio = _finite(row.get("ask_replenishment_ratio"))
        bid_pairs = int(row.get("bid_same_best_pairs") or 0)
        ask_pairs = int(row.get("ask_same_best_pairs") or 0)

        base = {
            "exchange": str(row["exchange"]),
            "market": str(row["market"]),
            "window_label": str(row["window_label"]),
            "window_seconds": float(row["window_seconds"]),
            "feature_ts": float(row["feature_ts"]),
            "window_start_ts": float(row["window_start_ts"]),
            "window_end_ts": float(row["window_end_ts"]),
            "trade_count": int(row.get("trade_count") or 0),
            "aggressive_quote_total": total_quote,
            "delta_quote": delta_quote,
            "delta_pct": delta_pct,
            "flow_continuity_complete": 1 if bool(row.get("flow_continuity_complete")) else 0,
            "side_coverage_pct": _finite(row.get("side_coverage_pct")),
            "bid_refill_quote": float(row.get("bid_refill_quote") or 0.0),
            "bid_depletion_quote": float(row.get("bid_depletion_quote") or 0.0),
            "ask_refill_quote": float(row.get("ask_refill_quote") or 0.0),
            "ask_depletion_quote": float(row.get("ask_depletion_quote") or 0.0),
            "bid_same_best_pairs": bid_pairs,
            "ask_same_best_pairs": ask_pairs,
            "bid_replenishment_ratio": bid_ratio,
            "ask_replenishment_ratio": ask_ratio,
            "orderbook_continuity_complete": 1 if bool(row.get("orderbook_continuity_complete")) else 0,
            "received_at": now,
        }
        if price is None:
            return {
                **base,
                "data_ready": 0,
                "status": "waiting_exact_closed_price_candle",
                "price_candle_ts": None,
                "price_open": None,
                "price_close": None,
                "price_return_pct": None,
                "price_return_bps": None,
                "price_efficiency_bps_per_100m_quote": None,
                "flow_price_opposition": 0,
                "strong_sell_pressure": 0,
                "strong_buy_pressure": 0,
                "price_resilient_to_sell": 0,
                "price_resilient_to_buy": 0,
                "passive_buy_absorption_candidate": 0,
                "passive_sell_absorption_candidate": 0,
                "evidence_label": "waiting_price",
            }

        open_price = _finite(price.get("open"))
        close_price = _finite(price.get("close"))
        candle_ts = _finite(price.get("candle_ts"))
        exact_price = (
            open_price is not None
            and close_price is not None
            and open_price > 0
            and close_price > 0
            and candle_ts == float(row["window_start_ts"])
            and bool(price.get("is_closed"))
        )
        if not exact_price or total_quote <= 0 or delta_pct is None:
            return {
                **base,
                "data_ready": 0,
                "status": "invalid_or_incomplete_join_evidence",
                "price_candle_ts": candle_ts,
                "price_open": open_price,
                "price_close": close_price,
                "price_return_pct": None,
                "price_return_bps": None,
                "price_efficiency_bps_per_100m_quote": None,
                "flow_price_opposition": 0,
                "strong_sell_pressure": 0,
                "strong_buy_pressure": 0,
                "price_resilient_to_sell": 0,
                "price_resilient_to_buy": 0,
                "passive_buy_absorption_candidate": 0,
                "passive_sell_absorption_candidate": 0,
                "evidence_label": "insufficient",
            }

        return_pct = (close_price / open_price - 1.0) * 100.0
        return_bps = return_pct * 100.0
        strong_sell = delta_pct <= -STRONG_DELTA_PCT
        strong_buy = delta_pct >= STRONG_DELTA_PCT
        resilient_sell = return_bps >= -MAX_ADVERSE_RETURN_BPS
        resilient_buy = return_bps <= MAX_ADVERSE_RETURN_BPS
        buy_candidate = bool(
            strong_sell
            and resilient_sell
            and bid_ratio is not None
            and bid_ratio >= MIN_REPLENISHMENT_RATIO
            and bid_pairs >= MIN_REPLENISHMENT_PAIRS
        )
        sell_candidate = bool(
            strong_buy
            and resilient_buy
            and ask_ratio is not None
            and ask_ratio >= MIN_REPLENISHMENT_RATIO
            and ask_pairs >= MIN_REPLENISHMENT_PAIRS
        )
        opposition = bool((delta_quote < 0 < return_pct) or (delta_quote > 0 > return_pct))
        efficiency = return_bps / (total_quote / QUOTE_NORMALIZATION_KRW) if total_quote > 0 else None
        label = "neutral"
        if buy_candidate:
            label = "passive_buy_absorption_candidate"
        elif sell_candidate:
            label = "passive_sell_absorption_candidate"
        elif opposition:
            label = "price_flow_opposition"
        return {
            **base,
            "data_ready": 1,
            "status": "ready",
            "price_candle_ts": candle_ts,
            "price_open": open_price,
            "price_close": close_price,
            "price_return_pct": return_pct,
            "price_return_bps": return_bps,
            "price_efficiency_bps_per_100m_quote": efficiency,
            "flow_price_opposition": 1 if opposition else 0,
            "strong_sell_pressure": 1 if strong_sell else 0,
            "strong_buy_pressure": 1 if strong_buy else 0,
            "price_resilient_to_sell": 1 if resilient_sell else 0,
            "price_resilient_to_buy": 1 if resilient_buy else 0,
            "passive_buy_absorption_candidate": 1 if buy_candidate else 0,
            "passive_sell_absorption_candidate": 1 if sell_candidate else 0,
            "evidence_label": label,
        }

    def _upsert(self, row: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO research_market_price_flow_divergence_mx(
                   exchange,market,window_label,window_seconds,feature_ts,window_start_ts,window_end_ts,
                   data_ready,status,price_candle_ts,price_open,price_close,price_return_pct,price_return_bps,
                   trade_count,aggressive_quote_total,delta_quote,delta_pct,flow_continuity_complete,
                   side_coverage_pct,bid_refill_quote,bid_depletion_quote,ask_refill_quote,ask_depletion_quote,
                   bid_same_best_pairs,ask_same_best_pairs,bid_replenishment_ratio,ask_replenishment_ratio,
                   orderbook_continuity_complete,price_efficiency_bps_per_100m_quote,flow_price_opposition,
                   strong_sell_pressure,strong_buy_pressure,price_resilient_to_sell,price_resilient_to_buy,
                   passive_buy_absorption_candidate,passive_sell_absorption_candidate,evidence_label,
                   source,received_at,feature_version,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(exchange,market,window_label,feature_ts) DO UPDATE SET
                   data_ready=excluded.data_ready,status=excluded.status,price_candle_ts=excluded.price_candle_ts,
                   price_open=excluded.price_open,price_close=excluded.price_close,
                   price_return_pct=excluded.price_return_pct,price_return_bps=excluded.price_return_bps,
                   trade_count=excluded.trade_count,aggressive_quote_total=excluded.aggressive_quote_total,
                   delta_quote=excluded.delta_quote,delta_pct=excluded.delta_pct,
                   flow_continuity_complete=excluded.flow_continuity_complete,
                   side_coverage_pct=excluded.side_coverage_pct,bid_refill_quote=excluded.bid_refill_quote,
                   bid_depletion_quote=excluded.bid_depletion_quote,ask_refill_quote=excluded.ask_refill_quote,
                   ask_depletion_quote=excluded.ask_depletion_quote,bid_same_best_pairs=excluded.bid_same_best_pairs,
                   ask_same_best_pairs=excluded.ask_same_best_pairs,
                   bid_replenishment_ratio=excluded.bid_replenishment_ratio,
                   ask_replenishment_ratio=excluded.ask_replenishment_ratio,
                   orderbook_continuity_complete=excluded.orderbook_continuity_complete,
                   price_efficiency_bps_per_100m_quote=excluded.price_efficiency_bps_per_100m_quote,
                   flow_price_opposition=excluded.flow_price_opposition,
                   strong_sell_pressure=excluded.strong_sell_pressure,strong_buy_pressure=excluded.strong_buy_pressure,
                   price_resilient_to_sell=excluded.price_resilient_to_sell,
                   price_resilient_to_buy=excluded.price_resilient_to_buy,
                   passive_buy_absorption_candidate=excluded.passive_buy_absorption_candidate,
                   passive_sell_absorption_candidate=excluded.passive_sell_absorption_candidate,
                   evidence_label=excluded.evidence_label,source=excluded.source,received_at=excluded.received_at,
                   feature_version=excluded.feature_version,schema_version=excluded.schema_version""",
            (
                row["exchange"],row["market"],row["window_label"],row["window_seconds"],row["feature_ts"],
                row["window_start_ts"],row["window_end_ts"],row["data_ready"],row["status"],row["price_candle_ts"],
                row["price_open"],row["price_close"],row["price_return_pct"],row["price_return_bps"],row["trade_count"],
                row["aggressive_quote_total"],row["delta_quote"],row["delta_pct"],row["flow_continuity_complete"],
                row["side_coverage_pct"],row["bid_refill_quote"],row["bid_depletion_quote"],row["ask_refill_quote"],
                row["ask_depletion_quote"],row["bid_same_best_pairs"],row["ask_same_best_pairs"],
                row["bid_replenishment_ratio"],row["ask_replenishment_ratio"],row["orderbook_continuity_complete"],
                row["price_efficiency_bps_per_100m_quote"],row["flow_price_opposition"],row["strong_sell_pressure"],
                row["strong_buy_pressure"],row["price_resilient_to_sell"],row["price_resilient_to_buy"],
                row["passive_buy_absorption_candidate"],row["passive_sell_absorption_candidate"],row["evidence_label"],
                "ws_trade+ws_orderbook+rest_ohlcv",row["received_at"],FEATURE_VERSION,SCHEMA_VERSION,
            ),
        )

    def _prune(self, exchange: str, market: str, window_label: str) -> None:
        self.conn.execute(
            """DELETE FROM research_market_price_flow_divergence_mx
               WHERE rowid IN (
                   SELECT rowid FROM research_market_price_flow_divergence_mx
                   WHERE exchange=? AND market=? AND window_label=?
                   ORDER BY feature_ts DESC LIMIT -1 OFFSET ?
               )""",
            (str(exchange), str(market), str(window_label), WINDOW_FEATURE_RETENTION),
        )

    def compute_pending(self, *, limit: int = MAX_CANDIDATES_PER_RUN, now: float | None = None) -> dict[str, Any]:
        current = float(now or time.time())
        candidates = self._candidate_rows(limit)
        ready = 0
        waiting = 0
        buy_candidates = 0
        sell_candidates = 0
        touched: set[tuple[str, str, str]] = set()
        with self.conn:
            for candidate in candidates:
                price = self._price_candle(candidate)
                derived = self._derive(candidate, price, current)
                self._upsert(derived)
                touched.add((derived["exchange"], derived["market"], derived["window_label"]))
                if derived["data_ready"]:
                    ready += 1
                else:
                    waiting += 1
                buy_candidates += int(derived["passive_buy_absorption_candidate"])
                sell_candidates += int(derived["passive_sell_absorption_candidate"])
            for exchange, market, label in touched:
                self._prune(exchange, market, label)
        return {
            "ok": True,
            "status": "computed" if candidates else "no_eligible_aligned_windows",
            "candidates_scanned": len(candidates),
            "ready_written": ready,
            "waiting_written": waiting,
            "passive_buy_absorption_candidates": buy_candidates,
            "passive_sell_absorption_candidates": sell_candidates,
            "paper_only": True,
            "score_wired": False,
            "can_place_orders": False,
        }

    def audit(self) -> dict[str, Any]:
        table_exists = bool(
            self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_price_flow_divergence_mx'"
            ).fetchone()
        )
        if not table_exists:
            return {"ok": False, "status": "table_missing", "table_exists": False}
        row_count = int(self.conn.execute("SELECT COUNT(*) FROM research_market_price_flow_divergence_mx").fetchone()[0])
        ready_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_price_flow_divergence_mx WHERE data_ready=1"
        ).fetchone()[0])
        waiting_count = row_count - ready_count
        buy_candidates = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_price_flow_divergence_mx WHERE data_ready=1 AND passive_buy_absorption_candidate=1"
        ).fetchone()[0])
        sell_candidates = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_price_flow_divergence_mx WHERE data_ready=1 AND passive_sell_absorption_candidate=1"
        ).fetchone()[0])
        alignment_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_price_flow_divergence_mx
               WHERE data_ready=1 AND (price_candle_ts IS NULL OR price_candle_ts!=window_start_ts)"""
        ).fetchone()[0])
        continuity_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_price_flow_divergence_mx
               WHERE data_ready=1 AND (flow_continuity_complete!=1 OR orderbook_continuity_complete!=1)"""
        ).fetchone()[0])
        latest_ready = [
            dict(row)
            for row in self.conn.execute(
                """SELECT d.* FROM research_market_price_flow_divergence_mx d
                   JOIN (
                       SELECT exchange,market,window_label,MAX(feature_ts) AS max_ts
                       FROM research_market_price_flow_divergence_mx
                       WHERE data_ready=1
                       GROUP BY exchange,market,window_label
                   ) latest
                     ON latest.exchange=d.exchange AND latest.market=d.market
                    AND latest.window_label=d.window_label AND latest.max_ts=d.feature_ts
                   ORDER BY d.exchange,d.market,d.window_seconds"""
            ).fetchall()
        ]
        return {
            "ok": True,
            "status": "ready" if ready_count > 0 else ("waiting" if row_count > 0 else "empty"),
            "table_exists": True,
            "row_count": row_count,
            "ready_rows": ready_count,
            "waiting_rows": waiting_count,
            "passive_buy_absorption_candidates": buy_candidates,
            "passive_sell_absorption_candidates": sell_candidates,
            "alignment_violations": alignment_violations,
            "continuity_violations": continuity_violations,
            "latest_ready": latest_ready,
            "thresholds": {
                "strong_delta_pct": STRONG_DELTA_PCT,
                "max_adverse_return_bps": MAX_ADVERSE_RETURN_BPS,
                "min_replenishment_ratio": MIN_REPLENISHMENT_RATIO,
                "min_replenishment_pairs": MIN_REPLENISHMENT_PAIRS,
                "quote_normalization_krw": QUOTE_NORMALIZATION_KRW,
            },
            "join_contract": "exact_aligned_closed_ohlcv+continuous_ws_trade+continuous_ws_orderbook",
            "source": "ws_trade+ws_orderbook+rest_ohlcv",
            "paper_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "raw_cloud_projection": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
