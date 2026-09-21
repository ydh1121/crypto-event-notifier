from __future__ import annotations

import math
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .market_flow_family_dedup import MarketFlowFamilyDedupStore
from .market_flow_promotion_gate import MarketFlowPromotionGateStore
from .market_flow_regime_confidence import MarketFlowRegimeConfidenceStore
from .market_flow_regime_history import MarketFlowRegimeHistoryStore
from .market_flow_regime_stability import MarketFlowRegimeStabilityStore

SCHEMA_VERSION = 1
FEATURE_VERSION = 1
ABSORPTION_LABELS = (
    "passive_buy_absorption_candidate",
    "passive_sell_absorption_candidate",
)
OBSERVATION_MIN_PER_VENUE = 20
PROMOTION_MIN_PER_VENUE = 50
PROMOTION_MIN_POOLED = 120
PROMOTION_WILSON_LOWER_PCT = 50.0
EXPECTED_EXCHANGES = ("bithumb", "upbit")


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


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


class MarketFlowReliabilityStore:
    """Cross-venue reliability gate for passive absorption reaction hypotheses.

    This layer evaluates forward reaction evidence without changing the signal
    heuristic. It deliberately separates an early directional watch from a
    promotion-ready discovery result. Discovery promotion requires larger
    per-venue and pooled samples plus positive cross-venue direction and a 95%
    Wilson lower bound above chance.

    Whenever that discovery threshold is first reached, the forward-only OOS
    promotion gate freezes a signal timestamp cutoff and accepts only strictly
    later reactions for final validation. A separate shadow regime-confidence
    ledger then summarizes evidence maturity. A conservative family dedup layer
    keeps one representative per market/regime/reaction-horizon and fully
    attenuates nested-timeframe siblings so correlated descriptions cannot be
    double-counted. A bounded 15-minute history captures confidence and family
    snapshots, then a longitudinal stability/degradation layer classifies whether
    those family states are holding or deteriorating. None of these layers is
    wired to score, PAPER decisions, strategy mutation or orders.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_reliability_mx(
                market TEXT NOT NULL,
                signal_window_label TEXT NOT NULL,
                signal_evidence_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                bithumb_sample_count INTEGER NOT NULL DEFAULT 0,
                upbit_sample_count INTEGER NOT NULL DEFAULT 0,
                pooled_sample_count INTEGER NOT NULL DEFAULT 0,
                bithumb_mean_hypothesis_return_pct REAL,
                upbit_mean_hypothesis_return_pct REAL,
                pooled_mean_hypothesis_return_pct REAL,
                bithumb_hit_rate_pct REAL,
                upbit_hit_rate_pct REAL,
                pooled_hit_rate_pct REAL,
                pooled_wilson_lower_pct REAL,
                cross_exchange_direction_consistent INTEGER NOT NULL DEFAULT 0,
                observation_ready INTEGER NOT NULL DEFAULT 0,
                promotion_ready INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'market_flow_reaction',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(market,signal_window_label,signal_evidence_label,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_reliability_status
            ON research_market_flow_reliability_mx(status,promotion_ready,pooled_sample_count DESC);
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
            """SELECT exchange,market,signal_window_label,signal_evidence_label,horizon_label,
                      hypothesis_directional_return_pct
               FROM research_market_flow_reaction_mx
               WHERE data_ready=1
                 AND signal_evidence_label IN (?,?)
                 AND hypothesis_directional_return_pct IS NOT NULL""",
            ABSORPTION_LABELS,
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _venue_stats(values: list[float]) -> dict[str, Any]:
        hits = sum(1 for value in values if value > 0.0)
        count = len(values)
        return {
            "count": count,
            "mean": _mean(values),
            "hit_rate": (hits / count * 100.0) if count else None,
            "hits": hits,
        }

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(now or time.time())
        rows = self._reaction_rows()
        grouped: dict[tuple[str, str, str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for row in rows:
            exchange = str(row.get("exchange") or "").lower()
            if exchange not in EXPECTED_EXCHANGES:
                continue
            value = float(row["hypothesis_directional_return_pct"])
            key = (
                str(row["market"]),
                str(row["signal_window_label"]),
                str(row["signal_evidence_label"]),
                str(row["horizon_label"]),
            )
            grouped[key][exchange].append(value)

        self.conn.execute("DELETE FROM research_market_flow_reliability_mx")
        status_counts: Counter[str] = Counter()
        promotion_ready_rows = 0
        observation_ready_rows = 0
        for key, by_exchange in grouped.items():
            bithumb = self._venue_stats(by_exchange.get("bithumb", []))
            upbit = self._venue_stats(by_exchange.get("upbit", []))
            pooled_values = [*by_exchange.get("bithumb", []), *by_exchange.get("upbit", [])]
            pooled = self._venue_stats(pooled_values)
            wilson_lower = _wilson_lower_pct(int(pooled["hits"]), int(pooled["count"]))

            observation_ready = (
                int(bithumb["count"]) >= OBSERVATION_MIN_PER_VENUE
                and int(upbit["count"]) >= OBSERVATION_MIN_PER_VENUE
            )
            direction_consistent = bool(
                observation_ready
                and bithumb["mean"] is not None and float(bithumb["mean"]) > 0.0
                and upbit["mean"] is not None and float(upbit["mean"]) > 0.0
                and bithumb["hit_rate"] is not None and float(bithumb["hit_rate"]) > 50.0
                and upbit["hit_rate"] is not None and float(upbit["hit_rate"]) > 50.0
            )
            promotion_ready = bool(
                direction_consistent
                and int(bithumb["count"]) >= PROMOTION_MIN_PER_VENUE
                and int(upbit["count"]) >= PROMOTION_MIN_PER_VENUE
                and int(pooled["count"]) >= PROMOTION_MIN_POOLED
                and pooled["mean"] is not None and float(pooled["mean"]) > 0.0
                and pooled["hit_rate"] is not None and float(pooled["hit_rate"]) > 50.0
                and wilson_lower is not None and float(wilson_lower) > PROMOTION_WILSON_LOWER_PCT
            )
            if promotion_ready:
                status = "validated_candidate"
            elif direction_consistent:
                status = "directional_watch"
            elif observation_ready:
                status = "mixed_cross_exchange"
            else:
                status = "collecting"

            self.conn.execute(
                """INSERT INTO research_market_flow_reliability_mx(
                       market,signal_window_label,signal_evidence_label,horizon_label,
                       bithumb_sample_count,upbit_sample_count,pooled_sample_count,
                       bithumb_mean_hypothesis_return_pct,upbit_mean_hypothesis_return_pct,
                       pooled_mean_hypothesis_return_pct,bithumb_hit_rate_pct,upbit_hit_rate_pct,
                       pooled_hit_rate_pct,pooled_wilson_lower_pct,cross_exchange_direction_consistent,
                       observation_ready,promotion_ready,status,source,received_at,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    *key,
                    int(bithumb["count"]),int(upbit["count"]),int(pooled["count"]),
                    bithumb["mean"],upbit["mean"],pooled["mean"],
                    bithumb["hit_rate"],upbit["hit_rate"],pooled["hit_rate"],wilson_lower,
                    1 if direction_consistent else 0,
                    1 if observation_ready else 0,
                    1 if promotion_ready else 0,
                    status,"market_flow_reaction",stamp,FEATURE_VERSION,SCHEMA_VERSION,
                ),
            )
            status_counts[status] += 1
            observation_ready_rows += 1 if observation_ready else 0
            promotion_ready_rows += 1 if promotion_ready else 0

        self.conn.commit()

        promotion_gate = MarketFlowPromotionGateStore(self.path)
        try:
            promotion_gate_result = promotion_gate.compute(now=stamp)
        finally:
            promotion_gate.close()

        regime_confidence = MarketFlowRegimeConfidenceStore(self.path)
        try:
            regime_confidence_result = regime_confidence.compute(now=stamp)
        finally:
            regime_confidence.close()

        family_dedup = MarketFlowFamilyDedupStore(self.path)
        try:
            family_dedup_result = family_dedup.compute(now=stamp)
        finally:
            family_dedup.close()

        regime_history = MarketFlowRegimeHistoryStore(self.path)
        try:
            regime_history_result = regime_history.capture(now=stamp)
        finally:
            regime_history.close()

        regime_stability = MarketFlowRegimeStabilityStore(self.path)
        try:
            regime_stability_result = regime_stability.compute(now=stamp)
        finally:
            regime_stability.close()

        return {
            "ok": (
                bool(promotion_gate_result.get("ok", True))
                and bool(regime_confidence_result.get("ok", True))
                and bool(family_dedup_result.get("ok", True))
                and bool(regime_history_result.get("ok", True))
                and bool(regime_stability_result.get("ok", True))
            ),
            "status": "computed" if grouped else "waiting_for_absorption_reactions",
            "groups_written": len(grouped),
            "observation_ready_rows": observation_ready_rows,
            "promotion_ready_rows": promotion_ready_rows,
            "status_counts": dict(status_counts),
            "thresholds": {
                "observation_min_per_venue": OBSERVATION_MIN_PER_VENUE,
                "promotion_min_per_venue": PROMOTION_MIN_PER_VENUE,
                "promotion_min_pooled": PROMOTION_MIN_POOLED,
                "promotion_wilson_lower_pct": PROMOTION_WILSON_LOWER_PCT,
            },
            "promotion_gate": promotion_gate_result,
            "regime_confidence": regime_confidence_result,
            "family_dedup": family_dedup_result,
            "regime_history": regime_history_result,
            "regime_stability": regime_stability_result,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
        }

    def audit(self) -> dict[str, Any]:
        exists = bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_reliability_mx'"
        ).fetchone())
        if not exists:
            return {
                "ok": True,"status": "waiting_for_table","table_exists": False,"row_count": 0,
                "paper_only": True,"score_wired": False,"can_place_orders": False,
            }
        row_count = int(self.conn.execute("SELECT COUNT(*) FROM research_market_flow_reliability_mx").fetchone()[0])
        promotion_ready_rows = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_reliability_mx WHERE promotion_ready=1"
        ).fetchone()[0])
        observation_ready_rows = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_reliability_mx WHERE observation_ready=1"
        ).fetchone()[0])
        promotion_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_reliability_mx
               WHERE promotion_ready=1 AND (
                   bithumb_sample_count<? OR upbit_sample_count<? OR pooled_sample_count<?
                   OR COALESCE(bithumb_mean_hypothesis_return_pct,0)<=0
                   OR COALESCE(upbit_mean_hypothesis_return_pct,0)<=0
                   OR COALESCE(bithumb_hit_rate_pct,0)<=50
                   OR COALESCE(upbit_hit_rate_pct,0)<=50
                   OR COALESCE(pooled_mean_hypothesis_return_pct,0)<=0
                   OR COALESCE(pooled_hit_rate_pct,0)<=50
                   OR COALESCE(pooled_wilson_lower_pct,0)<=?
                   OR cross_exchange_direction_consistent!=1
               )""",
            (PROMOTION_MIN_PER_VENUE,PROMOTION_MIN_PER_VENUE,PROMOTION_MIN_POOLED,PROMOTION_WILSON_LOWER_PCT),
        ).fetchone()[0])
        status_counts = {
            str(row["status"]): int(row["n"])
            for row in self.conn.execute(
                "SELECT status,COUNT(*) AS n FROM research_market_flow_reliability_mx GROUP BY status"
            ).fetchall()
        }
        rows = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_reliability_mx
               ORDER BY promotion_ready DESC,observation_ready DESC,pooled_sample_count DESC,
                        market,signal_window_label,horizon_label LIMIT 40"""
        ).fetchall()]
        columns = {
            str(row[1]) for row in self.conn.execute("PRAGMA table_info(research_market_flow_reliability_mx)").fetchall()
        }
        suspicious_score_columns = sorted(
            column for column in columns if "score" in column.lower() or "order" in column.lower() or "trade_intent" in column.lower()
        )
        return {
            "ok": promotion_violations == 0 and not suspicious_score_columns,
            "status": "ready" if row_count else "waiting_for_absorption_reactions",
            "table_exists": True,
            "row_count": row_count,
            "observation_ready_rows": observation_ready_rows,
            "promotion_ready_rows": promotion_ready_rows,
            "status_counts": status_counts,
            "promotion_contract_violations": promotion_violations,
            "score_wiring_columns": suspicious_score_columns,
            "rows": rows,
            "thresholds": {
                "observation_min_per_venue": OBSERVATION_MIN_PER_VENUE,
                "promotion_min_per_venue": PROMOTION_MIN_PER_VENUE,
                "promotion_min_pooled": PROMOTION_MIN_POOLED,
                "promotion_wilson_lower_pct": PROMOTION_WILSON_LOWER_PCT,
            },
            "source": "market_flow_reaction",
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "raw_cloud_projection": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
