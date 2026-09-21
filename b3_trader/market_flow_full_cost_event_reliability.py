from __future__ import annotations

import math
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 1
FEATURE_VERSION = 1
EXPECTED_EXCHANGES = ("bithumb", "upbit")
OBSERVATION_MIN_EVENTS = 30
OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS = 20
PROMOTION_MIN_EVENTS = 60
PROMOTION_MIN_CROSS_EXCHANGE_EVENTS = 40
PROMOTION_EVENT_WILSON_LOWER_PCT = 50.0
PROMOTION_CROSS_POSITIVE_WILSON_LOWER_PCT = 50.0
INTERPRETATION = (
    "forward_full_transaction_cost_overlap_clustered_event_reliability_"
    "not_probability_not_trading_score"
)


def _wilson_lower_pct(successes: int, sample_count: int, z: float = 1.96) -> float | None:
    n = int(sample_count)
    if n <= 0:
        return None
    hits = max(0, min(n, int(successes)))
    p = hits / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = p + z2 / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)
    return max(0.0, (center - margin) / denominator) * 100.0


class MarketFlowFullCostEventReliabilityStore:
    """Reliability view over forward full-transaction-cost event clusters.

    Promotion thresholds are preregistered to match the spread-only event layer
    for direct comparability. A group cannot become observation-ready without
    cross-exchange full-cost events. If one exchange lacks a verified fee profile,
    the gate therefore remains fail-closed instead of fabricating costs.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_full_cost_event_reliability_mx(
                market TEXT NOT NULL,
                regime_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                event_count INTEGER NOT NULL DEFAULT 0,
                positive_event_count INTEGER NOT NULL DEFAULT 0,
                mean_event_full_cost_adjusted_return_pct REAL,
                event_hit_rate_pct REAL,
                event_wilson_lower_pct REAL,
                cross_exchange_event_count INTEGER NOT NULL DEFAULT 0,
                cross_exchange_positive_agreement_count INTEGER NOT NULL DEFAULT 0,
                cross_exchange_sign_agreement_count INTEGER NOT NULL DEFAULT 0,
                mean_cross_exchange_event_return_pct REAL,
                cross_exchange_positive_agreement_rate_pct REAL,
                cross_exchange_positive_wilson_lower_pct REAL,
                cross_exchange_sign_agreement_rate_pct REAL,
                observation_ready INTEGER NOT NULL DEFAULT 0,
                direction_consistent INTEGER NOT NULL DEFAULT 0,
                promotion_ready INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'market_flow_full_cost_event_cluster',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(market,regime_label,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_full_cost_event_reliability_status
            ON research_market_flow_full_cost_event_reliability_mx(
                promotion_ready DESC,observation_ready DESC,event_count DESC
            );
            """
        )
        self.conn.commit()

    def _event_rows(self) -> list[dict[str, Any]]:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_full_cost_event_cluster_mx'"
        ).fetchone()
        if not exists:
            return []
        rows = self.conn.execute(
            """SELECT event_id,market,regime_label,horizon_label,
                      mean_full_cost_adjusted_return_pct,cross_exchange_confirmed
               FROM research_market_flow_full_cost_event_cluster_mx
               WHERE mean_full_cost_adjusted_return_pct IS NOT NULL
               ORDER BY market,regime_label,horizon_label,event_anchor_signal_ts"""
        ).fetchall()
        return [dict(row) for row in rows]

    def _representative_returns(self) -> dict[str, dict[str, float]]:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_full_cost_event_cluster_member_mx'"
        ).fetchone()
        if not exists:
            return {}
        result: dict[str, dict[str, float]] = defaultdict(dict)
        rows = self.conn.execute(
            """SELECT event_id,exchange,full_cost_adjusted_return_pct
               FROM research_market_flow_full_cost_event_cluster_member_mx
               WHERE representative_for_exchange=1
                 AND exchange IN (?,?)
                 AND full_cost_adjusted_return_pct IS NOT NULL""",
            EXPECTED_EXCHANGES,
        ).fetchall()
        for row in rows:
            result[str(row["event_id"])][str(row["exchange"])] = float(row["full_cost_adjusted_return_pct"])
        return dict(result)

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(now or time.time())
        events = self._event_rows()
        representatives = self._representative_returns()
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            grouped[(str(event["market"]), str(event["regime_label"]), str(event["horizon_label"]))].append(event)

        self.conn.execute("DELETE FROM research_market_flow_full_cost_event_reliability_mx")
        status_counts: Counter[str] = Counter()
        observation_ready_rows = 0
        promotion_ready_rows = 0

        for key, rows in grouped.items():
            event_returns = [float(row["mean_full_cost_adjusted_return_pct"]) for row in rows]
            event_count = len(event_returns)
            positive_events = sum(1 for value in event_returns if value > 0.0)
            mean_event_return = statistics.fmean(event_returns) if event_returns else None
            event_hit_rate = positive_events / event_count * 100.0 if event_count else None
            event_wilson = _wilson_lower_pct(positive_events, event_count)

            cross_returns: list[float] = []
            cross_positive = 0
            cross_sign_agreement = 0
            cross_count = 0
            for row in rows:
                by_exchange = representatives.get(str(row["event_id"]), {})
                if not all(exchange in by_exchange for exchange in EXPECTED_EXCHANGES):
                    continue
                bithumb = float(by_exchange["bithumb"])
                upbit = float(by_exchange["upbit"])
                cross_count += 1
                cross_returns.append((bithumb + upbit) / 2.0)
                if bithumb > 0.0 and upbit > 0.0:
                    cross_positive += 1
                if (bithumb > 0.0 and upbit > 0.0) or (bithumb <= 0.0 and upbit <= 0.0):
                    cross_sign_agreement += 1

            mean_cross_return = statistics.fmean(cross_returns) if cross_returns else None
            cross_positive_rate = cross_positive / cross_count * 100.0 if cross_count else None
            cross_positive_wilson = _wilson_lower_pct(cross_positive, cross_count)
            cross_sign_rate = cross_sign_agreement / cross_count * 100.0 if cross_count else None

            observation_ready = bool(
                event_count >= OBSERVATION_MIN_EVENTS
                and cross_count >= OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS
            )
            direction_consistent = bool(
                observation_ready
                and mean_event_return is not None and mean_event_return > 0.0
                and event_hit_rate is not None and event_hit_rate > 50.0
                and mean_cross_return is not None and mean_cross_return > 0.0
                and cross_positive_rate is not None and cross_positive_rate > 50.0
            )
            promotion_ready = bool(
                direction_consistent
                and event_count >= PROMOTION_MIN_EVENTS
                and cross_count >= PROMOTION_MIN_CROSS_EXCHANGE_EVENTS
                and event_wilson is not None and event_wilson > PROMOTION_EVENT_WILSON_LOWER_PCT
                and cross_positive_wilson is not None
                and cross_positive_wilson > PROMOTION_CROSS_POSITIVE_WILSON_LOWER_PCT
            )

            if promotion_ready:
                status = "validated_full_cost_candidate"
            elif direction_consistent:
                status = "full_cost_directional_watch"
            elif observation_ready:
                status = "mixed_full_cost_edge"
            else:
                status = "collecting_full_cost"

            self.conn.execute(
                """INSERT INTO research_market_flow_full_cost_event_reliability_mx(
                       market,regime_label,horizon_label,event_count,positive_event_count,
                       mean_event_full_cost_adjusted_return_pct,event_hit_rate_pct,event_wilson_lower_pct,
                       cross_exchange_event_count,cross_exchange_positive_agreement_count,
                       cross_exchange_sign_agreement_count,mean_cross_exchange_event_return_pct,
                       cross_exchange_positive_agreement_rate_pct,cross_exchange_positive_wilson_lower_pct,
                       cross_exchange_sign_agreement_rate_pct,observation_ready,direction_consistent,
                       promotion_ready,status,source,received_at,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                            'market_flow_full_cost_event_cluster',?,?,?)""",
                (
                    *key,event_count,positive_events,mean_event_return,event_hit_rate,event_wilson,
                    cross_count,cross_positive,cross_sign_agreement,mean_cross_return,
                    cross_positive_rate,cross_positive_wilson,cross_sign_rate,
                    1 if observation_ready else 0,1 if direction_consistent else 0,
                    1 if promotion_ready else 0,status,stamp,FEATURE_VERSION,SCHEMA_VERSION,
                ),
            )
            status_counts[status] += 1
            observation_ready_rows += 1 if observation_ready else 0
            promotion_ready_rows += 1 if promotion_ready else 0

        self.conn.commit()
        return {
            "ok": True,
            "status": "computed" if grouped else "waiting_for_forward_full_cost_events",
            "groups_written": len(grouped),
            "source_event_count": len(events),
            "observation_ready_rows": observation_ready_rows,
            "promotion_ready_rows": promotion_ready_rows,
            "status_counts": dict(status_counts),
            "thresholds": {
                "observation_min_events": OBSERVATION_MIN_EVENTS,
                "observation_min_cross_exchange_events": OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS,
                "promotion_min_events": PROMOTION_MIN_EVENTS,
                "promotion_min_cross_exchange_events": PROMOTION_MIN_CROSS_EXCHANGE_EVENTS,
                "promotion_event_wilson_lower_pct": PROMOTION_EVENT_WILSON_LOWER_PCT,
                "promotion_cross_positive_wilson_lower_pct": PROMOTION_CROSS_POSITIVE_WILSON_LOWER_PCT,
            },
            "bithumb_unverified_fee_profile_keeps_cross_exchange_fail_closed": True,
            "historical_full_cost_backfill": False,
            "paper_only": True,
            "shadow_only": True,
            "probability_interpretation": False,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }

    def audit(self) -> dict[str, Any]:
        exists = bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_full_cost_event_reliability_mx'"
        ).fetchone())
        if not exists:
            return {"ok": True,"status": "waiting_for_table","table_exists": False,"row_count": 0,"paper_only": True,"shadow_only": True,"score_wired": False,"can_place_orders": False}

        row_count = int(self.conn.execute("SELECT COUNT(*) FROM research_market_flow_full_cost_event_reliability_mx").fetchone()[0])
        observation_ready_rows = int(self.conn.execute("SELECT COUNT(*) FROM research_market_flow_full_cost_event_reliability_mx WHERE observation_ready=1").fetchone()[0])
        promotion_ready_rows = int(self.conn.execute("SELECT COUNT(*) FROM research_market_flow_full_cost_event_reliability_mx WHERE promotion_ready=1").fetchone()[0])
        promotion_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_full_cost_event_reliability_mx
               WHERE promotion_ready=1 AND (
                   event_count<? OR cross_exchange_event_count<?
                   OR COALESCE(mean_event_full_cost_adjusted_return_pct,0)<=0
                   OR COALESCE(event_hit_rate_pct,0)<=50 OR COALESCE(event_wilson_lower_pct,0)<=?
                   OR COALESCE(mean_cross_exchange_event_return_pct,0)<=0
                   OR COALESCE(cross_exchange_positive_agreement_rate_pct,0)<=50
                   OR COALESCE(cross_exchange_positive_wilson_lower_pct,0)<=?
                   OR observation_ready!=1 OR direction_consistent!=1
               )""",
            (PROMOTION_MIN_EVENTS,PROMOTION_MIN_CROSS_EXCHANGE_EVENTS,PROMOTION_EVENT_WILSON_LOWER_PCT,PROMOTION_CROSS_POSITIVE_WILSON_LOWER_PCT),
        ).fetchone()[0])
        observation_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_full_cost_event_reliability_mx
               WHERE observation_ready=1 AND (event_count<? OR cross_exchange_event_count<?)""",
            (OBSERVATION_MIN_EVENTS,OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS),
        ).fetchone()[0])
        direction_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_full_cost_event_reliability_mx
               WHERE direction_consistent=1 AND (
                   observation_ready!=1 OR COALESCE(mean_event_full_cost_adjusted_return_pct,0)<=0
                   OR COALESCE(event_hit_rate_pct,0)<=50 OR COALESCE(mean_cross_exchange_event_return_pct,0)<=0
                   OR COALESCE(cross_exchange_positive_agreement_rate_pct,0)<=50
               )"""
        ).fetchone()[0])
        source_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_full_cost_event_reliability_mx r
               WHERE NOT EXISTS(SELECT 1 FROM research_market_flow_full_cost_event_cluster_mx e
                   WHERE e.market=r.market AND e.regime_label=r.regime_label AND e.horizon_label=r.horizon_label)"""
        ).fetchone()[0])
        rows = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_full_cost_event_reliability_mx
               ORDER BY promotion_ready DESC,direction_consistent DESC,observation_ready DESC,event_count DESC,market,regime_label,horizon_label"""
        ).fetchall()]
        status_counts = {str(row["status"]): int(row["n"]) for row in self.conn.execute("SELECT status,COUNT(*) AS n FROM research_market_flow_full_cost_event_reliability_mx GROUP BY status").fetchall()}
        columns = {str(row[1]) for row in self.conn.execute("PRAGMA table_info(research_market_flow_full_cost_event_reliability_mx)").fetchall()}
        suspicious = sorted(column for column in columns if "trade_intent" in column.lower() or "order_qty" in column.lower() or "position_size" in column.lower() or "strategy_action" in column.lower())
        ok = promotion_violations == 0 and observation_violations == 0 and direction_violations == 0 and source_violations == 0 and not suspicious
        return {
            "ok": ok,
            "status": "ready" if row_count else "waiting_for_forward_full_cost_events",
            "table_exists": True,
            "row_count": row_count,
            "observation_ready_rows": observation_ready_rows,
            "promotion_ready_rows": promotion_ready_rows,
            "status_counts": status_counts,
            "promotion_contract_violations": promotion_violations,
            "observation_contract_violations": observation_violations,
            "direction_contract_violations": direction_violations,
            "full_cost_source_contract_violations": source_violations,
            "suspicious_wiring_columns": suspicious,
            "rows": rows,
            "thresholds": {
                "observation_min_events": OBSERVATION_MIN_EVENTS,
                "observation_min_cross_exchange_events": OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS,
                "promotion_min_events": PROMOTION_MIN_EVENTS,
                "promotion_min_cross_exchange_events": PROMOTION_MIN_CROSS_EXCHANGE_EVENTS,
                "promotion_event_wilson_lower_pct": PROMOTION_EVENT_WILSON_LOWER_PCT,
                "promotion_cross_positive_wilson_lower_pct": PROMOTION_CROSS_POSITIVE_WILSON_LOWER_PCT,
            },
            "interpretation": INTERPRETATION,
            "historical_full_cost_backfill": False,
            "raw_cloud_projection": False,
            "paper_only": True,
            "shadow_only": True,
            "probability_interpretation": False,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
