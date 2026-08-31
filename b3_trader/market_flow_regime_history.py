from __future__ import annotations

import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 1
FEATURE_VERSION = 1
HISTORY_BUCKET_SECONDS = 15 * 60
HISTORY_RETENTION_DAYS = 90
HISTORY_RETENTION_SECONDS = HISTORY_RETENTION_DAYS * 24 * 60 * 60


class MarketFlowRegimeHistoryStore:
    """Bounded shadow history for flow regime confidence and dedup families.

    Current-state confidence/family tables remain authoritative snapshots. This
    store records 15-minute research snapshots so evidence maturity and family
    representative changes can be inspected over time without wiring those
    values to PAPER, strategy mutation, score or orders.
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

    @staticmethod
    def _bucket_ts(value: float) -> float:
        return float(math.floor(float(value) / HISTORY_BUCKET_SECONDS) * HISTORY_BUCKET_SECONDS)

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_market_flow_regime_confidence_history_mx(
                snapshot_ts REAL NOT NULL,
                market TEXT NOT NULL,
                signal_window_label TEXT NOT NULL,
                signal_evidence_label TEXT NOT NULL,
                regime_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                reliability_status TEXT NOT NULL,
                promotion_gate_status TEXT,
                bithumb_sample_count INTEGER NOT NULL DEFAULT 0,
                upbit_sample_count INTEGER NOT NULL DEFAULT 0,
                pooled_sample_count INTEGER NOT NULL DEFAULT 0,
                pooled_wilson_lower_pct REAL,
                oos_bithumb_sample_count INTEGER NOT NULL DEFAULT 0,
                oos_upbit_sample_count INTEGER NOT NULL DEFAULT 0,
                oos_pooled_sample_count INTEGER NOT NULL DEFAULT 0,
                oos_pooled_wilson_lower_pct REAL,
                cross_exchange_direction_consistent INTEGER NOT NULL DEFAULT 0,
                base_promotion_ready INTEGER NOT NULL DEFAULT 0,
                final_candidate_ready INTEGER NOT NULL DEFAULT 0,
                evidence_confidence_pct REAL NOT NULL DEFAULT 0,
                confidence_band TEXT NOT NULL,
                source_received_at REAL NOT NULL,
                recorded_at REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'market_flow_regime_confidence',
                probability_interpretation INTEGER NOT NULL DEFAULT 0,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(snapshot_ts,market,signal_window_label,signal_evidence_label,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_regime_confidence_history_lookup
            ON research_market_flow_regime_confidence_history_mx(
                market,signal_evidence_label,horizon_label,snapshot_ts DESC
            );

            CREATE TABLE IF NOT EXISTS research_market_flow_family_history_mx(
                snapshot_ts REAL NOT NULL,
                market TEXT NOT NULL,
                regime_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                family_key TEXT NOT NULL,
                member_count INTEGER NOT NULL DEFAULT 0,
                representative_signal_window_label TEXT NOT NULL,
                representative_signal_evidence_label TEXT NOT NULL,
                representative_confidence_pct REAL NOT NULL DEFAULT 0,
                representative_confidence_band TEXT NOT NULL,
                representative_pooled_sample_count INTEGER NOT NULL DEFAULT 0,
                representative_cross_exchange_direction_consistent INTEGER NOT NULL DEFAULT 0,
                representative_base_promotion_ready INTEGER NOT NULL DEFAULT 0,
                representative_final_candidate_ready INTEGER NOT NULL DEFAULT 0,
                suppressed_member_count INTEGER NOT NULL DEFAULT 0,
                raw_confidence_sum_pct REAL NOT NULL DEFAULT 0,
                effective_family_confidence_pct REAL NOT NULL DEFAULT 0,
                inflation_avoided_pct REAL NOT NULL DEFAULT 0,
                source_received_at REAL NOT NULL,
                recorded_at REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'market_flow_family_dedup',
                probability_interpretation INTEGER NOT NULL DEFAULT 0,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(snapshot_ts,market,regime_label,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_family_history_lookup
            ON research_market_flow_family_history_mx(
                market,regime_label,horizon_label,snapshot_ts DESC
            );
            """
        )
        self.conn.commit()

    def _table_exists(self, table: str) -> bool:
        return bool(
            self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
        )

    def _confidence_rows(self) -> list[dict[str, Any]]:
        if not self._table_exists("research_market_flow_regime_confidence_mx"):
            return []
        return [
            dict(row)
            for row in self.conn.execute(
                """SELECT market,signal_window_label,signal_evidence_label,regime_label,horizon_label,
                          reliability_status,promotion_gate_status,bithumb_sample_count,upbit_sample_count,
                          pooled_sample_count,pooled_wilson_lower_pct,oos_bithumb_sample_count,
                          oos_upbit_sample_count,oos_pooled_sample_count,oos_pooled_wilson_lower_pct,
                          cross_exchange_direction_consistent,base_promotion_ready,final_candidate_ready,
                          evidence_confidence_pct,confidence_band,received_at
                   FROM research_market_flow_regime_confidence_mx"""
            ).fetchall()
        ]

    def _family_rows(self) -> list[dict[str, Any]]:
        if not self._table_exists("research_market_flow_family_dedup_mx"):
            return []
        return [
            dict(row)
            for row in self.conn.execute(
                """SELECT market,regime_label,horizon_label,family_key,member_count,
                          representative_signal_window_label,representative_signal_evidence_label,
                          representative_confidence_pct,representative_confidence_band,
                          representative_pooled_sample_count,
                          representative_cross_exchange_direction_consistent,
                          representative_base_promotion_ready,representative_final_candidate_ready,
                          suppressed_member_count,raw_confidence_sum_pct,
                          effective_family_confidence_pct,inflation_avoided_pct,received_at
                   FROM research_market_flow_family_dedup_mx"""
            ).fetchall()
        ]

    def capture(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(now or time.time())
        bucket = self._bucket_ts(stamp)
        confidence_rows = self._confidence_rows()
        family_rows = self._family_rows()

        for row in confidence_rows:
            self.conn.execute(
                """INSERT OR REPLACE INTO research_market_flow_regime_confidence_history_mx(
                       snapshot_ts,market,signal_window_label,signal_evidence_label,regime_label,horizon_label,
                       reliability_status,promotion_gate_status,bithumb_sample_count,upbit_sample_count,
                       pooled_sample_count,pooled_wilson_lower_pct,oos_bithumb_sample_count,
                       oos_upbit_sample_count,oos_pooled_sample_count,oos_pooled_wilson_lower_pct,
                       cross_exchange_direction_consistent,base_promotion_ready,final_candidate_ready,
                       evidence_confidence_pct,confidence_band,source_received_at,recorded_at,source,
                       probability_interpretation,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'market_flow_regime_confidence',0,?,?)""",
                (
                    bucket,str(row["market"]),str(row["signal_window_label"]),
                    str(row["signal_evidence_label"]),str(row["regime_label"]),str(row["horizon_label"]),
                    str(row["reliability_status"]),row.get("promotion_gate_status"),
                    int(row.get("bithumb_sample_count") or 0),int(row.get("upbit_sample_count") or 0),
                    int(row.get("pooled_sample_count") or 0),row.get("pooled_wilson_lower_pct"),
                    int(row.get("oos_bithumb_sample_count") or 0),int(row.get("oos_upbit_sample_count") or 0),
                    int(row.get("oos_pooled_sample_count") or 0),row.get("oos_pooled_wilson_lower_pct"),
                    int(row.get("cross_exchange_direction_consistent") or 0),
                    int(row.get("base_promotion_ready") or 0),int(row.get("final_candidate_ready") or 0),
                    float(row.get("evidence_confidence_pct") or 0.0),str(row.get("confidence_band") or "collecting"),
                    float(row.get("received_at") or stamp),stamp,FEATURE_VERSION,SCHEMA_VERSION,
                ),
            )

        for row in family_rows:
            self.conn.execute(
                """INSERT OR REPLACE INTO research_market_flow_family_history_mx(
                       snapshot_ts,market,regime_label,horizon_label,family_key,member_count,
                       representative_signal_window_label,representative_signal_evidence_label,
                       representative_confidence_pct,representative_confidence_band,
                       representative_pooled_sample_count,
                       representative_cross_exchange_direction_consistent,
                       representative_base_promotion_ready,representative_final_candidate_ready,
                       suppressed_member_count,raw_confidence_sum_pct,effective_family_confidence_pct,
                       inflation_avoided_pct,source_received_at,recorded_at,source,
                       probability_interpretation,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'market_flow_family_dedup',0,?,?)""",
                (
                    bucket,str(row["market"]),str(row["regime_label"]),str(row["horizon_label"]),
                    str(row["family_key"]),int(row.get("member_count") or 0),
                    str(row["representative_signal_window_label"]),str(row["representative_signal_evidence_label"]),
                    float(row.get("representative_confidence_pct") or 0.0),
                    str(row.get("representative_confidence_band") or "collecting"),
                    int(row.get("representative_pooled_sample_count") or 0),
                    int(row.get("representative_cross_exchange_direction_consistent") or 0),
                    int(row.get("representative_base_promotion_ready") or 0),
                    int(row.get("representative_final_candidate_ready") or 0),
                    int(row.get("suppressed_member_count") or 0),
                    float(row.get("raw_confidence_sum_pct") or 0.0),
                    float(row.get("effective_family_confidence_pct") or 0.0),
                    float(row.get("inflation_avoided_pct") or 0.0),
                    float(row.get("received_at") or stamp),stamp,FEATURE_VERSION,SCHEMA_VERSION,
                ),
            )

        cutoff = bucket - HISTORY_RETENTION_SECONDS
        confidence_pruned = self.conn.execute(
            "DELETE FROM research_market_flow_regime_confidence_history_mx WHERE snapshot_ts<?",
            (cutoff,),
        ).rowcount
        family_pruned = self.conn.execute(
            "DELETE FROM research_market_flow_family_history_mx WHERE snapshot_ts<?",
            (cutoff,),
        ).rowcount
        self.conn.commit()

        return {
            "ok": True,
            "status": "captured" if confidence_rows or family_rows else "waiting_for_current_state",
            "snapshot_ts": bucket,
            "bucket_seconds": HISTORY_BUCKET_SECONDS,
            "retention_days": HISTORY_RETENTION_DAYS,
            "confidence_rows_written": len(confidence_rows),
            "family_rows_written": len(family_rows),
            "confidence_rows_pruned": int(confidence_pruned or 0),
            "family_rows_pruned": int(family_pruned or 0),
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }

    def audit(self) -> dict[str, Any]:
        confidence_ready = self._table_exists("research_market_flow_regime_confidence_history_mx")
        family_ready = self._table_exists("research_market_flow_family_history_mx")
        if not confidence_ready or not family_ready:
            return {
                "ok": True,
                "status": "waiting_for_tables",
                "confidence_table_exists": confidence_ready,
                "family_table_exists": family_ready,
                "confidence_row_count": 0,
                "family_row_count": 0,
                "paper_only": True,
                "shadow_only": True,
                "score_wired": False,
                "can_place_orders": False,
            }

        confidence_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_regime_confidence_history_mx"
        ).fetchone()[0])
        family_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_family_history_mx"
        ).fetchone()[0])
        confidence_bucket_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_regime_confidence_history_mx
               WHERE ABS(snapshot_ts - CAST(snapshot_ts/? AS INTEGER)*?)>0.000001""",
            (HISTORY_BUCKET_SECONDS,HISTORY_BUCKET_SECONDS),
        ).fetchone()[0])
        family_bucket_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_family_history_mx
               WHERE ABS(snapshot_ts - CAST(snapshot_ts/? AS INTEGER)*?)>0.000001""",
            (HISTORY_BUCKET_SECONDS,HISTORY_BUCKET_SECONDS),
        ).fetchone()[0])
        probability_violations = int(self.conn.execute(
            """SELECT
                 (SELECT COUNT(*) FROM research_market_flow_regime_confidence_history_mx WHERE probability_interpretation!=0)
                 +
                 (SELECT COUNT(*) FROM research_market_flow_family_history_mx WHERE probability_interpretation!=0)"""
        ).fetchone()[0])
        latest_confidence = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_regime_confidence_history_mx
               ORDER BY snapshot_ts DESC,evidence_confidence_pct DESC LIMIT 20"""
        ).fetchall()]
        latest_families = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_family_history_mx
               ORDER BY snapshot_ts DESC,effective_family_confidence_pct DESC LIMIT 20"""
        ).fetchall()]
        latest_snapshot = max(
            [float(row["snapshot_ts"]) for row in latest_confidence + latest_families],
            default=0.0,
        )
        cutoff = latest_snapshot - HISTORY_RETENTION_SECONDS if latest_snapshot else 0.0
        retention_violations = 0
        if latest_snapshot:
            retention_violations = int(self.conn.execute(
                """SELECT
                     (SELECT COUNT(*) FROM research_market_flow_regime_confidence_history_mx WHERE snapshot_ts<?)
                     +
                     (SELECT COUNT(*) FROM research_market_flow_family_history_mx WHERE snapshot_ts<?)""",
                (cutoff,cutoff),
            ).fetchone()[0])

        ok = (
            confidence_bucket_violations == 0
            and family_bucket_violations == 0
            and probability_violations == 0
            and retention_violations == 0
        )
        return {
            "ok": ok,
            "status": "ready" if confidence_count or family_count else "waiting_for_history",
            "confidence_table_exists": True,
            "family_table_exists": True,
            "confidence_row_count": confidence_count,
            "family_row_count": family_count,
            "latest_snapshot_ts": latest_snapshot,
            "bucket_seconds": HISTORY_BUCKET_SECONDS,
            "retention_days": HISTORY_RETENTION_DAYS,
            "confidence_bucket_violations": confidence_bucket_violations,
            "family_bucket_violations": family_bucket_violations,
            "probability_contract_violations": probability_violations,
            "retention_contract_violations": retention_violations,
            "latest_confidence": latest_confidence,
            "latest_families": latest_families,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
            "raw_cloud_projection": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
