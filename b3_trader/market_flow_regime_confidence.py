from __future__ import annotations

import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 1
FEATURE_VERSION = 1
BASE_MIN_PER_VENUE = 50
BASE_MIN_POOLED = 120
OOS_MIN_PER_VENUE = 20
OOS_MIN_POOLED = 50

REGIME_BY_EVIDENCE = {
    "passive_buy_absorption_candidate": "accumulation_candidate",
    "passive_sell_absorption_candidate": "distribution_candidate",
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _sample_maturity(
    venue_a: int,
    venue_b: int,
    pooled: int,
    *,
    min_per_venue: int,
    min_pooled: int,
) -> float:
    return _clamp(
        min(
            float(venue_a) / float(min_per_venue),
            float(venue_b) / float(min_per_venue),
            float(pooled) / float(min_pooled),
        )
        * 100.0
    )


class MarketFlowRegimeConfidenceStore:
    """Shadow evidence maturity for accumulation/distribution hypotheses.

    This is deliberately not a probability and not a trading score. Each exact
    market/window/evidence/horizon group remains separate so correlated 1m/5m/
    15m/1h descriptions of the same phenomenon cannot be summed before a future
    feature-family correlation/deduplication contract exists.

    The index combines conservative base sample maturity, cross-venue Wilson
    support, forward OOS sample maturity and forward OOS Wilson support. Status
    caps prevent pre-OOS evidence from looking fully validated. No score, PAPER,
    strategy mutation or order path reads this table.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_regime_confidence_mx(
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
                base_sample_maturity_pct REAL NOT NULL DEFAULT 0,
                directional_support_pct REAL NOT NULL DEFAULT 0,
                oos_bithumb_sample_count INTEGER NOT NULL DEFAULT 0,
                oos_upbit_sample_count INTEGER NOT NULL DEFAULT 0,
                oos_pooled_sample_count INTEGER NOT NULL DEFAULT 0,
                oos_pooled_wilson_lower_pct REAL,
                oos_sample_maturity_pct REAL NOT NULL DEFAULT 0,
                oos_directional_support_pct REAL NOT NULL DEFAULT 0,
                cross_exchange_direction_consistent INTEGER NOT NULL DEFAULT 0,
                base_promotion_ready INTEGER NOT NULL DEFAULT 0,
                final_candidate_ready INTEGER NOT NULL DEFAULT 0,
                evidence_confidence_pct REAL NOT NULL DEFAULT 0,
                confidence_band TEXT NOT NULL,
                family_aggregation_blocked INTEGER NOT NULL DEFAULT 1,
                probability_interpretation INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'market_flow_reliability+market_flow_promotion_gate',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(market,signal_window_label,signal_evidence_label,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_regime_confidence
            ON research_market_flow_regime_confidence_mx(
                final_candidate_ready DESC,evidence_confidence_pct DESC,market
            );
            """
        )
        self.conn.commit()

    def _source_rows(self) -> list[dict[str, Any]]:
        tables = {
            str(row[0])
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "research_market_flow_reliability_mx" not in tables:
            return []
        has_gate = "research_market_flow_promotion_gate_mx" in tables
        gate_join = (
            "LEFT JOIN research_market_flow_promotion_gate_mx g "
            "ON g.market=r.market AND g.signal_window_label=r.signal_window_label "
            "AND g.signal_evidence_label=r.signal_evidence_label AND g.horizon_label=r.horizon_label"
            if has_gate
            else ""
        )
        gate_columns = (
            "g.status AS promotion_gate_status,g.oos_bithumb_sample_count,g.oos_upbit_sample_count,"
            "g.oos_pooled_sample_count,g.oos_pooled_wilson_lower_pct,g.oos_direction_consistent,"
            "g.final_candidate_ready"
            if has_gate
            else "NULL AS promotion_gate_status,0 AS oos_bithumb_sample_count,0 AS oos_upbit_sample_count,"
            "0 AS oos_pooled_sample_count,NULL AS oos_pooled_wilson_lower_pct,0 AS oos_direction_consistent,"
            "0 AS final_candidate_ready"
        )
        rows = self.conn.execute(
            f"""SELECT r.market,r.signal_window_label,r.signal_evidence_label,r.horizon_label,
                       r.bithumb_sample_count,r.upbit_sample_count,r.pooled_sample_count,
                       r.pooled_wilson_lower_pct,r.cross_exchange_direction_consistent,
                       r.promotion_ready,r.status AS reliability_status,{gate_columns}
                FROM research_market_flow_reliability_mx r
                {gate_join}
                WHERE r.signal_evidence_label IN ('passive_buy_absorption_candidate','passive_sell_absorption_candidate')"""
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _confidence_band(
        *,
        reliability_status: str,
        promotion_gate_status: str | None,
        final_ready: bool,
    ) -> str:
        if final_ready:
            return "oos_validated_shadow"
        if promotion_gate_status == "oos_mixed":
            return "oos_mixed"
        if promotion_gate_status == "collecting_oos":
            return "base_validated_oos_collecting"
        if reliability_status == "validated_candidate":
            return "base_validated_oos_pending"
        if reliability_status == "directional_watch":
            return "directional_watch"
        if reliability_status == "mixed_cross_exchange":
            return "mixed_cross_exchange"
        return "collecting"

    @staticmethod
    def _confidence_value(row: dict[str, Any]) -> tuple[float, float, float, float, float]:
        base_maturity = _sample_maturity(
            int(row.get("bithumb_sample_count") or 0),
            int(row.get("upbit_sample_count") or 0),
            int(row.get("pooled_sample_count") or 0),
            min_per_venue=BASE_MIN_PER_VENUE,
            min_pooled=BASE_MIN_POOLED,
        )
        cross_consistent = bool(int(row.get("cross_exchange_direction_consistent") or 0))
        directional_support = (
            _clamp(float(row.get("pooled_wilson_lower_pct") or 0.0))
            if cross_consistent
            else 0.0
        )
        oos_maturity = _sample_maturity(
            int(row.get("oos_bithumb_sample_count") or 0),
            int(row.get("oos_upbit_sample_count") or 0),
            int(row.get("oos_pooled_sample_count") or 0),
            min_per_venue=OOS_MIN_PER_VENUE,
            min_pooled=OOS_MIN_POOLED,
        )
        oos_consistent = bool(int(row.get("oos_direction_consistent") or 0))
        oos_support = (
            _clamp(float(row.get("oos_pooled_wilson_lower_pct") or 0.0))
            if oos_consistent
            else 0.0
        )

        value = (
            0.35 * base_maturity
            + 0.25 * directional_support
            + 0.20 * oos_maturity
            + 0.20 * oos_support
        )
        reliability_status = str(row.get("reliability_status") or "collecting")
        base_ready = bool(int(row.get("promotion_ready") or 0))
        final_ready = bool(int(row.get("final_candidate_ready") or 0))
        if final_ready:
            cap = 100.0
        elif base_ready:
            cap = 79.9
        elif reliability_status == "directional_watch":
            cap = 59.9
        else:
            cap = 39.9
        return base_maturity, directional_support, oos_maturity, oos_support, _clamp(value, 0.0, cap)

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(now or time.time())
        rows = self._source_rows()
        self.conn.execute("DELETE FROM research_market_flow_regime_confidence_mx")
        band_counts: Counter[str] = Counter()
        regime_counts: Counter[str] = Counter()
        high_shadow_rows = 0

        for row in rows:
            evidence = str(row["signal_evidence_label"])
            regime = REGIME_BY_EVIDENCE[evidence]
            base_maturity, directional_support, oos_maturity, oos_support, confidence = self._confidence_value(row)
            final_ready = bool(int(row.get("final_candidate_ready") or 0))
            band = self._confidence_band(
                reliability_status=str(row.get("reliability_status") or "collecting"),
                promotion_gate_status=(
                    str(row["promotion_gate_status"])
                    if row.get("promotion_gate_status") is not None
                    else None
                ),
                final_ready=final_ready,
            )
            self.conn.execute(
                """INSERT INTO research_market_flow_regime_confidence_mx(
                       market,signal_window_label,signal_evidence_label,regime_label,horizon_label,
                       reliability_status,promotion_gate_status,
                       bithumb_sample_count,upbit_sample_count,pooled_sample_count,pooled_wilson_lower_pct,
                       base_sample_maturity_pct,directional_support_pct,
                       oos_bithumb_sample_count,oos_upbit_sample_count,oos_pooled_sample_count,
                       oos_pooled_wilson_lower_pct,oos_sample_maturity_pct,oos_directional_support_pct,
                       cross_exchange_direction_consistent,base_promotion_ready,final_candidate_ready,
                       evidence_confidence_pct,confidence_band,family_aggregation_blocked,
                       probability_interpretation,source,received_at,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,0,?,?,?,?)""",
                (
                    str(row["market"]),str(row["signal_window_label"]),evidence,regime,str(row["horizon_label"]),
                    str(row.get("reliability_status") or "collecting"),row.get("promotion_gate_status"),
                    int(row.get("bithumb_sample_count") or 0),int(row.get("upbit_sample_count") or 0),
                    int(row.get("pooled_sample_count") or 0),row.get("pooled_wilson_lower_pct"),
                    base_maturity,directional_support,
                    int(row.get("oos_bithumb_sample_count") or 0),int(row.get("oos_upbit_sample_count") or 0),
                    int(row.get("oos_pooled_sample_count") or 0),row.get("oos_pooled_wilson_lower_pct"),
                    oos_maturity,oos_support,
                    int(row.get("cross_exchange_direction_consistent") or 0),int(row.get("promotion_ready") or 0),
                    1 if final_ready else 0,confidence,band,
                    "market_flow_reliability+market_flow_promotion_gate",stamp,FEATURE_VERSION,SCHEMA_VERSION,
                ),
            )
            band_counts[band] += 1
            regime_counts[regime] += 1
            high_shadow_rows += 1 if final_ready and confidence >= 80.0 else 0

        self.conn.commit()
        return {
            "ok": True,
            "status": "computed" if rows else "waiting_for_reliability_rows",
            "rows_written": len(rows),
            "regime_counts": dict(regime_counts),
            "confidence_band_counts": dict(band_counts),
            "oos_validated_high_confidence_shadow_rows": high_shadow_rows,
            "confidence_contract": {
                "interpretation": "evidence_maturity_not_probability_not_trading_score",
                "base_sample_weight": 0.35,
                "base_directional_wilson_weight": 0.25,
                "oos_sample_weight": 0.20,
                "oos_directional_wilson_weight": 0.20,
                "pre_oos_cap_pct": 79.9,
                "directional_watch_cap_pct": 59.9,
                "mixed_or_collecting_cap_pct": 39.9,
                "family_aggregation_blocked": True,
            },
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }

    def audit(self) -> dict[str, Any]:
        exists = bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_regime_confidence_mx'"
        ).fetchone())
        if not exists:
            return {
                "ok": True,
                "status": "waiting_for_table",
                "table_exists": False,
                "row_count": 0,
                "paper_only": True,
                "score_wired": False,
                "can_place_orders": False,
            }
        row_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_regime_confidence_mx"
        ).fetchone()[0])
        aggregation_violations = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_regime_confidence_mx WHERE family_aggregation_blocked!=1"
        ).fetchone()[0])
        probability_violations = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_regime_confidence_mx WHERE probability_interpretation!=0"
        ).fetchone()[0])
        cap_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_regime_confidence_mx WHERE
                   (final_candidate_ready=0 AND base_promotion_ready=1 AND evidence_confidence_pct>79.9)
                OR (base_promotion_ready=0 AND reliability_status='directional_watch' AND evidence_confidence_pct>59.9)
                OR (base_promotion_ready=0 AND reliability_status!='directional_watch' AND evidence_confidence_pct>39.9)
                OR evidence_confidence_pct<0 OR evidence_confidence_pct>100"""
        ).fetchone()[0])
        regime_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_regime_confidence_mx WHERE
                   (signal_evidence_label='passive_buy_absorption_candidate' AND regime_label!='accumulation_candidate')
                OR (signal_evidence_label='passive_sell_absorption_candidate' AND regime_label!='distribution_candidate')"""
        ).fetchone()[0])
        columns = {
            str(row[1])
            for row in self.conn.execute(
                "PRAGMA table_info(research_market_flow_regime_confidence_mx)"
            ).fetchall()
        }
        suspicious_wiring_columns = sorted(
            column
            for column in columns
            if "order" in column.lower() or "trade_intent" in column.lower() or "strategy" in column.lower()
        )
        rows = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_regime_confidence_mx
               ORDER BY final_candidate_ready DESC,evidence_confidence_pct DESC,
                        pooled_sample_count DESC,market,signal_window_label,horizon_label LIMIT 40"""
        ).fetchall()]
        band_counts = {
            str(row["confidence_band"]): int(row["n"])
            for row in self.conn.execute(
                "SELECT confidence_band,COUNT(*) AS n FROM research_market_flow_regime_confidence_mx GROUP BY confidence_band"
            ).fetchall()
        }
        ok = not (
            aggregation_violations
            or probability_violations
            or cap_violations
            or regime_violations
            or suspicious_wiring_columns
        )
        return {
            "ok": ok,
            "status": "ready" if row_count else "waiting_for_reliability_rows",
            "table_exists": True,
            "row_count": row_count,
            "confidence_band_counts": band_counts,
            "aggregation_contract_violations": aggregation_violations,
            "probability_contract_violations": probability_violations,
            "confidence_cap_violations": cap_violations,
            "regime_mapping_violations": regime_violations,
            "wiring_columns": suspicious_wiring_columns,
            "rows": rows,
            "interpretation": "evidence_maturity_not_probability_not_trading_score",
            "family_aggregation_blocked": True,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
            "raw_cloud_projection": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
