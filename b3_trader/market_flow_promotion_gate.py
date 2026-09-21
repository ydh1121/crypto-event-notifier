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
OOS_MIN_PER_VENUE = 20
OOS_MIN_POOLED = 50
OOS_WILSON_LOWER_PCT = 50.0
MAX_TRANSITIONS = 5000


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


class MarketFlowPromotionGateStore:
    """Forward-only OOS gate after the discovery reliability gate fires.

    The discovery/reliability layer may inspect all reaction evidence accumulated
    so far. The first time a reaction group reaches its preregistered promotion
    threshold, this store freezes the maximum signal_feature_ts observed at that
    moment. Only strictly later reactions can enter the OOS cohort. This avoids
    manufacturing a retrospective holdout after looking at the same data.

    OOS state changes are journaled locally. Even an OOS-validated row remains a
    shadow research candidate: no score, PAPER decision, strategy mutation or
    order path reads these tables.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_promotion_gate_mx(
                market TEXT NOT NULL,
                signal_window_label TEXT NOT NULL,
                signal_evidence_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                gate_started_at REAL NOT NULL,
                cutoff_signal_ts REAL NOT NULL,
                base_bithumb_sample_count INTEGER NOT NULL DEFAULT 0,
                base_upbit_sample_count INTEGER NOT NULL DEFAULT 0,
                base_pooled_sample_count INTEGER NOT NULL DEFAULT 0,
                oos_bithumb_sample_count INTEGER NOT NULL DEFAULT 0,
                oos_upbit_sample_count INTEGER NOT NULL DEFAULT 0,
                oos_pooled_sample_count INTEGER NOT NULL DEFAULT 0,
                oos_bithumb_mean_hypothesis_return_pct REAL,
                oos_upbit_mean_hypothesis_return_pct REAL,
                oos_pooled_mean_hypothesis_return_pct REAL,
                oos_bithumb_hit_rate_pct REAL,
                oos_upbit_hit_rate_pct REAL,
                oos_pooled_hit_rate_pct REAL,
                oos_pooled_wilson_lower_pct REAL,
                oos_direction_consistent INTEGER NOT NULL DEFAULT 0,
                oos_sample_ready INTEGER NOT NULL DEFAULT 0,
                final_candidate_ready INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'collecting_oos',
                source TEXT NOT NULL DEFAULT 'market_flow_reliability+market_flow_reaction',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(market,signal_window_label,signal_evidence_label,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_promotion_gate_status
            ON research_market_flow_promotion_gate_mx(final_candidate_ready,oos_sample_ready,status,oos_pooled_sample_count DESC);

            CREATE TABLE IF NOT EXISTS research_market_flow_promotion_transition_mx(
                transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                market TEXT NOT NULL,
                signal_window_label TEXT NOT NULL,
                signal_evidence_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                previous_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                previous_final_candidate_ready INTEGER NOT NULL DEFAULT 0,
                new_final_candidate_ready INTEGER NOT NULL DEFAULT 0,
                cutoff_signal_ts REAL NOT NULL,
                changed_at REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'market_flow_promotion_gate',
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_promotion_transition_recent
            ON research_market_flow_promotion_transition_mx(changed_at DESC,transition_id DESC);
            """
        )
        self.conn.commit()

    def _tables_ready(self) -> bool:
        names = {
            str(row[0])
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        return {
            "research_market_flow_reliability_mx",
            "research_market_flow_reaction_mx",
        }.issubset(names)

    @staticmethod
    def _venue_stats(values: list[float]) -> dict[str, Any]:
        count = len(values)
        hits = sum(1 for value in values if value > 0.0)
        return {
            "count": count,
            "mean": _mean(values),
            "hit_rate": (hits / count * 100.0) if count else None,
            "hits": hits,
        }

    def _freeze_new_gates(self, stamp: float) -> int:
        rows = self.conn.execute(
            """SELECT market,signal_window_label,signal_evidence_label,horizon_label,
                      bithumb_sample_count,upbit_sample_count,pooled_sample_count
               FROM research_market_flow_reliability_mx
               WHERE promotion_ready=1"""
        ).fetchall()
        started = 0
        for row in rows:
            key = (
                str(row["market"]),
                str(row["signal_window_label"]),
                str(row["signal_evidence_label"]),
                str(row["horizon_label"]),
            )
            exists = self.conn.execute(
                """SELECT 1 FROM research_market_flow_promotion_gate_mx
                   WHERE market=? AND signal_window_label=? AND signal_evidence_label=? AND horizon_label=?""",
                key,
            ).fetchone()
            if exists:
                continue
            cutoff_row = self.conn.execute(
                """SELECT MAX(signal_feature_ts) AS cutoff
                   FROM research_market_flow_reaction_mx
                   WHERE market=? AND signal_window_label=? AND signal_evidence_label=? AND horizon_label=?
                     AND data_ready=1 AND hypothesis_directional_return_pct IS NOT NULL""",
                key,
            ).fetchone()
            cutoff = float(cutoff_row["cutoff"] or 0.0) if cutoff_row else 0.0
            if cutoff <= 0:
                continue
            self.conn.execute(
                """INSERT INTO research_market_flow_promotion_gate_mx(
                       market,signal_window_label,signal_evidence_label,horizon_label,
                       gate_started_at,cutoff_signal_ts,
                       base_bithumb_sample_count,base_upbit_sample_count,base_pooled_sample_count,
                       status,received_at,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,'collecting_oos',?,?,?)""",
                (
                    *key,
                    stamp,
                    cutoff,
                    int(row["bithumb_sample_count"] or 0),
                    int(row["upbit_sample_count"] or 0),
                    int(row["pooled_sample_count"] or 0),
                    stamp,
                    FEATURE_VERSION,
                    SCHEMA_VERSION,
                ),
            )
            self._journal(
                key,
                previous_status="not_started",
                new_status="collecting_oos",
                previous_final=0,
                new_final=0,
                cutoff=cutoff,
                stamp=stamp,
            )
            started += 1
        return started

    def _oos_values(self, gate: sqlite3.Row) -> dict[str, list[float]]:
        rows = self.conn.execute(
            """SELECT exchange,hypothesis_directional_return_pct
               FROM research_market_flow_reaction_mx
               WHERE market=? AND signal_window_label=? AND signal_evidence_label=? AND horizon_label=?
                 AND data_ready=1 AND hypothesis_directional_return_pct IS NOT NULL
                 AND signal_feature_ts>?
               ORDER BY signal_feature_ts ASC""",
            (
                str(gate["market"]),
                str(gate["signal_window_label"]),
                str(gate["signal_evidence_label"]),
                str(gate["horizon_label"]),
                float(gate["cutoff_signal_ts"]),
            ),
        ).fetchall()
        values: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            exchange = str(row["exchange"] or "").lower()
            if exchange in EXPECTED_EXCHANGES:
                values[exchange].append(float(row["hypothesis_directional_return_pct"]))
        return values

    def _journal(
        self,
        key: tuple[str, str, str, str],
        *,
        previous_status: str,
        new_status: str,
        previous_final: int,
        new_final: int,
        cutoff: float,
        stamp: float,
    ) -> None:
        self.conn.execute(
            """INSERT INTO research_market_flow_promotion_transition_mx(
                   market,signal_window_label,signal_evidence_label,horizon_label,
                   previous_status,new_status,previous_final_candidate_ready,new_final_candidate_ready,
                   cutoff_signal_ts,changed_at,source,feature_version,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,'market_flow_promotion_gate',?,?)""",
            (
                *key,
                str(previous_status),str(new_status),int(previous_final),int(new_final),
                float(cutoff),float(stamp),FEATURE_VERSION,SCHEMA_VERSION,
            ),
        )

    def _prune_transitions(self) -> int:
        before = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_promotion_transition_mx"
        ).fetchone()[0])
        if before <= MAX_TRANSITIONS:
            return 0
        self.conn.execute(
            """DELETE FROM research_market_flow_promotion_transition_mx
               WHERE transition_id NOT IN (
                   SELECT transition_id FROM research_market_flow_promotion_transition_mx
                   ORDER BY transition_id DESC LIMIT ?
               )""",
            (MAX_TRANSITIONS,),
        )
        return max(0, before - MAX_TRANSITIONS)

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(now or time.time())
        if not self._tables_ready():
            return {
                "ok": True,
                "status": "waiting_for_reliability_tables",
                "gates_started": 0,
                "active_gates": 0,
                "oos_sample_ready_rows": 0,
                "final_candidate_ready_rows": 0,
                "transition_rows_written": 0,
                "paper_only": True,
                "shadow_only": True,
                "score_wired": False,
                "can_place_orders": False,
            }

        gates_started = self._freeze_new_gates(stamp)
        gates = self.conn.execute(
            "SELECT * FROM research_market_flow_promotion_gate_mx"
        ).fetchall()
        status_counts: Counter[str] = Counter()
        transition_rows_written = gates_started
        oos_sample_ready_rows = 0
        final_candidate_ready_rows = 0

        for gate in gates:
            values = self._oos_values(gate)
            bithumb = self._venue_stats(values.get("bithumb", []))
            upbit = self._venue_stats(values.get("upbit", []))
            pooled_values = [*values.get("bithumb", []), *values.get("upbit", [])]
            pooled = self._venue_stats(pooled_values)
            wilson_lower = _wilson_lower_pct(int(pooled["hits"]), int(pooled["count"]))

            sample_ready = bool(
                int(bithumb["count"]) >= OOS_MIN_PER_VENUE
                and int(upbit["count"]) >= OOS_MIN_PER_VENUE
                and int(pooled["count"]) >= OOS_MIN_POOLED
            )
            direction_consistent = bool(
                sample_ready
                and bithumb["mean"] is not None and float(bithumb["mean"]) > 0.0
                and upbit["mean"] is not None and float(upbit["mean"]) > 0.0
                and bithumb["hit_rate"] is not None and float(bithumb["hit_rate"]) > 50.0
                and upbit["hit_rate"] is not None and float(upbit["hit_rate"]) > 50.0
            )
            final_ready = bool(
                direction_consistent
                and pooled["mean"] is not None and float(pooled["mean"]) > 0.0
                and pooled["hit_rate"] is not None and float(pooled["hit_rate"]) > 50.0
                and wilson_lower is not None and float(wilson_lower) > OOS_WILSON_LOWER_PCT
            )
            status = "oos_validated" if final_ready else "oos_mixed" if sample_ready else "collecting_oos"
            key = (
                str(gate["market"]),str(gate["signal_window_label"]),
                str(gate["signal_evidence_label"]),str(gate["horizon_label"]),
            )
            previous_status = str(gate["status"])
            previous_final = int(gate["final_candidate_ready"] or 0)
            new_final = 1 if final_ready else 0

            self.conn.execute(
                """UPDATE research_market_flow_promotion_gate_mx SET
                       oos_bithumb_sample_count=?,oos_upbit_sample_count=?,oos_pooled_sample_count=?,
                       oos_bithumb_mean_hypothesis_return_pct=?,oos_upbit_mean_hypothesis_return_pct=?,
                       oos_pooled_mean_hypothesis_return_pct=?,oos_bithumb_hit_rate_pct=?,
                       oos_upbit_hit_rate_pct=?,oos_pooled_hit_rate_pct=?,oos_pooled_wilson_lower_pct=?,
                       oos_direction_consistent=?,oos_sample_ready=?,final_candidate_ready=?,status=?,
                       received_at=?,feature_version=?,schema_version=?
                   WHERE market=? AND signal_window_label=? AND signal_evidence_label=? AND horizon_label=?""",
                (
                    int(bithumb["count"]),int(upbit["count"]),int(pooled["count"]),
                    bithumb["mean"],upbit["mean"],pooled["mean"],
                    bithumb["hit_rate"],upbit["hit_rate"],pooled["hit_rate"],wilson_lower,
                    1 if direction_consistent else 0,1 if sample_ready else 0,new_final,status,
                    stamp,FEATURE_VERSION,SCHEMA_VERSION,*key,
                ),
            )
            if previous_status != status or previous_final != new_final:
                self._journal(
                    key,
                    previous_status=previous_status,
                    new_status=status,
                    previous_final=previous_final,
                    new_final=new_final,
                    cutoff=float(gate["cutoff_signal_ts"]),
                    stamp=stamp,
                )
                transition_rows_written += 1

            status_counts[status] += 1
            oos_sample_ready_rows += 1 if sample_ready else 0
            final_candidate_ready_rows += 1 if final_ready else 0

        transitions_pruned = self._prune_transitions()
        self.conn.commit()
        return {
            "ok": True,
            "status": "computed" if gates else "waiting_for_base_promotion",
            "gates_started": gates_started,
            "active_gates": len(gates),
            "oos_sample_ready_rows": oos_sample_ready_rows,
            "final_candidate_ready_rows": final_candidate_ready_rows,
            "status_counts": dict(status_counts),
            "transition_rows_written": transition_rows_written,
            "transitions_pruned": transitions_pruned,
            "cutoff_contract": "signal_feature_ts_strictly_greater_than_frozen_cutoff",
            "thresholds": {
                "oos_min_per_venue": OOS_MIN_PER_VENUE,
                "oos_min_pooled": OOS_MIN_POOLED,
                "oos_wilson_lower_pct": OOS_WILSON_LOWER_PCT,
            },
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
        }

    def audit(self) -> dict[str, Any]:
        gate_exists = bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_promotion_gate_mx'"
        ).fetchone())
        transition_exists = bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_promotion_transition_mx'"
        ).fetchone())
        if not gate_exists or not transition_exists:
            return {
                "ok": True,
                "status": "waiting_for_table",
                "gate_table_exists": gate_exists,
                "transition_table_exists": transition_exists,
                "row_count": 0,
                "paper_only": True,
                "score_wired": False,
                "can_place_orders": False,
            }

        rows = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_promotion_gate_mx
               ORDER BY final_candidate_ready DESC,oos_sample_ready DESC,oos_pooled_sample_count DESC,
                        market,signal_window_label,horizon_label LIMIT 40"""
        ).fetchall()]
        row_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_promotion_gate_mx"
        ).fetchone()[0])
        transition_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_promotion_transition_mx"
        ).fetchone()[0])
        oos_ready = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_promotion_gate_mx WHERE oos_sample_ready=1"
        ).fetchone()[0])
        final_ready = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_promotion_gate_mx WHERE final_candidate_ready=1"
        ).fetchone()[0])
        contract_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_promotion_gate_mx
               WHERE final_candidate_ready=1 AND (
                   oos_bithumb_sample_count<? OR oos_upbit_sample_count<? OR oos_pooled_sample_count<?
                   OR COALESCE(oos_bithumb_mean_hypothesis_return_pct,0)<=0
                   OR COALESCE(oos_upbit_mean_hypothesis_return_pct,0)<=0
                   OR COALESCE(oos_bithumb_hit_rate_pct,0)<=50
                   OR COALESCE(oos_upbit_hit_rate_pct,0)<=50
                   OR COALESCE(oos_pooled_mean_hypothesis_return_pct,0)<=0
                   OR COALESCE(oos_pooled_hit_rate_pct,0)<=50
                   OR COALESCE(oos_pooled_wilson_lower_pct,0)<=?
                   OR oos_direction_consistent!=1 OR oos_sample_ready!=1
               )""",
            (OOS_MIN_PER_VENUE,OOS_MIN_PER_VENUE,OOS_MIN_POOLED,OOS_WILSON_LOWER_PCT),
        ).fetchone()[0])

        cutoff_count_mismatches = 0
        for row in rows:
            counts = {
                str(item["exchange"]): int(item["n"])
                for item in self.conn.execute(
                    """SELECT exchange,COUNT(*) AS n FROM research_market_flow_reaction_mx
                       WHERE market=? AND signal_window_label=? AND signal_evidence_label=? AND horizon_label=?
                         AND data_ready=1 AND hypothesis_directional_return_pct IS NOT NULL
                         AND signal_feature_ts>?
                       GROUP BY exchange""",
                    (
                        row["market"],row["signal_window_label"],row["signal_evidence_label"],row["horizon_label"],
                        float(row["cutoff_signal_ts"]),
                    ),
                ).fetchall()
            }
            if (
                int(row["oos_bithumb_sample_count"] or 0) != int(counts.get("bithumb", 0))
                or int(row["oos_upbit_sample_count"] or 0) != int(counts.get("upbit", 0))
            ):
                cutoff_count_mismatches += 1

        status_counts = {
            str(row["status"]): int(row["n"])
            for row in self.conn.execute(
                "SELECT status,COUNT(*) AS n FROM research_market_flow_promotion_gate_mx GROUP BY status"
            ).fetchall()
        }
        transition_rows = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_promotion_transition_mx
               ORDER BY transition_id DESC LIMIT 40"""
        ).fetchall()]
        columns = {
            str(row[1])
            for table in ("research_market_flow_promotion_gate_mx","research_market_flow_promotion_transition_mx")
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        suspicious_score_columns = sorted(
            column for column in columns
            if "score" in column.lower() or "order" in column.lower() or "trade_intent" in column.lower()
        )
        return {
            "ok": contract_violations == 0 and cutoff_count_mismatches == 0 and not suspicious_score_columns,
            "status": "ready" if row_count else "waiting_for_base_promotion",
            "gate_table_exists": True,
            "transition_table_exists": True,
            "row_count": row_count,
            "transition_count": transition_count,
            "oos_sample_ready_rows": oos_ready,
            "final_candidate_ready_rows": final_ready,
            "status_counts": status_counts,
            "oos_contract_violations": contract_violations,
            "forward_cutoff_count_mismatches": cutoff_count_mismatches,
            "score_wiring_columns": suspicious_score_columns,
            "rows": rows,
            "transitions": transition_rows,
            "thresholds": {
                "oos_min_per_venue": OOS_MIN_PER_VENUE,
                "oos_min_pooled": OOS_MIN_POOLED,
                "oos_wilson_lower_pct": OOS_WILSON_LOWER_PCT,
            },
            "cutoff_contract": "signal_feature_ts_strictly_greater_than_frozen_cutoff",
            "source": "market_flow_reliability+market_flow_reaction",
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "raw_cloud_projection": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
