from __future__ import annotations

import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH, MIN_ORDER_KRW
from .market_fee_schedule import MarketFeeScheduleStore
from .market_orderbook_ladder import MAX_PRIOR_AGE_SECONDS, MarketOrderbookLadderStore

SCHEMA_VERSION = 1
FEATURE_VERSION = 1


class MarketFlowFullCostEdgeStore:
    """Forward-only full transaction-cost view over ready flow reactions.

    Gross directional returns are inherited from the existing reaction/cost-edge
    layer, but transaction friction is recomputed from exact prior-only top-5
    orderbook ladders plus a versioned taker-fee schedule. No historical ladder
    or fee backfill is permitted. Bithumb remains fail-closed until an account
    fee profile is explicitly selected locally.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_full_cost_edge_mx(
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
                entry_ladder_age_seconds REAL,
                exit_ladder_age_seconds REAL,
                entry_spread_bps REAL,
                exit_spread_bps REAL,
                roundtrip_spread_cost_bps REAL,
                entry_slippage_bps REAL,
                exit_slippage_bps REAL,
                entry_fee_bps REAL,
                exit_fee_bps REAL,
                total_transaction_cost_bps REAL,
                full_cost_adjusted_return_pct REAL,
                fee_profile TEXT,
                fee_model_ready INTEGER NOT NULL DEFAULT 0,
                ladder_slippage_ready INTEGER NOT NULL DEFAULT 0,
                full_cost_edge_ready INTEGER NOT NULL DEFAULT 0,
                cost_status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'flow_reaction+prior_top5_ladder+versioned_fee',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,signal_window_label,signal_feature_ts,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_full_cost_ready
            ON research_market_flow_full_cost_edge_mx(full_cost_edge_ready,horizon_label,signal_feature_ts DESC);

            CREATE TABLE IF NOT EXISTS research_market_flow_full_cost_edge_stats_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                signal_window_label TEXT NOT NULL,
                signal_evidence_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                full_cost_ready_count INTEGER NOT NULL DEFAULT 0,
                mean_gross_hypothesis_return_pct REAL,
                mean_total_transaction_cost_bps REAL,
                mean_full_cost_adjusted_return_pct REAL,
                full_cost_adjusted_hit_rate_pct REAL,
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,signal_window_label,signal_evidence_label,horizon_label)
            );
            """
        )
        self.conn.commit()

    def _source_rows(self) -> list[dict[str, Any]]:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_cost_edge_mx'"
        ).fetchone()
        if not exists:
            return []
        rows = self.conn.execute(
            """SELECT exchange,market,signal_window_label,signal_feature_ts,signal_evidence_label,
                      horizon_label,reaction_end_ts,hypothesis_direction,gross_hypothesis_return_pct
               FROM research_market_flow_cost_edge_mx
               WHERE orderbook_friction_ready=1
               ORDER BY signal_feature_ts DESC"""
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _fill_for_direction(
        ladder: MarketOrderbookLadderStore,
        snapshot: dict[str, Any],
        direction: int,
        *,
        entry: bool,
        quote_notional: float,
    ) -> dict[str, float] | None:
        if direction > 0:
            return (
                ladder.estimate_buy(snapshot["ask_levels"], quote_notional)
                if entry
                else ladder.estimate_sell(snapshot["bid_levels"], quote_notional)
            )
        if direction < 0:
            return (
                ladder.estimate_sell(snapshot["bid_levels"], quote_notional)
                if entry
                else ladder.estimate_buy(snapshot["ask_levels"], quote_notional)
            )
        return None

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(now or time.time())
        fee_store = MarketFeeScheduleStore(self.path)
        ladder_store = MarketOrderbookLadderStore(self.path)
        try:
            fee_store.ensure_current_catalog(now=stamp)
            rows = self._source_rows()
            self.conn.execute("DELETE FROM research_market_flow_full_cost_edge_mx")
            self.conn.execute("DELETE FROM research_market_flow_full_cost_edge_stats_mx")

            status_counts: Counter[str] = Counter()
            full_ready_rows = 0
            grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)

            for source_row in rows:
                exchange = str(source_row["exchange"])
                market = str(source_row["market"])
                signal_ts = float(source_row["signal_feature_ts"])
                end_ts = float(source_row["reaction_end_ts"])
                direction = int(source_row.get("hypothesis_direction") or 0)
                gross = float(source_row["gross_hypothesis_return_pct"])
                reference_notional = float(MIN_ORDER_KRW)

                entry_fee = fee_store.resolve_taker_fee(exchange, market, signal_ts)
                exit_fee = fee_store.resolve_taker_fee(exchange, market, end_ts)
                fee_ready = bool(entry_fee and exit_fee)
                fee_profile = str(entry_fee.get("profile")) if entry_fee else None
                if fee_ready and str(exit_fee.get("profile")) != fee_profile:
                    fee_ready = False
                    fee_profile = None

                entry_book = ladder_store.prior_snapshot(
                    exchange, market, signal_ts, max_age_seconds=MAX_PRIOR_AGE_SECONDS
                )
                exit_book = ladder_store.prior_snapshot(
                    exchange, market, end_ts, max_age_seconds=MAX_PRIOR_AGE_SECONDS
                )
                ladder_present = bool(entry_book and exit_book)

                entry_spread = ladder_store.spread_bps(entry_book) if entry_book else None
                exit_spread = ladder_store.spread_bps(exit_book) if exit_book else None
                entry_fill = (
                    self._fill_for_direction(
                        ladder_store, entry_book, direction, entry=True, quote_notional=reference_notional
                    )
                    if entry_book else None
                )
                exit_fill = (
                    self._fill_for_direction(
                        ladder_store, exit_book, direction, entry=False, quote_notional=reference_notional
                    )
                    if exit_book else None
                )
                ladder_ready = bool(
                    ladder_present and entry_spread is not None and exit_spread is not None
                    and entry_fill is not None and exit_fill is not None
                )

                roundtrip_spread = (
                    (float(entry_spread) + float(exit_spread)) / 2.0
                    if ladder_ready else None
                )
                entry_slippage = float(entry_fill["slippage_bps"]) if entry_fill else None
                exit_slippage = float(exit_fill["slippage_bps"]) if exit_fill else None
                entry_fee_bps = float(entry_fee["taker_fee_bps"]) if entry_fee else None
                exit_fee_bps = float(exit_fee["taker_fee_bps"]) if exit_fee else None
                full_ready = bool(fee_ready and ladder_ready)
                total_cost_bps = (
                    float(roundtrip_spread)
                    + float(entry_slippage)
                    + float(exit_slippage)
                    + float(entry_fee_bps)
                    + float(exit_fee_bps)
                    if full_ready else None
                )
                adjusted = gross - float(total_cost_bps) / 100.0 if total_cost_bps is not None else None

                if not fee_ready:
                    status = "waiting_versioned_fee_profile"
                elif not ladder_present:
                    status = "waiting_prior_only_ladder"
                elif not ladder_ready:
                    status = "waiting_top5_depth"
                else:
                    status = "full_cost_ready"

                record = {
                    **source_row,
                    "reference_notional_krw": reference_notional,
                    "entry_ladder_source_ts": float(entry_book["source_ts"]) if entry_book else None,
                    "exit_ladder_source_ts": float(exit_book["source_ts"]) if exit_book else None,
                    "entry_ladder_age_seconds": float(entry_book["age_seconds"]) if entry_book else None,
                    "exit_ladder_age_seconds": float(exit_book["age_seconds"]) if exit_book else None,
                    "entry_spread_bps": entry_spread,
                    "exit_spread_bps": exit_spread,
                    "roundtrip_spread_cost_bps": roundtrip_spread,
                    "entry_slippage_bps": entry_slippage,
                    "exit_slippage_bps": exit_slippage,
                    "entry_fee_bps": entry_fee_bps,
                    "exit_fee_bps": exit_fee_bps,
                    "total_transaction_cost_bps": total_cost_bps,
                    "full_cost_adjusted_return_pct": adjusted,
                    "fee_profile": fee_profile,
                    "fee_model_ready": 1 if fee_ready else 0,
                    "ladder_slippage_ready": 1 if ladder_ready else 0,
                    "full_cost_edge_ready": 1 if full_ready else 0,
                    "cost_status": status,
                }
                self.conn.execute(
                    """INSERT INTO research_market_flow_full_cost_edge_mx(
                           exchange,market,signal_window_label,signal_feature_ts,signal_evidence_label,
                           horizon_label,reaction_end_ts,hypothesis_direction,gross_hypothesis_return_pct,
                           reference_notional_krw,entry_ladder_source_ts,exit_ladder_source_ts,
                           entry_ladder_age_seconds,exit_ladder_age_seconds,entry_spread_bps,exit_spread_bps,
                           roundtrip_spread_cost_bps,entry_slippage_bps,exit_slippage_bps,
                           entry_fee_bps,exit_fee_bps,total_transaction_cost_bps,
                           full_cost_adjusted_return_pct,fee_profile,fee_model_ready,ladder_slippage_ready,
                           full_cost_edge_ready,cost_status,source,received_at,feature_version,schema_version
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                                'flow_reaction+prior_top5_ladder+versioned_fee',?,?,?)""",
                    (
                        record["exchange"],record["market"],record["signal_window_label"],
                        record["signal_feature_ts"],record["signal_evidence_label"],record["horizon_label"],
                        record["reaction_end_ts"],record["hypothesis_direction"],
                        record["gross_hypothesis_return_pct"],record["reference_notional_krw"],
                        record["entry_ladder_source_ts"],record["exit_ladder_source_ts"],
                        record["entry_ladder_age_seconds"],record["exit_ladder_age_seconds"],
                        record["entry_spread_bps"],record["exit_spread_bps"],
                        record["roundtrip_spread_cost_bps"],record["entry_slippage_bps"],
                        record["exit_slippage_bps"],record["entry_fee_bps"],record["exit_fee_bps"],
                        record["total_transaction_cost_bps"],record["full_cost_adjusted_return_pct"],
                        record["fee_profile"],record["fee_model_ready"],record["ladder_slippage_ready"],
                        record["full_cost_edge_ready"],record["cost_status"],stamp,FEATURE_VERSION,SCHEMA_VERSION,
                    ),
                )
                status_counts[status] += 1
                full_ready_rows += 1 if full_ready else 0
                grouped[(
                    exchange,market,str(source_row["signal_window_label"]),
                    str(source_row["signal_evidence_label"]),str(source_row["horizon_label"]),
                )].append(record)

            for key, group_rows in grouped.items():
                ready = [row for row in group_rows if int(row["full_cost_edge_ready"]) == 1]
                gross_values = [float(row["gross_hypothesis_return_pct"]) for row in group_rows]
                costs = [float(row["total_transaction_cost_bps"]) for row in ready]
                adjusted_values = [float(row["full_cost_adjusted_return_pct"]) for row in ready]
                self.conn.execute(
                    """INSERT INTO research_market_flow_full_cost_edge_stats_mx(
                           exchange,market,signal_window_label,signal_evidence_label,horizon_label,
                           sample_count,full_cost_ready_count,mean_gross_hypothesis_return_pct,
                           mean_total_transaction_cost_bps,mean_full_cost_adjusted_return_pct,
                           full_cost_adjusted_hit_rate_pct,received_at,feature_version,schema_version
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        *key,len(group_rows),len(ready),statistics.fmean(gross_values) if gross_values else None,
                        statistics.fmean(costs) if costs else None,
                        statistics.fmean(adjusted_values) if adjusted_values else None,
                        (sum(1 for value in adjusted_values if value > 0.0) / len(adjusted_values) * 100.0)
                        if adjusted_values else None,
                        stamp,FEATURE_VERSION,SCHEMA_VERSION,
                    ),
                )
            self.conn.commit()
            return {
                "ok": True,
                "status": "computed" if rows else "waiting_for_spread_ready_source_rows",
                "source_rows": len(rows),
                "full_cost_ready_rows": full_ready_rows,
                "status_counts": dict(status_counts),
                "reference_notional_krw": float(MIN_ORDER_KRW),
                "max_prior_ladder_age_seconds": MAX_PRIOR_AGE_SECONDS,
                "full_cost_formula": "gross - (half_entry_spread+half_exit_spread+entry_slippage+exit_slippage+entry_taker_fee+exit_taker_fee)",
                "historical_ladder_backfill": False,
                "historical_fee_backfill": False,
                "bithumb_profile_must_be_selected": True,
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
        exists = bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_full_cost_edge_mx'"
        ).fetchone())
        if not exists:
            return {"ok": True,"status": "waiting_for_table","table_exists": False,"row_count": 0}
        row_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_full_cost_edge_mx"
        ).fetchone()[0])
        ready_rows = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_full_cost_edge_mx WHERE full_cost_edge_ready=1"
        ).fetchone()[0])
        readiness_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_full_cost_edge_mx
               WHERE full_cost_edge_ready=1 AND (
                   fee_model_ready!=1 OR ladder_slippage_ready!=1
                   OR entry_ladder_source_ts IS NULL OR exit_ladder_source_ts IS NULL
                   OR entry_ladder_source_ts>=signal_feature_ts
                   OR exit_ladder_source_ts>=reaction_end_ts
                   OR entry_ladder_age_seconds<=0 OR entry_ladder_age_seconds>?
                   OR exit_ladder_age_seconds<=0 OR exit_ladder_age_seconds>?
                   OR entry_spread_bps IS NULL OR exit_spread_bps IS NULL
                   OR roundtrip_spread_cost_bps IS NULL
                   OR entry_slippage_bps IS NULL OR exit_slippage_bps IS NULL
                   OR entry_fee_bps IS NULL OR exit_fee_bps IS NULL
                   OR total_transaction_cost_bps IS NULL
                   OR full_cost_adjusted_return_pct IS NULL
               )""",
            (MAX_PRIOR_AGE_SECONDS, MAX_PRIOR_AGE_SECONDS),
        ).fetchone()[0])
        formula_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_full_cost_edge_mx
               WHERE full_cost_edge_ready=1 AND (
                   ABS(roundtrip_spread_cost_bps-((entry_spread_bps+exit_spread_bps)/2.0))>0.000001
                   OR ABS(total_transaction_cost_bps-(roundtrip_spread_cost_bps+entry_slippage_bps+
                        exit_slippage_bps+entry_fee_bps+exit_fee_bps))>0.000001
                   OR ABS(full_cost_adjusted_return_pct-(gross_hypothesis_return_pct-
                        total_transaction_cost_bps/100.0))>0.000001
               )"""
        ).fetchone()[0])
        future_ladder_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_full_cost_edge_mx
               WHERE (entry_ladder_source_ts IS NOT NULL AND entry_ladder_source_ts>=signal_feature_ts)
                  OR (exit_ladder_source_ts IS NOT NULL AND exit_ladder_source_ts>=reaction_end_ts)"""
        ).fetchone()[0])
        safety_columns = {
            str(row[1])
            for row in self.conn.execute("PRAGMA table_info(research_market_flow_full_cost_edge_mx)").fetchall()
        }
        suspicious = sorted(
            column for column in safety_columns
            if "trade_intent" in column.lower() or "order_qty" in column.lower()
            or "position_size" in column.lower()
        )
        status_counts = {
            str(row["cost_status"]): int(row["n"])
            for row in self.conn.execute(
                "SELECT cost_status,COUNT(*) AS n FROM research_market_flow_full_cost_edge_mx GROUP BY cost_status"
            ).fetchall()
        }
        sample_ready = [
            dict(row)
            for row in self.conn.execute(
                """SELECT * FROM research_market_flow_full_cost_edge_mx
                   WHERE full_cost_edge_ready=1 ORDER BY signal_feature_ts DESC LIMIT 20"""
            ).fetchall()
        ]
        return {
            "ok": readiness_violations == 0 and formula_violations == 0 and future_ladder_violations == 0 and not suspicious,
            "status": "ready",
            "table_exists": True,
            "row_count": row_count,
            "full_cost_ready_rows": ready_rows,
            "status_counts": status_counts,
            "readiness_contract_violations": readiness_violations,
            "formula_contract_violations": formula_violations,
            "future_ladder_violations": future_ladder_violations,
            "suspicious_wiring_columns": suspicious,
            "sample_ready_rows": sample_ready,
            "max_prior_ladder_age_seconds": MAX_PRIOR_AGE_SECONDS,
            "historical_ladder_backfill": False,
            "historical_fee_backfill": False,
            "raw_cloud_projection": False,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
