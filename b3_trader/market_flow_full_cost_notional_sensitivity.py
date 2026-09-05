from __future__ import annotations

import sqlite3
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH, MIN_ORDER_KRW
from .market_fee_schedule import MarketFeeScheduleStore
from .market_orderbook_ladder import MAX_PRIOR_AGE_SECONDS, MarketOrderbookLadderStore

SCHEMA_VERSION = 1
FEATURE_VERSION = 1
REFERENCE_NOTIONALS_KRW = (
    50_000.0,
    250_000.0,
    500_000.0,
    750_000.0,
    1_000_000.0,
    2_000_000.0,
    4_500_000.0,
)


class MarketFlowFullCostNotionalSensitivityStore:
    """Shadow-only transaction-cost sensitivity across PAPER-relevant notionals.

    The canonical 50K full-cost row remains the source of truth. This layer only
    replays the exact same prior-only top-5 ladders and versioned fee profile at
    larger quote notionals. It never backfills missing ladders, changes score,
    mutates strategy, or places orders.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_full_cost_notional_sensitivity_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                signal_window_label TEXT NOT NULL,
                signal_feature_ts REAL NOT NULL,
                signal_evidence_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                reaction_end_ts REAL NOT NULL,
                hypothesis_direction INTEGER NOT NULL,
                gross_hypothesis_return_pct REAL NOT NULL,
                reference_notional_krw REAL NOT NULL,
                entry_ladder_source_ts REAL,
                exit_ladder_source_ts REAL,
                entry_slippage_bps REAL,
                exit_slippage_bps REAL,
                roundtrip_spread_cost_bps REAL,
                entry_fee_bps REAL,
                exit_fee_bps REAL,
                total_transaction_cost_bps REAL,
                full_cost_adjusted_return_pct REAL,
                fee_profile TEXT,
                depth_ready INTEGER NOT NULL DEFAULT 0,
                full_cost_ready INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'full_cost_edge+exact_prior_top5_notional_replay',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(
                    exchange,market,signal_window_label,signal_feature_ts,horizon_label,
                    reference_notional_krw
                )
            );
            CREATE INDEX IF NOT EXISTS idx_full_cost_notional_ready
            ON research_market_flow_full_cost_notional_sensitivity_mx(
                reference_notional_krw,full_cost_ready,signal_feature_ts DESC
            );

            CREATE TABLE IF NOT EXISTS research_market_flow_full_cost_notional_sensitivity_stats_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                reference_notional_krw REAL NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                ready_count INTEGER NOT NULL DEFAULT 0,
                depth_ready_rate_pct REAL,
                mean_total_transaction_cost_bps REAL,
                mean_full_cost_adjusted_return_pct REAL,
                full_cost_adjusted_hit_rate_pct REAL,
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,horizon_label,reference_notional_krw)
            );
            """
        )
        self.conn.commit()

    def _source_rows(self) -> list[dict[str, Any]]:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_full_cost_edge_mx'"
        ).fetchone()
        if not exists:
            return []
        rows = self.conn.execute(
            """SELECT exchange,market,signal_window_label,signal_feature_ts,
                      signal_evidence_label,horizon_label,reaction_end_ts,
                      hypothesis_direction,gross_hypothesis_return_pct
               FROM research_market_flow_full_cost_edge_mx
               WHERE full_cost_edge_ready=1
                 AND fee_model_ready=1
                 AND ladder_slippage_ready=1
               ORDER BY signal_feature_ts,exchange,market"""
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _fill(
        ladder: MarketOrderbookLadderStore,
        snapshot: dict[str, Any],
        direction: int,
        *,
        entry: bool,
        notional: float,
    ) -> dict[str, float] | None:
        if direction > 0:
            return (
                ladder.estimate_buy(snapshot["ask_levels"], notional)
                if entry
                else ladder.estimate_sell(snapshot["bid_levels"], notional)
            )
        if direction < 0:
            return (
                ladder.estimate_sell(snapshot["bid_levels"], notional)
                if entry
                else ladder.estimate_buy(snapshot["ask_levels"], notional)
            )
        return None

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(now or time.time())
        fee_store = MarketFeeScheduleStore(self.path)
        ladder_store = MarketOrderbookLadderStore(self.path)
        status_counts: Counter[str] = Counter()
        attempted = 0
        ready = 0
        try:
            fee_store.ensure_current_catalog(now=stamp)
            rows = self._source_rows()
            for row in rows:
                exchange = str(row["exchange"])
                market = str(row["market"])
                signal_ts = float(row["signal_feature_ts"])
                end_ts = float(row["reaction_end_ts"])
                direction = int(row["hypothesis_direction"])
                gross = float(row["gross_hypothesis_return_pct"])

                entry_fee = fee_store.resolve_taker_fee(exchange, market, signal_ts)
                exit_fee = fee_store.resolve_taker_fee(exchange, market, end_ts)
                fee_profile = str(entry_fee["profile"]) if entry_fee else None
                fee_ready = bool(
                    entry_fee and exit_fee and str(exit_fee["profile"]) == fee_profile
                )

                entry_book = ladder_store.prior_snapshot(
                    exchange, market, signal_ts, max_age_seconds=MAX_PRIOR_AGE_SECONDS
                )
                exit_book = ladder_store.prior_snapshot(
                    exchange, market, end_ts, max_age_seconds=MAX_PRIOR_AGE_SECONDS
                )
                books_ready = bool(entry_book and exit_book)
                entry_spread = ladder_store.spread_bps(entry_book) if entry_book else None
                exit_spread = ladder_store.spread_bps(exit_book) if exit_book else None
                spread_ready = bool(entry_spread is not None and exit_spread is not None)
                roundtrip_spread = (
                    (float(entry_spread) + float(exit_spread)) / 2.0
                    if spread_ready else None
                )

                for notional in REFERENCE_NOTIONALS_KRW:
                    attempted += 1
                    entry_fill = (
                        self._fill(
                            ladder_store, entry_book, direction,
                            entry=True, notional=notional,
                        ) if entry_book else None
                    )
                    exit_fill = (
                        self._fill(
                            ladder_store, exit_book, direction,
                            entry=False, notional=notional,
                        ) if exit_book else None
                    )
                    depth_ready = bool(books_ready and entry_fill and exit_fill)
                    full_ready = bool(fee_ready and spread_ready and depth_ready)

                    entry_slippage = float(entry_fill["slippage_bps"]) if entry_fill else None
                    exit_slippage = float(exit_fill["slippage_bps"]) if exit_fill else None
                    entry_fee_bps = float(entry_fee["taker_fee_bps"]) if entry_fee else None
                    exit_fee_bps = float(exit_fee["taker_fee_bps"]) if exit_fee else None
                    total_cost = (
                        float(roundtrip_spread)
                        + float(entry_slippage)
                        + float(exit_slippage)
                        + float(entry_fee_bps)
                        + float(exit_fee_bps)
                        if full_ready else None
                    )
                    adjusted = gross - total_cost / 100.0 if total_cost is not None else None

                    if not fee_ready:
                        status = "waiting_versioned_fee_profile"
                    elif not books_ready:
                        status = "waiting_prior_only_ladder"
                    elif not spread_ready:
                        status = "waiting_spread"
                    elif not depth_ready:
                        status = "insufficient_top5_depth"
                    else:
                        status = "full_cost_ready"

                    self.conn.execute(
                        """INSERT INTO research_market_flow_full_cost_notional_sensitivity_mx(
                               exchange,market,signal_window_label,signal_feature_ts,
                               signal_evidence_label,horizon_label,reaction_end_ts,
                               hypothesis_direction,gross_hypothesis_return_pct,reference_notional_krw,
                               entry_ladder_source_ts,exit_ladder_source_ts,
                               entry_slippage_bps,exit_slippage_bps,roundtrip_spread_cost_bps,
                               entry_fee_bps,exit_fee_bps,total_transaction_cost_bps,
                               full_cost_adjusted_return_pct,fee_profile,depth_ready,full_cost_ready,
                               status,source,received_at,feature_version,schema_version
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                                    'full_cost_edge+exact_prior_top5_notional_replay',?,?,?)
                           ON CONFLICT(
                               exchange,market,signal_window_label,signal_feature_ts,horizon_label,
                               reference_notional_krw
                           ) DO UPDATE SET
                               signal_evidence_label=excluded.signal_evidence_label,
                               reaction_end_ts=excluded.reaction_end_ts,
                               hypothesis_direction=excluded.hypothesis_direction,
                               gross_hypothesis_return_pct=excluded.gross_hypothesis_return_pct,
                               entry_ladder_source_ts=excluded.entry_ladder_source_ts,
                               exit_ladder_source_ts=excluded.exit_ladder_source_ts,
                               entry_slippage_bps=excluded.entry_slippage_bps,
                               exit_slippage_bps=excluded.exit_slippage_bps,
                               roundtrip_spread_cost_bps=excluded.roundtrip_spread_cost_bps,
                               entry_fee_bps=excluded.entry_fee_bps,
                               exit_fee_bps=excluded.exit_fee_bps,
                               total_transaction_cost_bps=excluded.total_transaction_cost_bps,
                               full_cost_adjusted_return_pct=excluded.full_cost_adjusted_return_pct,
                               fee_profile=excluded.fee_profile,
                               depth_ready=excluded.depth_ready,
                               full_cost_ready=excluded.full_cost_ready,
                               status=excluded.status,
                               received_at=excluded.received_at,
                               feature_version=excluded.feature_version,
                               schema_version=excluded.schema_version""",
                        (
                            exchange,market,str(row["signal_window_label"]),signal_ts,
                            str(row["signal_evidence_label"]),str(row["horizon_label"]),end_ts,
                            direction,gross,float(notional),
                            float(entry_book["source_ts"]) if entry_book else None,
                            float(exit_book["source_ts"]) if exit_book else None,
                            entry_slippage,exit_slippage,roundtrip_spread,
                            entry_fee_bps,exit_fee_bps,total_cost,adjusted,fee_profile,
                            1 if depth_ready else 0,1 if full_ready else 0,status,
                            stamp,FEATURE_VERSION,SCHEMA_VERSION,
                        ),
                    )
                    status_counts[status] += 1
                    ready += 1 if full_ready else 0

            self.conn.execute("DELETE FROM research_market_flow_full_cost_notional_sensitivity_stats_mx")
            stat_groups = self.conn.execute(
                """SELECT exchange,market,horizon_label,reference_notional_krw,
                          COUNT(*) AS sample_count,
                          SUM(full_cost_ready) AS ready_count,
                          100.0*AVG(CASE WHEN depth_ready=1 THEN 1.0 ELSE 0.0 END) AS depth_rate
                   FROM research_market_flow_full_cost_notional_sensitivity_mx
                   GROUP BY exchange,market,horizon_label,reference_notional_krw"""
            ).fetchall()
            for group in stat_groups:
                values = self.conn.execute(
                    """SELECT total_transaction_cost_bps,full_cost_adjusted_return_pct
                       FROM research_market_flow_full_cost_notional_sensitivity_mx
                       WHERE exchange=? AND market=? AND horizon_label=?
                         AND reference_notional_krw=? AND full_cost_ready=1""",
                    (group["exchange"],group["market"],group["horizon_label"],group["reference_notional_krw"]),
                ).fetchall()
                costs = [float(value[0]) for value in values if value[0] is not None]
                adjusted = [float(value[1]) for value in values if value[1] is not None]
                self.conn.execute(
                    """INSERT INTO research_market_flow_full_cost_notional_sensitivity_stats_mx(
                           exchange,market,horizon_label,reference_notional_krw,
                           sample_count,ready_count,depth_ready_rate_pct,
                           mean_total_transaction_cost_bps,mean_full_cost_adjusted_return_pct,
                           full_cost_adjusted_hit_rate_pct,received_at,feature_version,schema_version
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        group["exchange"],group["market"],group["horizon_label"],
                        float(group["reference_notional_krw"]),int(group["sample_count"]),
                        int(group["ready_count"] or 0),float(group["depth_rate"] or 0.0),
                        statistics.fmean(costs) if costs else None,
                        statistics.fmean(adjusted) if adjusted else None,
                        (sum(1 for value in adjusted if value > 0.0) / len(adjusted) * 100.0)
                        if adjusted else None,
                        stamp,FEATURE_VERSION,SCHEMA_VERSION,
                    ),
                )
            self.conn.commit()
            return {
                "ok": True,
                "status": "computed" if rows else "waiting_for_canonical_full_cost_rows",
                "source_full_cost_rows": len(rows),
                "attempted_notional_rows": attempted,
                "ready_notional_rows": ready,
                "status_counts": dict(status_counts),
                "reference_notionals_krw": list(REFERENCE_NOTIONALS_KRW),
                "canonical_baseline_notional_krw": float(MIN_ORDER_KRW),
                "paper_base_notional_krw": 750_000.0,
                "paper_max_position_notional_krw": 4_500_000.0,
                "historical_ladder_backfill": False,
                "paper_only": True,
                "shadow_only": True,
                "score_wired": False,
                "can_place_orders": False,
                "can_modify_strategy": False,
            }
        finally:
            ladder_store.close()
            fee_store.close()

    def audit(self) -> dict[str, Any]:
        row_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_full_cost_notional_sensitivity_mx"
        ).fetchone()[0])
        ready_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_full_cost_notional_sensitivity_mx WHERE full_cost_ready=1"
        ).fetchone()[0])

        baseline_mismatch = int(self.conn.execute(
            """SELECT COUNT(*)
               FROM research_market_flow_full_cost_notional_sensitivity_mx s
               JOIN research_market_flow_full_cost_edge_mx c
                 ON c.exchange=s.exchange AND c.market=s.market
                AND c.signal_window_label=s.signal_window_label
                AND c.signal_feature_ts=s.signal_feature_ts
                AND c.horizon_label=s.horizon_label
               WHERE s.reference_notional_krw=?
                 AND s.full_cost_ready=1 AND c.full_cost_edge_ready=1
                 AND (
                     ABS(s.total_transaction_cost_bps-c.total_transaction_cost_bps)>0.000001
                     OR ABS(s.full_cost_adjusted_return_pct-c.full_cost_adjusted_return_pct)>0.000001
                 )""",
            (float(MIN_ORDER_KRW),),
        ).fetchone()[0])

        monotonic_cost_violations = int(self.conn.execute(
            """WITH ordered AS (
                   SELECT exchange,market,signal_window_label,signal_feature_ts,horizon_label,
                          reference_notional_krw,total_transaction_cost_bps,
                          LAG(total_transaction_cost_bps) OVER (
                              PARTITION BY exchange,market,signal_window_label,signal_feature_ts,horizon_label
                              ORDER BY reference_notional_krw
                          ) AS prev_cost
                   FROM research_market_flow_full_cost_notional_sensitivity_mx
                   WHERE full_cost_ready=1
               )
               SELECT COUNT(*) FROM ordered
               WHERE prev_cost IS NOT NULL AND total_transaction_cost_bps+0.000001<prev_cost"""
        ).fetchone()[0])

        depth_monotonic_violations = int(self.conn.execute(
            """SELECT COUNT(*)
               FROM research_market_flow_full_cost_notional_sensitivity_mx small
               JOIN research_market_flow_full_cost_notional_sensitivity_mx large
                 ON large.exchange=small.exchange AND large.market=small.market
                AND large.signal_window_label=small.signal_window_label
                AND large.signal_feature_ts=small.signal_feature_ts
                AND large.horizon_label=small.horizon_label
                AND large.reference_notional_krw>small.reference_notional_krw
               WHERE small.depth_ready=0 AND large.depth_ready=1"""
        ).fetchone()[0])

        notionals = [
            float(row[0]) for row in self.conn.execute(
                "SELECT DISTINCT reference_notional_krw FROM research_market_flow_full_cost_notional_sensitivity_mx ORDER BY reference_notional_krw"
            ).fetchall()
        ]
        stats = [
            dict(row) for row in self.conn.execute(
                """SELECT * FROM research_market_flow_full_cost_notional_sensitivity_stats_mx
                   ORDER BY exchange,market,horizon_label,reference_notional_krw"""
            ).fetchall()
        ]
        ok = (
            baseline_mismatch == 0
            and monotonic_cost_violations == 0
            and depth_monotonic_violations == 0
            and (not notionals or notionals == list(REFERENCE_NOTIONALS_KRW))
        )
        return {
            "ok": ok,
            "status": "ready" if row_count else "waiting_for_forward_full_cost_rows",
            "row_count": row_count,
            "ready_row_count": ready_count,
            "reference_notionals_krw": notionals,
            "expected_reference_notionals_krw": list(REFERENCE_NOTIONALS_KRW),
            "baseline_50k_mismatch_count": baseline_mismatch,
            "cost_monotonicity_violations": monotonic_cost_violations,
            "depth_monotonicity_violations": depth_monotonic_violations,
            "stats": stats,
            "historical_ladder_backfill": False,
            "raw_cloud_projection": False,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
