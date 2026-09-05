from __future__ import annotations

import math
import sqlite3
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .market_flow_event_cluster import EXPECTED_EXCHANGES, REGIME_BY_EVIDENCE, WINDOW_SECONDS

SCHEMA_VERSION = 1
FEATURE_VERSION = 1
REFERENCE_NOTIONAL_KRW = 750_000.0
OBSERVATION_MIN_EVENTS_PER_SIDE = 20
CONFIRMATION_MIN_EVENTS_PER_SIDE = 40
COMPARISON_POLICY = "separate_forward_activation+same_calendar_window+cross_exchange_only+750k_full_cost"
V1_CLUSTER_POLICY = "fixed_anchor_reaction_overlap+earliest_per_exchange+750k+outcome_blind"


def _wilson_lower_pct(successes: int, sample_count: int, z: float = 1.96) -> float | None:
    n = int(sample_count)
    if n <= 0:
        return None
    hits = max(0, min(n, int(successes)))
    phat = hits / n
    z2 = z * z
    den = 1.0 + z2 / n
    center = phat + z2 / (2.0 * n)
    margin = z * math.sqrt((phat * (1.0 - phat) + z2 / (4.0 * n)) / n)
    return max(0.0, (center - margin) / den) * 100.0


class MarketFlowAbsorptionConsensusV2OosComparatorStore:
    """Separate forward-only 750K OOS comparison between v1 and v2.

    The comparator has its own activation timestamp. Research outcomes observed
    before this comparator was defined are context only and never enter the
    comparison metrics. V1 is rebuilt from exact 750K notional-sensitivity rows
    using fixed-anchor, outcome-blind overlap clustering. V2 uses only already
    deduplicated cross-exchange full-cost-ready v2 events.

    This layer never selects a winner and is unwired from score, PAPER decisions,
    strategy mutation, sizing, and order placement.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_absorption_consensus_v2_oos_comparator_control_mx(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                activation_ts REAL NOT NULL,
                v2_forward_activation_ts REAL NOT NULL,
                reference_notional_krw REAL NOT NULL,
                historical_comparison_backfill INTEGER NOT NULL DEFAULT 0,
                winner_selection_enabled INTEGER NOT NULL DEFAULT 0,
                comparison_policy TEXT NOT NULL,
                last_checked_at REAL NOT NULL,
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS research_market_flow_absorption_consensus_v2_oos_comparison_mx(
                scope_label TEXT NOT NULL,
                market_label TEXT NOT NULL,
                regime_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                comparator_activation_ts REAL NOT NULL,
                reference_notional_krw REAL NOT NULL,
                v1_event_count INTEGER NOT NULL DEFAULT 0,
                v2_event_count INTEGER NOT NULL DEFAULT 0,
                v1_positive_event_count INTEGER NOT NULL DEFAULT 0,
                v2_positive_event_count INTEGER NOT NULL DEFAULT 0,
                v1_both_exchange_positive_count INTEGER NOT NULL DEFAULT 0,
                v2_both_exchange_positive_count INTEGER NOT NULL DEFAULT 0,
                v1_mean_full_cost_adjusted_return_pct REAL,
                v2_mean_full_cost_adjusted_return_pct REAL,
                delta_v2_minus_v1_mean_return_pct REAL,
                v1_hit_rate_pct REAL,
                v2_hit_rate_pct REAL,
                delta_v2_minus_v1_hit_rate_pct REAL,
                v1_wilson_lower_pct REAL,
                v2_wilson_lower_pct REAL,
                v1_both_exchange_positive_rate_pct REAL,
                v2_both_exchange_positive_rate_pct REAL,
                v1_both_exchange_positive_wilson_lower_pct REAL,
                v2_both_exchange_positive_wilson_lower_pct REAL,
                observation_comparable INTEGER NOT NULL DEFAULT 0,
                confirmation_comparable INTEGER NOT NULL DEFAULT 0,
                winner_selection_enabled INTEGER NOT NULL DEFAULT 0,
                statistical_significance_claim INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'v1_750k_oos+v2_consensus_oos',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(scope_label,market_label,regime_label,horizon_label)
            );
            """
        )
        self.conn.commit()

    def _table_exists(self, name: str) -> bool:
        return bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone())

    def _v2_forward_activation(self) -> float | None:
        table = "research_market_flow_absorption_consensus_v2_forward_control_mx"
        if not self._table_exists(table):
            return None
        row = self.conn.execute(
            f"SELECT activation_ts FROM {table} WHERE singleton=1"
        ).fetchone()
        return float(row["activation_ts"]) if row else None

    def _activation(self, stamp: float) -> tuple[float | None, str]:
        row = self.conn.execute(
            """SELECT activation_ts FROM
               research_market_flow_absorption_consensus_v2_oos_comparator_control_mx
               WHERE singleton=1"""
        ).fetchone()
        if row:
            return float(row["activation_ts"]), "existing"

        v2_activation = self._v2_forward_activation()
        if v2_activation is None:
            return None, "waiting_for_v2_forward_activation"
        existing = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_oos_comparison_mx"
        ).fetchone()[0])
        if existing:
            raise RuntimeError("comparison rows exist without immutable comparator activation")
        with self.conn:
            self.conn.execute(
                """INSERT INTO research_market_flow_absorption_consensus_v2_oos_comparator_control_mx(
                       singleton,activation_ts,v2_forward_activation_ts,reference_notional_krw,
                       historical_comparison_backfill,winner_selection_enabled,comparison_policy,
                       last_checked_at,received_at,feature_version,schema_version
                   ) VALUES(1,?,?,?,?,?,?,?,?,?,?)""",
                (
                    stamp, v2_activation, REFERENCE_NOTIONAL_KRW, 0, 0,
                    COMPARISON_POLICY, stamp, stamp, FEATURE_VERSION, SCHEMA_VERSION,
                ),
            )
        return stamp, "activated"

    @staticmethod
    def _rep_key(row: dict[str, Any]) -> tuple[float, int, str, str]:
        window = str(row.get("signal_window_label") or "")
        return (
            float(row["signal_feature_ts"]),
            int(WINDOW_SECONDS.get(window, 10**9)),
            window,
            str(row.get("signal_evidence_label") or ""),
        )

    @staticmethod
    def _clusters(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        ordered = sorted(rows, key=lambda r: (
            float(r["signal_feature_ts"]), float(r["reaction_end_ts"]),
            str(r["exchange"]), int(WINDOW_SECONDS.get(str(r["signal_window_label"]), 10**9)),
            str(r["signal_window_label"]),
        ))
        clusters: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        anchor_end: float | None = None
        for row in ordered:
            signal_ts = float(row["signal_feature_ts"])
            if not current or anchor_end is None or signal_ts >= anchor_end:
                if current:
                    clusters.append(current)
                current = [row]
                anchor_end = float(row["reaction_end_ts"])
            else:
                current.append(row)
        if current:
            clusters.append(current)
        return clusters

    def _v1_rows(self, activation: float) -> list[dict[str, Any]]:
        table = "research_market_flow_full_cost_notional_sensitivity_mx"
        if not self._table_exists(table):
            return []
        raw = self.conn.execute(
            f"""SELECT exchange,market,signal_window_label,signal_feature_ts,
                       signal_evidence_label,horizon_label,reaction_end_ts,
                       gross_hypothesis_return_pct,total_transaction_cost_bps,
                       full_cost_adjusted_return_pct
                FROM {table}
                WHERE full_cost_ready=1
                  AND reference_notional_krw=?
                  AND signal_feature_ts>=?
                  AND reaction_end_ts>signal_feature_ts
                  AND full_cost_adjusted_return_pct IS NOT NULL
                ORDER BY market,signal_feature_ts,horizon_label,exchange,signal_window_label""",
            (REFERENCE_NOTIONAL_KRW, activation),
        ).fetchall()
        rows: list[dict[str, Any]] = []
        for item in raw:
            row = dict(item)
            regime = REGIME_BY_EVIDENCE.get(str(row["signal_evidence_label"]))
            if regime is None:
                continue
            row["regime_label"] = str(regime)
            rows.append(row)
        return rows

    def _v1_events(self, activation: float) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in self._v1_rows(activation):
            grouped[(str(row["market"]), str(row["regime_label"]), str(row["horizon_label"]))].append(row)

        events: list[dict[str, Any]] = []
        for (market, regime, horizon), rows in grouped.items():
            for members in self._clusters(rows):
                by_exchange: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for member in members:
                    by_exchange[str(member["exchange"])].append(member)
                reps = {
                    exchange: min(exchange_rows, key=self._rep_key)
                    for exchange, exchange_rows in by_exchange.items()
                }
                if not all(exchange in reps for exchange in EXPECTED_EXCHANGES):
                    continue
                selected = [reps[exchange] for exchange in EXPECTED_EXCHANGES]
                adjusted = [float(row["full_cost_adjusted_return_pct"]) for row in selected]
                gross = [float(row["gross_hypothesis_return_pct"]) for row in selected]
                costs = [float(row["total_transaction_cost_bps"]) for row in selected]
                anchor = min(selected, key=self._rep_key)
                events.append({
                    "market": market,
                    "regime_label": regime,
                    "horizon_label": horizon,
                    "event_ts": float(anchor["signal_feature_ts"]),
                    "mean_full_cost_adjusted_return_pct": statistics.fmean(adjusted),
                    "mean_gross_hypothesis_return_pct": statistics.fmean(gross),
                    "mean_total_transaction_cost_bps": statistics.fmean(costs),
                    "positive_event": 1 if statistics.fmean(adjusted) > 0.0 else 0,
                    "both_exchange_positive": 1 if all(v > 0.0 for v in adjusted) else 0,
                })
        return sorted(events, key=lambda r: (r["event_ts"], r["market"], r["horizon_label"]))

    def _v2_events(self, activation: float) -> list[dict[str, Any]]:
        table = "research_market_flow_absorption_consensus_v2_event_mx"
        if not self._table_exists(table):
            return []
        rows = self.conn.execute(
            f"""SELECT market,regime_label,horizon_label,consensus_received_at,
                       mean_full_cost_adjusted_return_pct,positive_event,both_exchange_positive
                FROM {table}
                WHERE suppressed_overlap=0
                  AND cross_exchange_full_cost_ready=1
                  AND consensus_received_at>=?
                  AND mean_full_cost_adjusted_return_pct IS NOT NULL
                ORDER BY consensus_received_at,market,horizon_label""",
            (activation,),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(rows)
        values = [float(row["mean_full_cost_adjusted_return_pct"]) for row in rows]
        hits = sum(1 for row in rows if int(row["positive_event"] or 0) == 1)
        both = sum(1 for row in rows if int(row["both_exchange_positive"] or 0) == 1)
        return {
            "n": n, "hits": hits, "both": both,
            "mean": statistics.fmean(values) if values else None,
            "hit_rate": hits / n * 100.0 if n else None,
            "wilson": _wilson_lower_pct(hits, n),
            "both_rate": both / n * 100.0 if n else None,
            "both_wilson": _wilson_lower_pct(both, n),
        }

    def _insert_comparison(
        self, scope: str, market: str, regime: str, horizon: str,
        activation: float, v1_rows: list[dict[str, Any]],
        v2_rows: list[dict[str, Any]], stamp: float,
    ) -> None:
        v1 = self._metrics(v1_rows)
        v2 = self._metrics(v2_rows)
        observation = min(v1["n"], v2["n"]) >= OBSERVATION_MIN_EVENTS_PER_SIDE
        confirmation = min(v1["n"], v2["n"]) >= CONFIRMATION_MIN_EVENTS_PER_SIDE
        status = "confirmation_comparable" if confirmation else (
            "observation_comparable" if observation else "collecting"
        )
        delta_mean = v2["mean"] - v1["mean"] if v1["mean"] is not None and v2["mean"] is not None else None
        delta_hit = v2["hit_rate"] - v1["hit_rate"] if v1["hit_rate"] is not None and v2["hit_rate"] is not None else None
        self.conn.execute(
            """INSERT INTO research_market_flow_absorption_consensus_v2_oos_comparison_mx(
                   scope_label,market_label,regime_label,horizon_label,comparator_activation_ts,
                   reference_notional_krw,v1_event_count,v2_event_count,
                   v1_positive_event_count,v2_positive_event_count,
                   v1_both_exchange_positive_count,v2_both_exchange_positive_count,
                   v1_mean_full_cost_adjusted_return_pct,v2_mean_full_cost_adjusted_return_pct,
                   delta_v2_minus_v1_mean_return_pct,v1_hit_rate_pct,v2_hit_rate_pct,
                   delta_v2_minus_v1_hit_rate_pct,v1_wilson_lower_pct,v2_wilson_lower_pct,
                   v1_both_exchange_positive_rate_pct,v2_both_exchange_positive_rate_pct,
                   v1_both_exchange_positive_wilson_lower_pct,
                   v2_both_exchange_positive_wilson_lower_pct,observation_comparable,
                   confirmation_comparable,winner_selection_enabled,statistical_significance_claim,
                   status,source,received_at,feature_version,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,
                        'v1_750k_oos+v2_consensus_oos',?,?,?)""",
            (
                scope, market, regime, horizon, activation, REFERENCE_NOTIONAL_KRW,
                v1["n"], v2["n"], v1["hits"], v2["hits"], v1["both"], v2["both"],
                v1["mean"], v2["mean"], delta_mean, v1["hit_rate"], v2["hit_rate"],
                delta_hit, v1["wilson"], v2["wilson"], v1["both_rate"], v2["both_rate"],
                v1["both_wilson"], v2["both_wilson"],
                1 if observation else 0, 1 if confirmation else 0,
                status, stamp, FEATURE_VERSION, SCHEMA_VERSION,
            ),
        )

    def _refresh(self, activation: float, stamp: float) -> dict[str, int]:
        v1 = self._v1_events(activation)
        v2 = self._v2_events(activation)
        self.conn.execute("DELETE FROM research_market_flow_absorption_consensus_v2_oos_comparison_mx")
        keys = sorted({(str(r["market"]), str(r["regime_label"]), str(r["horizon_label"])) for r in [*v1, *v2]})
        rows_written = 0
        for market, regime, horizon in keys:
            self._insert_comparison(
                "market", market, regime, horizon, activation,
                [r for r in v1 if r["market"] == market and r["regime_label"] == regime and r["horizon_label"] == horizon],
                [r for r in v2 if r["market"] == market and r["regime_label"] == regime and r["horizon_label"] == horizon],
                stamp,
            )
            rows_written += 1
        pooled = sorted({(str(r["regime_label"]), str(r["horizon_label"])) for r in [*v1, *v2]})
        for regime, horizon in pooled:
            self._insert_comparison(
                "pooled", "__POOLED__", regime, horizon, activation,
                [r for r in v1 if r["regime_label"] == regime and r["horizon_label"] == horizon],
                [r for r in v2 if r["regime_label"] == regime and r["horizon_label"] == horizon],
                stamp,
            )
            rows_written += 1
        observation = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_oos_comparison_mx WHERE observation_comparable=1"
        ).fetchone()[0])
        confirmation = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_oos_comparison_mx WHERE confirmation_comparable=1"
        ).fetchone()[0])
        return {
            "v1_cross_exchange_events": len(v1),
            "v2_cross_exchange_events": len(v2),
            "comparison_rows": rows_written,
            "observation_comparable_rows": observation,
            "confirmation_comparable_rows": confirmation,
        }

    def _context(self, activation: float) -> dict[str, int]:
        v1_before = 0
        v1_table = "research_market_flow_full_cost_notional_sensitivity_mx"
        if self._table_exists(v1_table):
            v1_before = int(self.conn.execute(
                f"""SELECT COUNT(*) FROM {v1_table}
                    WHERE full_cost_ready=1 AND reference_notional_krw=? AND signal_feature_ts<?""",
                (REFERENCE_NOTIONAL_KRW, activation),
            ).fetchone()[0])
        v2_before = 0
        v2_table = "research_market_flow_absorption_consensus_v2_event_mx"
        if self._table_exists(v2_table):
            v2_before = int(self.conn.execute(
                f"""SELECT COUNT(*) FROM {v2_table}
                    WHERE suppressed_overlap=0 AND cross_exchange_full_cost_ready=1
                      AND consensus_received_at<?""",
                (activation,),
            ).fetchone()[0])
        return {
            "v1_750k_ready_members_before_comparator_activation_context": v1_before,
            "v2_ready_events_before_comparator_activation_context": v2_before,
        }

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(now or time.time())
        activation, activation_status = self._activation(stamp)
        if activation is None:
            return {
                "ok": True, "status": activation_status, "activation_present": False,
                "reference_notional_krw": REFERENCE_NOTIONAL_KRW,
                "historical_comparison_backfill": False, "winner_selection_enabled": False,
                "paper_only": True, "shadow_only": True, "score_wired": False,
                "can_place_orders": False, "can_modify_strategy": False,
            }
        metrics = self._refresh(activation, stamp)
        context = self._context(activation)
        with self.conn:
            self.conn.execute(
                """UPDATE research_market_flow_absorption_consensus_v2_oos_comparator_control_mx
                   SET last_checked_at=?,received_at=? WHERE singleton=1""",
                (stamp, stamp),
            )
        return {
            "ok": True, "status": "computed", "activation_status": activation_status,
            "activation_ts": activation, "v2_forward_activation_ts": self._v2_forward_activation(),
            "reference_notional_krw": REFERENCE_NOTIONAL_KRW, **metrics, **context,
            "comparison_policy": COMPARISON_POLICY, "v1_cluster_policy": V1_CLUSTER_POLICY,
            "historical_comparison_backfill": False, "winner_selection_enabled": False,
            "statistical_significance_claim": False, "network_fetches": False,
            "paper_only": True, "shadow_only": True, "score_wired": False,
            "can_place_orders": False, "can_modify_strategy": False,
        }

    def audit(self) -> dict[str, Any]:
        control = self.conn.execute(
            "SELECT * FROM research_market_flow_absorption_consensus_v2_oos_comparator_control_mx WHERE singleton=1"
        ).fetchone()
        if not control:
            return {
                "ok": True, "status": "waiting_for_comparator_activation",
                "activation_present": False, "paper_only": True, "shadow_only": True,
                "score_wired": False, "can_place_orders": False,
            }
        activation = float(control["activation_ts"])
        v2_activation = float(control["v2_forward_activation_ts"])
        notional_bad = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_oos_comparison_mx
               WHERE ABS(reference_notional_krw-?)>0.000001""",
            (REFERENCE_NOTIONAL_KRW,),
        ).fetchone()[0])
        winner_bad = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_oos_comparison_mx
               WHERE winner_selection_enabled<>0 OR statistical_significance_claim<>0"""
        ).fetchone()[0])
        threshold_bad = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_oos_comparison_mx
               WHERE observation_comparable <>
                     CASE WHEN MIN(v1_event_count,v2_event_count)>=? THEN 1 ELSE 0 END
                  OR confirmation_comparable <>
                     CASE WHEN MIN(v1_event_count,v2_event_count)>=? THEN 1 ELSE 0 END""",
            (OBSERVATION_MIN_EVENTS_PER_SIDE, CONFIRMATION_MIN_EVENTS_PER_SIDE),
        ).fetchone()[0])
        status_bad = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_oos_comparison_mx
               WHERE status NOT IN ('collecting','observation_comparable','confirmation_comparable')"""
        ).fetchone()[0])
        rows = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_oos_comparison_mx"
        ).fetchone()[0])
        observation = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_oos_comparison_mx WHERE observation_comparable=1"
        ).fetchone()[0])
        confirmation = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_oos_comparison_mx WHERE confirmation_comparable=1"
        ).fetchone()[0])
        v1_events = len(self._v1_events(activation))
        v2_events = len(self._v2_events(activation))
        controls_clean = (
            activation >= v2_activation
            and int(control["historical_comparison_backfill"]) == 0
            and int(control["winner_selection_enabled"]) == 0
            and abs(float(control["reference_notional_krw"]) - REFERENCE_NOTIONAL_KRW) <= 0.000001
            and str(control["comparison_policy"]) == COMPARISON_POLICY
        )
        clean = controls_clean and notional_bad == 0 and winner_bad == 0 and threshold_bad == 0 and status_bad == 0
        return {
            "ok": clean, "status": "ready" if clean else "contract_violation",
            "activation_present": True, "activation_ts": activation,
            "v2_forward_activation_ts": v2_activation,
            "activation_order_clean": activation >= v2_activation,
            "controls_clean": controls_clean, "notional_mismatch_rows": notional_bad,
            "winner_selection_violation_rows": winner_bad, "threshold_mismatch_rows": threshold_bad,
            "invalid_status_rows": status_bad, "v1_cross_exchange_events": v1_events,
            "v2_cross_exchange_events": v2_events, "comparison_rows": rows,
            "observation_comparable_rows": observation,
            "confirmation_comparable_rows": confirmation,
            "reference_notional_krw": REFERENCE_NOTIONAL_KRW,
            "observation_min_events_per_side": OBSERVATION_MIN_EVENTS_PER_SIDE,
            "confirmation_min_events_per_side": CONFIRMATION_MIN_EVENTS_PER_SIDE,
            "historical_comparison_backfill": False, "winner_selection_enabled": False,
            "statistical_significance_claim": False, "network_fetches": False,
            "paper_only": True, "shadow_only": True, "score_wired": False,
            "can_place_orders": False, "can_modify_strategy": False,
            "feature_version": FEATURE_VERSION, "schema_version": SCHEMA_VERSION,
        }
