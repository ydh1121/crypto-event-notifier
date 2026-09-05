from __future__ import annotations

import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH, MIN_ORDER_KRW

SCHEMA_VERSION = 1
FEATURE_VERSION = 1
ORDERBOOK_WINDOW_LABEL = "1m"
ABSORPTION_LABELS = (
    "passive_buy_absorption_candidate",
    "passive_sell_absorption_candidate",
)


class MarketFlowCostEdgeStore:
    """Shadow-only execution-friction view over ready flow reactions.

    This layer does not pretend that a complete historical transaction-cost model
    exists. Exact continuous 1-minute orderbook windows are used only to estimate
    the round-trip spread penalty and to record relevant top-5 depth. Historical
    price-ladder snapshots are not retained, so past slippage cannot be replayed
    with ``estimate_buy``/``estimate_sell``. No versioned fee schedule currently
    exists either. Therefore ``full_cost_edge_ready`` is intentionally fail-closed
    at zero and ``full_cost_adjusted_return_pct`` remains NULL.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_cost_edge_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                signal_window_label TEXT NOT NULL,
                signal_feature_ts REAL NOT NULL,
                signal_evidence_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                reaction_end_ts REAL NOT NULL,
                hypothesis_direction INTEGER NOT NULL,
                gross_hypothesis_return_pct REAL NOT NULL,
                entry_spread_bps REAL,
                exit_spread_bps REAL,
                roundtrip_spread_cost_bps REAL,
                spread_adjusted_hypothesis_return_pct REAL,
                entry_relevant_top5_depth_quote REAL,
                exit_relevant_top5_depth_quote REAL,
                reference_notional_krw REAL NOT NULL,
                max_reference_notional_share_pct REAL,
                orderbook_friction_ready INTEGER NOT NULL DEFAULT 0,
                fee_model_ready INTEGER NOT NULL DEFAULT 0,
                slippage_model_ready INTEGER NOT NULL DEFAULT 0,
                full_cost_edge_ready INTEGER NOT NULL DEFAULT 0,
                full_cost_adjusted_return_pct REAL,
                cost_status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'flow_reaction+ws_orderbook_window',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,signal_window_label,signal_feature_ts,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_cost_edge_ready
            ON research_market_flow_cost_edge_mx(orderbook_friction_ready,horizon_label,signal_feature_ts DESC);

            CREATE TABLE IF NOT EXISTS research_market_flow_cost_edge_stats_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                signal_window_label TEXT NOT NULL,
                signal_evidence_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                spread_ready_count INTEGER NOT NULL DEFAULT 0,
                mean_gross_hypothesis_return_pct REAL,
                mean_roundtrip_spread_cost_bps REAL,
                mean_spread_adjusted_hypothesis_return_pct REAL,
                spread_adjusted_hit_rate_pct REAL,
                full_cost_ready_count INTEGER NOT NULL DEFAULT 0,
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,signal_window_label,signal_evidence_label,horizon_label)
            );
            """
        )
        self.conn.commit()

    def _reaction_rows(self) -> list[dict[str, Any]]:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_reaction_mx'"
        ).fetchone()
        if not exists:
            return []
        rows = self.conn.execute(
            """SELECT exchange,market,signal_window_label,signal_feature_ts,
                      signal_evidence_label,horizon_label,reaction_end_ts,
                      hypothesis_direction,hypothesis_directional_return_pct
               FROM research_market_flow_reaction_mx
               WHERE data_ready=1
                 AND signal_evidence_label IN (?,?)
                 AND hypothesis_directional_return_pct IS NOT NULL
               ORDER BY signal_feature_ts DESC""",
            ABSORPTION_LABELS,
        ).fetchall()
        return [dict(row) for row in rows]

    def _book_window(self, exchange: str, market: str, feature_ts: float) -> dict[str, Any] | None:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_orderbook_window_feature_mx'"
        ).fetchone()
        if not exists:
            return None
        row = self.conn.execute(
            """SELECT spread_bps_avg,bid_depth_quote_avg,ask_depth_quote_avg,continuity_complete
               FROM research_market_orderbook_window_feature_mx
               WHERE exchange=? AND market=? AND window_label=? AND feature_ts=?""",
            (exchange, market, ORDERBOOK_WINDOW_LABEL, float(feature_ts)),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _finite_nonnegative(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number < 0 or number != number or number in (float("inf"), float("-inf")):
            return None
        return number

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(now or time.time())
        reactions = self._reaction_rows()
        self.conn.execute("DELETE FROM research_market_flow_cost_edge_mx")
        self.conn.execute("DELETE FROM research_market_flow_cost_edge_stats_mx")

        status_counts: Counter[str] = Counter()
        ready_rows = 0
        grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)

        for reaction in reactions:
            exchange = str(reaction["exchange"])
            market = str(reaction["market"])
            signal_ts = float(reaction["signal_feature_ts"])
            end_ts = float(reaction["reaction_end_ts"])
            hypothesis_direction = int(reaction.get("hypothesis_direction") or 0)
            gross_return = float(reaction["hypothesis_directional_return_pct"])
            entry = self._book_window(exchange, market, signal_ts)
            exit_book = self._book_window(exchange, market, end_ts)

            entry_spread = self._finite_nonnegative(entry.get("spread_bps_avg")) if entry else None
            exit_spread = self._finite_nonnegative(exit_book.get("spread_bps_avg")) if exit_book else None
            entry_continuous = bool(entry and int(entry.get("continuity_complete") or 0) == 1)
            exit_continuous = bool(exit_book and int(exit_book.get("continuity_complete") or 0) == 1)
            friction_ready = bool(
                entry_continuous and exit_continuous
                and entry_spread is not None and exit_spread is not None
            )

            entry_depth = None
            exit_depth = None
            if entry and exit_book and hypothesis_direction != 0:
                if hypothesis_direction > 0:
                    entry_depth = self._finite_nonnegative(entry.get("ask_depth_quote_avg"))
                    exit_depth = self._finite_nonnegative(exit_book.get("bid_depth_quote_avg"))
                else:
                    entry_depth = self._finite_nonnegative(entry.get("bid_depth_quote_avg"))
                    exit_depth = self._finite_nonnegative(exit_book.get("ask_depth_quote_avg"))

            spread_cost_bps = ((entry_spread + exit_spread) / 2.0) if friction_ready else None
            spread_adjusted = (
                gross_return - spread_cost_bps / 100.0
                if spread_cost_bps is not None
                else None
            )
            depth_shares = [
                float(MIN_ORDER_KRW) / depth * 100.0
                for depth in (entry_depth, exit_depth)
                if depth is not None and depth > 0
            ]
            max_notional_share = max(depth_shares) if len(depth_shares) == 2 else None
            cost_status = (
                "spread_only_fee_and_historical_ladder_missing"
                if friction_ready
                else "waiting_exact_continuous_orderbook_windows"
            )

            row = {
                "exchange": exchange,
                "market": market,
                "signal_window_label": str(reaction["signal_window_label"]),
                "signal_feature_ts": signal_ts,
                "signal_evidence_label": str(reaction["signal_evidence_label"]),
                "horizon_label": str(reaction["horizon_label"]),
                "reaction_end_ts": end_ts,
                "hypothesis_direction": hypothesis_direction,
                "gross_hypothesis_return_pct": gross_return,
                "entry_spread_bps": entry_spread,
                "exit_spread_bps": exit_spread,
                "roundtrip_spread_cost_bps": spread_cost_bps,
                "spread_adjusted_hypothesis_return_pct": spread_adjusted,
                "entry_relevant_top5_depth_quote": entry_depth,
                "exit_relevant_top5_depth_quote": exit_depth,
                "reference_notional_krw": float(MIN_ORDER_KRW),
                "max_reference_notional_share_pct": max_notional_share,
                "orderbook_friction_ready": 1 if friction_ready else 0,
                "cost_status": cost_status,
            }
            self.conn.execute(
                """INSERT INTO research_market_flow_cost_edge_mx(
                       exchange,market,signal_window_label,signal_feature_ts,signal_evidence_label,
                       horizon_label,reaction_end_ts,hypothesis_direction,gross_hypothesis_return_pct,
                       entry_spread_bps,exit_spread_bps,roundtrip_spread_cost_bps,
                       spread_adjusted_hypothesis_return_pct,entry_relevant_top5_depth_quote,
                       exit_relevant_top5_depth_quote,reference_notional_krw,
                       max_reference_notional_share_pct,orderbook_friction_ready,
                       fee_model_ready,slippage_model_ready,full_cost_edge_ready,
                       full_cost_adjusted_return_pct,cost_status,source,received_at,
                       feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,0,NULL,?,
                            'flow_reaction+ws_orderbook_window',?,?,?)""",
                (
                    row["exchange"],row["market"],row["signal_window_label"],row["signal_feature_ts"],
                    row["signal_evidence_label"],row["horizon_label"],row["reaction_end_ts"],
                    row["hypothesis_direction"],row["gross_hypothesis_return_pct"],row["entry_spread_bps"],
                    row["exit_spread_bps"],row["roundtrip_spread_cost_bps"],
                    row["spread_adjusted_hypothesis_return_pct"],row["entry_relevant_top5_depth_quote"],
                    row["exit_relevant_top5_depth_quote"],row["reference_notional_krw"],
                    row["max_reference_notional_share_pct"],row["orderbook_friction_ready"],
                    row["cost_status"],stamp,FEATURE_VERSION,SCHEMA_VERSION,
                ),
            )
            status_counts[cost_status] += 1
            ready_rows += 1 if friction_ready else 0
            grouped[(
                exchange,market,row["signal_window_label"],row["signal_evidence_label"],row["horizon_label"]
            )].append(row)

        for key, rows in grouped.items():
            spread_rows = [row for row in rows if int(row["orderbook_friction_ready"]) == 1]
            gross = [float(row["gross_hypothesis_return_pct"]) for row in rows]
            spread_costs = [float(row["roundtrip_spread_cost_bps"]) for row in spread_rows]
            adjusted = [float(row["spread_adjusted_hypothesis_return_pct"]) for row in spread_rows]
            self.conn.execute(
                """INSERT INTO research_market_flow_cost_edge_stats_mx(
                       exchange,market,signal_window_label,signal_evidence_label,horizon_label,
                       sample_count,spread_ready_count,mean_gross_hypothesis_return_pct,
                       mean_roundtrip_spread_cost_bps,mean_spread_adjusted_hypothesis_return_pct,
                       spread_adjusted_hit_rate_pct,full_cost_ready_count,received_at,
                       feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    *key,len(rows),len(spread_rows),statistics.fmean(gross) if gross else None,
                    statistics.fmean(spread_costs) if spread_costs else None,
                    statistics.fmean(adjusted) if adjusted else None,
                    (sum(1 for value in adjusted if value > 0) / len(adjusted) * 100.0) if adjusted else None,
                    0,stamp,FEATURE_VERSION,SCHEMA_VERSION,
                ),
            )

        self.conn.commit()
        return {
            "ok": True,
            "status": "computed" if reactions else "waiting_for_ready_absorption_reactions",
            "reaction_rows": len(reactions),
            "orderbook_friction_ready_rows": ready_rows,
            "status_counts": dict(status_counts),
            "reference_notional_krw": float(MIN_ORDER_KRW),
            "cost_contract": {
                "entry_exit_orderbook_window": ORDERBOOK_WINDOW_LABEL,
                "roundtrip_spread_penalty": "half_entry_spread_plus_half_exit_spread",
                "historical_slippage_replay_available": False,
                "versioned_fee_schedule_available": False,
                "full_cost_edge_fail_closed": True,
            },
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }

    def audit(self) -> dict[str, Any]:
        exists = bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_cost_edge_mx'"
        ).fetchone())
        if not exists:
            return {
                "ok": True,"status": "waiting_for_table","table_exists": False,"row_count": 0,
                "paper_only": True,"shadow_only": True,"score_wired": False,"can_place_orders": False,
            }
        row_count = int(self.conn.execute("SELECT COUNT(*) FROM research_market_flow_cost_edge_mx").fetchone()[0])
        ready_rows = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_cost_edge_mx WHERE orderbook_friction_ready=1"
        ).fetchone()[0])
        full_cost_ready_rows = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_cost_edge_mx WHERE full_cost_edge_ready=1"
        ).fetchone()[0])
        incomplete_cost_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_cost_edge_mx
               WHERE fee_model_ready!=0 OR slippage_model_ready!=0 OR full_cost_edge_ready!=0
                  OR full_cost_adjusted_return_pct IS NOT NULL"""
        ).fetchone()[0])
        spread_contract_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_cost_edge_mx
               WHERE orderbook_friction_ready=1 AND (
                   entry_spread_bps IS NULL OR exit_spread_bps IS NULL
                   OR roundtrip_spread_cost_bps IS NULL
                   OR spread_adjusted_hypothesis_return_pct IS NULL
                   OR ABS(roundtrip_spread_cost_bps-((entry_spread_bps+exit_spread_bps)/2.0))>0.000001
                   OR cost_status!='spread_only_fee_and_historical_ladder_missing'
               )"""
        ).fetchone()[0])
        safety_columns = {
            str(row[1]) for row in self.conn.execute("PRAGMA table_info(research_market_flow_cost_edge_mx)").fetchall()
        }
        suspicious_columns = sorted(
            column for column in safety_columns
            if "trade_intent" in column.lower() or "order_qty" in column.lower() or "position_size" in column.lower()
        )
        status_counts = {
            str(row["cost_status"]): int(row["n"])
            for row in self.conn.execute(
                "SELECT cost_status,COUNT(*) AS n FROM research_market_flow_cost_edge_mx GROUP BY cost_status"
            ).fetchall()
        }
        stats = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_cost_edge_stats_mx
               ORDER BY spread_ready_count DESC,sample_count DESC,market,signal_window_label,horizon_label LIMIT 40"""
        ).fetchall()]
        rows = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_cost_edge_mx
               ORDER BY orderbook_friction_ready DESC,signal_feature_ts DESC LIMIT 80"""
        ).fetchall()]
        ok = incomplete_cost_violations == 0 and spread_contract_violations == 0 and not suspicious_columns
        return {
            "ok": ok,
            "status": "ready" if row_count else "waiting_for_ready_absorption_reactions",
            "table_exists": True,
            "row_count": row_count,
            "orderbook_friction_ready_rows": ready_rows,
            "full_cost_ready_rows": full_cost_ready_rows,
            "status_counts": status_counts,
            "incomplete_cost_contract_violations": incomplete_cost_violations,
            "spread_contract_violations": spread_contract_violations,
            "suspicious_wiring_columns": suspicious_columns,
            "stats": stats,
            "rows": rows,
            "interpretation": "spread_adjusted_research_edge_not_complete_transaction_cost_not_trading_score",
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
            "raw_cloud_projection": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
