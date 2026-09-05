from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 2
FEATURE_VERSION = 1
CORRELATION_POLICY = (
    "same_market+same_regime+same_horizon+nested_signal_windows_"
    "conservative_full_suppression_v1"
)
AGGREGATION_METHOD = "representative_only_full_suppression"
WINDOW_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}
BAND_RANK = {
    "collecting": 0,
    "mixed_cross_exchange": 1,
    "directional_watch": 2,
    "base_validated_oos_pending": 3,
    "base_validated_oos_collecting": 4,
    "oos_mixed": 4,
    "oos_validated_shadow": 5,
}


class MarketFlowFamilyDedupStore:
    """Conservative multi-timeframe family deduplication for flow regimes.

    Rows are grouped only when market, regime direction and reaction horizon are
    identical. One representative receives effective weight 1.0 and correlated
    sibling windows receive 0.0. `base_gate_started` is propagated separately
    from current `base_promotion_ready` so a frozen forward OOS cohort keeps its
    lifecycle identity even when the expanding discovery sample later falls back
    under the current promotion threshold.

    Accumulation and distribution are never netted, different reaction horizons
    are never merged, and the family output is evidence maturity rather than a
    probability or trading score. It is not wired to PAPER, strategy or orders.
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

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        columns = {
            str(row[1])
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_market_flow_family_dedup_mx(
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
                representative_base_gate_started INTEGER NOT NULL DEFAULT 0,
                representative_base_promotion_ready INTEGER NOT NULL DEFAULT 0,
                representative_final_candidate_ready INTEGER NOT NULL DEFAULT 0,
                suppressed_member_count INTEGER NOT NULL DEFAULT 0,
                suppressed_windows_json TEXT NOT NULL DEFAULT '[]',
                raw_confidence_sum_pct REAL NOT NULL DEFAULT 0,
                effective_family_confidence_pct REAL NOT NULL DEFAULT 0,
                inflation_avoided_pct REAL NOT NULL DEFAULT 0,
                correlation_policy TEXT NOT NULL,
                aggregation_method TEXT NOT NULL,
                empirical_correlation_estimated INTEGER NOT NULL DEFAULT 0,
                probability_interpretation INTEGER NOT NULL DEFAULT 0,
                received_at REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'market_flow_regime_confidence',
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 2,
                PRIMARY KEY(market,regime_label,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_family_dedup_rep
            ON research_market_flow_family_dedup_mx(
                representative_final_candidate_ready DESC,
                effective_family_confidence_pct DESC,
                market,regime_label,horizon_label
            );

            CREATE TABLE IF NOT EXISTS research_market_flow_family_member_mx(
                market TEXT NOT NULL,
                regime_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                signal_window_label TEXT NOT NULL,
                signal_evidence_label TEXT NOT NULL,
                evidence_confidence_pct REAL NOT NULL DEFAULT 0,
                confidence_band TEXT NOT NULL,
                pooled_sample_count INTEGER NOT NULL DEFAULT 0,
                cross_exchange_direction_consistent INTEGER NOT NULL DEFAULT 0,
                base_gate_started INTEGER NOT NULL DEFAULT 0,
                base_promotion_ready INTEGER NOT NULL DEFAULT 0,
                final_candidate_ready INTEGER NOT NULL DEFAULT 0,
                validation_rank INTEGER NOT NULL DEFAULT 0,
                representative_member INTEGER NOT NULL DEFAULT 0,
                suppressed_correlated_member INTEGER NOT NULL DEFAULT 1,
                effective_weight REAL NOT NULL DEFAULT 0,
                effective_confidence_contribution_pct REAL NOT NULL DEFAULT 0,
                correlation_policy TEXT NOT NULL,
                received_at REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'market_flow_regime_confidence',
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 2,
                PRIMARY KEY(market,regime_label,horizon_label,signal_window_label,signal_evidence_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_family_member_rep
            ON research_market_flow_family_member_mx(
                representative_member DESC,evidence_confidence_pct DESC,market,regime_label,horizon_label
            );
            """
        )
        self._ensure_column(
            "research_market_flow_family_dedup_mx",
            "representative_base_gate_started",
            "INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column(
            "research_market_flow_family_member_mx",
            "base_gate_started",
            "INTEGER NOT NULL DEFAULT 0",
        )
        self.conn.commit()

    def _source_rows(self) -> list[dict[str, Any]]:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_regime_confidence_mx'"
        ).fetchone()
        if not exists:
            return []
        rows = self.conn.execute(
            """SELECT market,signal_window_label,signal_evidence_label,regime_label,horizon_label,
                      reliability_status,promotion_gate_status,pooled_sample_count,
                      cross_exchange_direction_consistent,base_gate_started,
                      base_promotion_ready,final_candidate_ready,
                      evidence_confidence_pct,confidence_band
               FROM research_market_flow_regime_confidence_mx"""
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _validation_rank(row: dict[str, Any]) -> int:
        if int(row.get("final_candidate_ready") or 0) == 1:
            return 5
        if int(row.get("base_gate_started") or 0) == 1 or int(row.get("base_promotion_ready") or 0) == 1:
            return 4
        if int(row.get("cross_exchange_direction_consistent") or 0) == 1:
            return 3
        return int(BAND_RANK.get(str(row.get("confidence_band") or "collecting"), 0))

    @classmethod
    def _selection_key(cls, row: dict[str, Any]) -> tuple[int, float, int, int, str]:
        return (
            cls._validation_rank(row),
            float(row.get("evidence_confidence_pct") or 0.0),
            int(row.get("pooled_sample_count") or 0),
            int(WINDOW_SECONDS.get(str(row.get("signal_window_label") or ""), 0)),
            str(row.get("signal_window_label") or ""),
        )

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(now or time.time())
        rows = self._source_rows()
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[
                (
                    str(row["market"]),
                    str(row["regime_label"]),
                    str(row["horizon_label"]),
                )
            ].append(row)

        self.conn.execute("DELETE FROM research_market_flow_family_member_mx")
        self.conn.execute("DELETE FROM research_market_flow_family_dedup_mx")

        family_size_counts: Counter[str] = Counter()
        total_suppressed = 0
        total_raw_confidence = 0.0
        total_effective_confidence = 0.0

        for key, members in grouped.items():
            market, regime, horizon = key
            representative = max(members, key=self._selection_key)
            representative_window = str(representative["signal_window_label"])
            representative_evidence = str(representative["signal_evidence_label"])
            representative_confidence = float(representative.get("evidence_confidence_pct") or 0.0)
            raw_sum = sum(float(member.get("evidence_confidence_pct") or 0.0) for member in members)
            suppressed = [
                str(member["signal_window_label"])
                for member in members
                if member is not representative
            ]
            suppressed_count = max(0, len(members) - 1)
            inflation_avoided = max(0.0, raw_sum - representative_confidence)
            family_key = f"{market}|{regime}|{horizon}"

            self.conn.execute(
                """INSERT INTO research_market_flow_family_dedup_mx(
                       market,regime_label,horizon_label,family_key,member_count,
                       representative_signal_window_label,representative_signal_evidence_label,
                       representative_confidence_pct,representative_confidence_band,
                       representative_pooled_sample_count,
                       representative_cross_exchange_direction_consistent,
                       representative_base_gate_started,representative_base_promotion_ready,
                       representative_final_candidate_ready,
                       suppressed_member_count,suppressed_windows_json,
                       raw_confidence_sum_pct,effective_family_confidence_pct,inflation_avoided_pct,
                       correlation_policy,aggregation_method,empirical_correlation_estimated,
                       probability_interpretation,received_at,source,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, ?,?,0,0,?,'market_flow_regime_confidence',?,?)""",
                (
                    market,regime,horizon,family_key,len(members),
                    representative_window,representative_evidence,representative_confidence,
                    str(representative.get("confidence_band") or "collecting"),
                    int(representative.get("pooled_sample_count") or 0),
                    int(representative.get("cross_exchange_direction_consistent") or 0),
                    int(representative.get("base_gate_started") or 0),
                    int(representative.get("base_promotion_ready") or 0),
                    int(representative.get("final_candidate_ready") or 0),
                    suppressed_count,json.dumps(sorted(suppressed),ensure_ascii=False),
                    raw_sum,representative_confidence,inflation_avoided,
                    CORRELATION_POLICY,AGGREGATION_METHOD,stamp,FEATURE_VERSION,SCHEMA_VERSION,
                ),
            )

            for member in members:
                is_rep = member is representative
                confidence = float(member.get("evidence_confidence_pct") or 0.0)
                self.conn.execute(
                    """INSERT INTO research_market_flow_family_member_mx(
                           market,regime_label,horizon_label,signal_window_label,signal_evidence_label,
                           evidence_confidence_pct,confidence_band,pooled_sample_count,
                           cross_exchange_direction_consistent,base_gate_started,
                           base_promotion_ready,final_candidate_ready,
                           validation_rank,representative_member,suppressed_correlated_member,
                           effective_weight,effective_confidence_contribution_pct,
                           correlation_policy,received_at,source,feature_version,schema_version
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'market_flow_regime_confidence',?,?)""",
                    (
                        market,regime,horizon,str(member["signal_window_label"]),
                        str(member["signal_evidence_label"]),confidence,
                        str(member.get("confidence_band") or "collecting"),
                        int(member.get("pooled_sample_count") or 0),
                        int(member.get("cross_exchange_direction_consistent") or 0),
                        int(member.get("base_gate_started") or 0),
                        int(member.get("base_promotion_ready") or 0),
                        int(member.get("final_candidate_ready") or 0),
                        self._validation_rank(member),1 if is_rep else 0,0 if is_rep else 1,
                        1.0 if is_rep else 0.0,confidence if is_rep else 0.0,
                        CORRELATION_POLICY,stamp,FEATURE_VERSION,SCHEMA_VERSION,
                    ),
                )

            family_size_counts[str(len(members))] += 1
            total_suppressed += suppressed_count
            total_raw_confidence += raw_sum
            total_effective_confidence += representative_confidence

        self.conn.commit()
        return {
            "ok": True,
            "status": "computed" if grouped else "waiting_for_regime_confidence_rows",
            "families_written": len(grouped),
            "members_written": len(rows),
            "suppressed_correlated_members": total_suppressed,
            "family_size_counts": dict(family_size_counts),
            "raw_confidence_sum_pct": total_raw_confidence,
            "effective_confidence_sum_pct": total_effective_confidence,
            "inflation_avoided_pct": max(0.0, total_raw_confidence - total_effective_confidence),
            "correlation_contract": {
                "policy": CORRELATION_POLICY,
                "aggregation_method": AGGREGATION_METHOD,
                "empirical_correlation_estimated": False,
                "representative_weight": 1.0,
                "suppressed_sibling_weight": 0.0,
                "opposite_regimes_never_netted": True,
                "different_horizons_never_merged": True,
                "base_gate_started_propagated": True,
            },
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }

    def audit(self) -> dict[str, Any]:
        tables = {
            str(row[0])
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        summary_ready = "research_market_flow_family_dedup_mx" in tables
        member_ready = "research_market_flow_family_member_mx" in tables
        if not summary_ready or not member_ready:
            return {
                "ok": True,
                "status": "waiting_for_tables",
                "summary_table_exists": summary_ready,
                "member_table_exists": member_ready,
                "family_count": 0,
                "member_count": 0,
                "paper_only": True,
                "score_wired": False,
                "can_place_orders": False,
            }

        family_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_family_dedup_mx"
        ).fetchone()[0])
        member_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_family_member_mx"
        ).fetchone()[0])
        representative_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM (
                   SELECT market,regime_label,horizon_label,SUM(representative_member) AS reps
                   FROM research_market_flow_family_member_mx
                   GROUP BY market,regime_label,horizon_label
                   HAVING reps!=1
               )"""
        ).fetchone()[0])
        weight_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM (
                   SELECT market,regime_label,horizon_label,SUM(effective_weight) AS total_weight
                   FROM research_market_flow_family_member_mx
                   GROUP BY market,regime_label,horizon_label
                   HAVING ABS(total_weight-1.0)>0.000001
               )"""
        ).fetchone()[0])
        suppression_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_family_member_mx WHERE
                   (representative_member=1 AND (suppressed_correlated_member!=0 OR effective_weight!=1.0))
                OR (representative_member=0 AND (suppressed_correlated_member!=1 OR effective_weight!=0.0))"""
        ).fetchone()[0])
        summary_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_family_dedup_mx s WHERE
                   suppressed_member_count!=member_count-1
                OR ABS(effective_family_confidence_pct-representative_confidence_pct)>0.000001
                OR raw_confidence_sum_pct+0.000001<effective_family_confidence_pct
                OR ABS(inflation_avoided_pct-(raw_confidence_sum_pct-effective_family_confidence_pct))>0.000001
                OR correlation_policy!=?
                OR aggregation_method!=?
                OR empirical_correlation_estimated!=0
                OR probability_interpretation!=0""",
            (CORRELATION_POLICY,AGGREGATION_METHOD),
        ).fetchone()[0])
        count_mismatches = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_family_dedup_mx s
               WHERE member_count!=(
                   SELECT COUNT(*) FROM research_market_flow_family_member_mx m
                   WHERE m.market=s.market AND m.regime_label=s.regime_label AND m.horizon_label=s.horizon_label
               )"""
        ).fetchone()[0])
        gate_lifecycle_mismatches = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_family_dedup_mx s
               WHERE representative_base_gate_started!=(
                   SELECT m.base_gate_started FROM research_market_flow_family_member_mx m
                   WHERE m.market=s.market AND m.regime_label=s.regime_label AND m.horizon_label=s.horizon_label
                     AND m.representative_member=1 LIMIT 1
               )"""
        ).fetchone()[0])
        columns = {
            str(row[1])
            for table in ("research_market_flow_family_dedup_mx","research_market_flow_family_member_mx")
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        suspicious_wiring_columns = sorted(
            column
            for column in columns
            if "order" in column.lower() or "trade_intent" in column.lower() or "strategy" in column.lower()
        )
        rows = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_family_dedup_mx
               ORDER BY representative_final_candidate_ready DESC,
                        representative_base_gate_started DESC,
                        effective_family_confidence_pct DESC,market,regime_label,horizon_label
               LIMIT 40"""
        ).fetchall()]
        members = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_family_member_mx
               ORDER BY market,regime_label,horizon_label,representative_member DESC,
                        evidence_confidence_pct DESC LIMIT 80"""
        ).fetchall()]
        ok = (
            representative_violations == 0
            and weight_violations == 0
            and suppression_violations == 0
            and summary_violations == 0
            and count_mismatches == 0
            and gate_lifecycle_mismatches == 0
            and not suspicious_wiring_columns
        )
        return {
            "ok": ok,
            "status": "ready" if family_count else "waiting_for_regime_confidence_rows",
            "summary_table_exists": True,
            "member_table_exists": True,
            "family_count": family_count,
            "member_count": member_count,
            "representative_contract_violations": representative_violations,
            "effective_weight_contract_violations": weight_violations,
            "suppression_contract_violations": suppression_violations,
            "summary_contract_violations": summary_violations,
            "member_count_mismatches": count_mismatches,
            "base_gate_lifecycle_mismatches": gate_lifecycle_mismatches,
            "wiring_columns": suspicious_wiring_columns,
            "rows": rows,
            "members": members,
            "correlation_policy": CORRELATION_POLICY,
            "aggregation_method": AGGREGATION_METHOD,
            "empirical_correlation_estimated": False,
            "probability_interpretation": False,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
            "raw_cloud_projection": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
