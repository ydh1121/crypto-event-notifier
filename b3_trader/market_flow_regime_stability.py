from __future__ import annotations

import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .market_flow_regime_history import HISTORY_BUCKET_SECONDS

SCHEMA_VERSION = 1
FEATURE_VERSION = 1
MIN_CONTIGUOUS_BUCKETS = 4
STABILITY_WINDOW_BUCKETS = 12
MAX_HISTORY_BUCKETS = 24
TREND_DELTA_PCT = 5.0
VOLATILITY_RANGE_PCT = 10.0
REPRESENTATIVE_SWITCH_THRESHOLD = 2


class MarketFlowRegimeStabilityStore:
    """Shadow-only stability/degradation view over bounded family history.

    The classifier does not estimate a trading probability or score. It only
    describes whether the currently selected family representative is holding,
    improving, weakening, volatile or degraded across exact 15-minute history
    buckets. OOS lifecycle semantics take precedence over numeric confidence:
    an `oos_mixed` family is hard degradation even when maturity confidence is
    numerically high, while a started OOS gate whose current discovery sample
    has fallen back below the base threshold is soft degradation.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_regime_stability_mx(
                market TEXT NOT NULL,
                regime_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                family_key TEXT NOT NULL,
                current_snapshot_ts REAL NOT NULL,
                current_confidence_pct REAL NOT NULL DEFAULT 0,
                current_confidence_band TEXT NOT NULL,
                current_representative_signal_window_label TEXT NOT NULL,
                current_base_gate_started INTEGER NOT NULL DEFAULT 0,
                current_base_promotion_ready INTEGER NOT NULL DEFAULT 0,
                current_final_candidate_ready INTEGER NOT NULL DEFAULT 0,
                contiguous_bucket_count INTEGER NOT NULL DEFAULT 0,
                short_window_bucket_count INTEGER NOT NULL DEFAULT 0,
                stability_window_bucket_count INTEGER NOT NULL DEFAULT 0,
                short_median_confidence_pct REAL,
                stability_median_confidence_pct REAL,
                confidence_delta_vs_stability_median_pct REAL,
                short_confidence_range_pct REAL,
                representative_switch_count INTEGER NOT NULL DEFAULT 0,
                base_ready_share_pct REAL,
                final_ready_share_pct REAL,
                history_ready INTEGER NOT NULL DEFAULT 0,
                stability_window_ready INTEGER NOT NULL DEFAULT 0,
                degradation_level TEXT NOT NULL,
                degradation_reason TEXT NOT NULL,
                stability_state TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'market_flow_family_history',
                probability_interpretation INTEGER NOT NULL DEFAULT 0,
                score_wired INTEGER NOT NULL DEFAULT 0,
                can_place_orders INTEGER NOT NULL DEFAULT 0,
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(market,regime_label,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_regime_stability_state
            ON research_market_flow_regime_stability_mx(
                degradation_level,stability_state,current_confidence_pct DESC
            );
            """
        )
        self.conn.commit()

    def _history_rows(self) -> list[dict[str, Any]]:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_family_history_mx'"
        ).fetchone()
        if not exists:
            return []
        return [
            dict(row)
            for row in self.conn.execute(
                """SELECT snapshot_ts,market,regime_label,horizon_label,family_key,
                          representative_signal_window_label,representative_confidence_pct,
                          representative_confidence_band,representative_base_gate_started,
                          representative_base_promotion_ready,representative_final_candidate_ready
                   FROM research_market_flow_family_history_mx
                   ORDER BY market,regime_label,horizon_label,snapshot_ts DESC"""
            ).fetchall()
        ]

    @staticmethod
    def _contiguous(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        ordered = sorted(rows, key=lambda row: float(row["snapshot_ts"]), reverse=True)
        contiguous = [ordered[0]]
        expected = float(ordered[0]["snapshot_ts"]) - HISTORY_BUCKET_SECONDS
        for row in ordered[1:]:
            if len(contiguous) >= MAX_HISTORY_BUCKETS:
                break
            stamp = float(row["snapshot_ts"])
            if abs(stamp - expected) > 0.000001:
                break
            contiguous.append(row)
            expected -= HISTORY_BUCKET_SECONDS
        return contiguous

    @staticmethod
    def _median(rows: list[dict[str, Any]]) -> float | None:
        values = [float(row.get("representative_confidence_pct") or 0.0) for row in rows]
        return statistics.median(values) if values else None

    @staticmethod
    def _share(rows: list[dict[str, Any]], key: str) -> float | None:
        if not rows:
            return None
        hits = sum(1 for row in rows if int(row.get(key) or 0) == 1)
        return hits / len(rows) * 100.0

    @staticmethod
    def _representative_switches(rows: list[dict[str, Any]]) -> int:
        if len(rows) < 2:
            return 0
        chronological = list(reversed(rows))
        switches = 0
        previous = str(chronological[0].get("representative_signal_window_label") or "")
        for row in chronological[1:]:
            current = str(row.get("representative_signal_window_label") or "")
            if current != previous:
                switches += 1
            previous = current
        return switches

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(now or time.time())
        rows = self._history_rows()
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[(str(row["market"]), str(row["regime_label"]), str(row["horizon_label"]))].append(row)

        self.conn.execute("DELETE FROM research_market_flow_regime_stability_mx")
        state_counts: Counter[str] = Counter()
        degradation_counts: Counter[str] = Counter()
        history_ready_rows = 0
        stability_ready_rows = 0

        for key, family_rows in grouped.items():
            contiguous = self._contiguous(family_rows)
            if not contiguous:
                continue
            current = contiguous[0]
            short_rows = contiguous[:MIN_CONTIGUOUS_BUCKETS]
            stability_rows = contiguous[:STABILITY_WINDOW_BUCKETS]
            contiguous_count = len(contiguous)
            history_ready = contiguous_count >= MIN_CONTIGUOUS_BUCKETS
            stability_ready = contiguous_count >= STABILITY_WINDOW_BUCKETS
            short_median = self._median(short_rows)
            stability_median = self._median(stability_rows)
            current_confidence = float(current.get("representative_confidence_pct") or 0.0)
            delta = (
                current_confidence - float(stability_median)
                if stability_median is not None
                else None
            )
            short_values = [float(row.get("representative_confidence_pct") or 0.0) for row in short_rows]
            short_range = (max(short_values) - min(short_values)) if short_values else None
            representative_switches = self._representative_switches(stability_rows)
            base_ready_share = self._share(stability_rows, "representative_base_promotion_ready")
            final_ready_share = self._share(stability_rows, "representative_final_candidate_ready")

            current_band = str(current.get("representative_confidence_band") or "collecting")
            base_gate_started = int(current.get("representative_base_gate_started") or 0)
            base_ready = int(current.get("representative_base_promotion_ready") or 0)
            final_ready = int(current.get("representative_final_candidate_ready") or 0)

            if current_band == "oos_mixed":
                degradation_level = "hard"
                degradation_reason = "forward_oos_mixed"
                stability_state = "hard_degradation"
            elif base_gate_started == 1 and base_ready == 0:
                degradation_level = "soft"
                degradation_reason = "base_threshold_lost_after_oos_gate_started"
                stability_state = "soft_degradation"
            else:
                degradation_level = "none"
                degradation_reason = ""
                if not history_ready:
                    stability_state = "insufficient_history"
                elif not stability_ready:
                    stability_state = "observing"
                elif representative_switches >= REPRESENTATIVE_SWITCH_THRESHOLD:
                    stability_state = "volatile"
                elif short_range is not None and short_range >= VOLATILITY_RANGE_PCT:
                    stability_state = "volatile"
                elif delta is not None and delta >= TREND_DELTA_PCT:
                    stability_state = "improving"
                elif delta is not None and delta <= -TREND_DELTA_PCT:
                    stability_state = "weakening"
                else:
                    stability_state = "stable"

            self.conn.execute(
                """INSERT INTO research_market_flow_regime_stability_mx(
                       market,regime_label,horizon_label,family_key,current_snapshot_ts,
                       current_confidence_pct,current_confidence_band,
                       current_representative_signal_window_label,current_base_gate_started,
                       current_base_promotion_ready,current_final_candidate_ready,
                       contiguous_bucket_count,short_window_bucket_count,stability_window_bucket_count,
                       short_median_confidence_pct,stability_median_confidence_pct,
                       confidence_delta_vs_stability_median_pct,short_confidence_range_pct,
                       representative_switch_count,base_ready_share_pct,final_ready_share_pct,
                       history_ready,stability_window_ready,degradation_level,degradation_reason,
                       stability_state,source,probability_interpretation,score_wired,can_place_orders,
                       received_at,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                            'market_flow_family_history',0,0,0,?,?,?)""",
                (
                    *key,
                    str(current.get("family_key") or ""),
                    float(current["snapshot_ts"]),
                    current_confidence,
                    current_band,
                    str(current.get("representative_signal_window_label") or ""),
                    base_gate_started,
                    base_ready,
                    final_ready,
                    contiguous_count,
                    len(short_rows),
                    len(stability_rows),
                    short_median,
                    stability_median,
                    delta,
                    short_range,
                    representative_switches,
                    base_ready_share,
                    final_ready_share,
                    1 if history_ready else 0,
                    1 if stability_ready else 0,
                    degradation_level,
                    degradation_reason,
                    stability_state,
                    stamp,
                    FEATURE_VERSION,
                    SCHEMA_VERSION,
                ),
            )
            state_counts[stability_state] += 1
            degradation_counts[degradation_level] += 1
            history_ready_rows += 1 if history_ready else 0
            stability_ready_rows += 1 if stability_ready else 0

        self.conn.commit()
        return {
            "ok": True,
            "status": "computed" if grouped else "waiting_for_family_history",
            "families_written": len(grouped),
            "history_ready_rows": history_ready_rows,
            "stability_window_ready_rows": stability_ready_rows,
            "state_counts": dict(state_counts),
            "degradation_counts": dict(degradation_counts),
            "thresholds": {
                "history_bucket_seconds": HISTORY_BUCKET_SECONDS,
                "min_contiguous_buckets": MIN_CONTIGUOUS_BUCKETS,
                "stability_window_buckets": STABILITY_WINDOW_BUCKETS,
                "max_history_buckets": MAX_HISTORY_BUCKETS,
                "trend_delta_pct": TREND_DELTA_PCT,
                "volatility_range_pct": VOLATILITY_RANGE_PCT,
                "representative_switch_threshold": REPRESENTATIVE_SWITCH_THRESHOLD,
            },
            "paper_only": True,
            "shadow_only": True,
            "probability_interpretation": False,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }

    def audit(self) -> dict[str, Any]:
        exists = bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_regime_stability_mx'"
        ).fetchone())
        if not exists:
            return {
                "ok": True,
                "status": "waiting_for_table",
                "table_exists": False,
                "row_count": 0,
                "paper_only": True,
                "shadow_only": True,
                "score_wired": False,
                "can_place_orders": False,
            }

        row_count = int(self.conn.execute("SELECT COUNT(*) FROM research_market_flow_regime_stability_mx").fetchone()[0])
        hard_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_regime_stability_mx
               WHERE stability_state='hard_degradation' AND (
                   degradation_level!='hard' OR degradation_reason!='forward_oos_mixed'
                   OR current_confidence_band!='oos_mixed'
               )"""
        ).fetchone()[0])
        soft_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_regime_stability_mx
               WHERE stability_state='soft_degradation' AND (
                   degradation_level!='soft'
                   OR degradation_reason!='base_threshold_lost_after_oos_gate_started'
                   OR current_base_gate_started!=1 OR current_base_promotion_ready!=0
                   OR current_confidence_band='oos_mixed'
               )"""
        ).fetchone()[0])
        readiness_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_regime_stability_mx WHERE
                   history_ready!=(CASE WHEN contiguous_bucket_count>=? THEN 1 ELSE 0 END)
                OR stability_window_ready!=(CASE WHEN contiguous_bucket_count>=? THEN 1 ELSE 0 END)""",
            (MIN_CONTIGUOUS_BUCKETS, STABILITY_WINDOW_BUCKETS),
        ).fetchone()[0])
        safety_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_regime_stability_mx WHERE
                   probability_interpretation!=0 OR score_wired!=0 OR can_place_orders!=0"""
        ).fetchone()[0])
        columns = {
            str(row[1])
            for row in self.conn.execute("PRAGMA table_info(research_market_flow_regime_stability_mx)").fetchall()
        }
        suspicious_columns = sorted(
            column
            for column in columns
            if ("trade_intent" in column.lower() or "order_qty" in column.lower() or "position_size" in column.lower())
        )
        state_counts = {
            str(row["stability_state"]): int(row["n"])
            for row in self.conn.execute(
                "SELECT stability_state,COUNT(*) AS n FROM research_market_flow_regime_stability_mx GROUP BY stability_state"
            ).fetchall()
        }
        degradation_counts = {
            str(row["degradation_level"]): int(row["n"])
            for row in self.conn.execute(
                "SELECT degradation_level,COUNT(*) AS n FROM research_market_flow_regime_stability_mx GROUP BY degradation_level"
            ).fetchall()
        }
        rows = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_regime_stability_mx
               ORDER BY CASE degradation_level WHEN 'hard' THEN 0 WHEN 'soft' THEN 1 ELSE 2 END,
                        current_confidence_pct DESC,market,regime_label,horizon_label"""
        ).fetchall()]
        ok = (
            hard_violations == 0
            and soft_violations == 0
            and readiness_violations == 0
            and safety_violations == 0
            and not suspicious_columns
        )
        return {
            "ok": ok,
            "status": "ready" if row_count else "waiting_for_family_history",
            "table_exists": True,
            "row_count": row_count,
            "history_ready_rows": sum(1 for row in rows if int(row.get("history_ready") or 0) == 1),
            "stability_window_ready_rows": sum(1 for row in rows if int(row.get("stability_window_ready") or 0) == 1),
            "state_counts": state_counts,
            "degradation_counts": degradation_counts,
            "hard_degradation_contract_violations": hard_violations,
            "soft_degradation_contract_violations": soft_violations,
            "readiness_contract_violations": readiness_violations,
            "safety_contract_violations": safety_violations,
            "suspicious_wiring_columns": suspicious_columns,
            "rows": rows,
            "thresholds": {
                "history_bucket_seconds": HISTORY_BUCKET_SECONDS,
                "min_contiguous_buckets": MIN_CONTIGUOUS_BUCKETS,
                "stability_window_buckets": STABILITY_WINDOW_BUCKETS,
                "max_history_buckets": MAX_HISTORY_BUCKETS,
                "trend_delta_pct": TREND_DELTA_PCT,
                "volatility_range_pct": VOLATILITY_RANGE_PCT,
                "representative_switch_threshold": REPRESENTATIVE_SWITCH_THRESHOLD,
            },
            "interpretation": "longitudinal_evidence_stability_not_probability_not_trading_score",
            "paper_only": True,
            "shadow_only": True,
            "probability_interpretation": False,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
            "raw_cloud_projection": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
