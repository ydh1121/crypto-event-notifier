from __future__ import annotations

import json
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
CLUSTER_POLICY = "same_market+same_regime+same_horizon+fixed_anchor_reaction_overlap_full_cost_v2"
REPRESENTATIVE_POLICY = "earliest_signal_per_exchange_then_shortest_window_no_performance_selection"


class MarketFlowFullCostEventClusterStore:
    """Cluster only forward rows with complete fee+spread+ladder transaction costs.

    The fixed-anchor and representative-selection policies intentionally match
    the spread-only event-cluster layer. This makes the v2 output comparable
    without rewriting or retrospectively upgrading the v1 evidence ledger.

    Statistical independence is not claimed. Nothing here is wired to score,
    PAPER decisions, strategy mutation, or order placement.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_full_cost_event_cluster_mx(
                event_id TEXT PRIMARY KEY,
                market TEXT NOT NULL,
                regime_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                event_anchor_signal_ts REAL NOT NULL,
                event_anchor_end_ts REAL NOT NULL,
                member_count INTEGER NOT NULL DEFAULT 0,
                representative_count INTEGER NOT NULL DEFAULT 0,
                exchange_count INTEGER NOT NULL DEFAULT 0,
                cross_exchange_confirmed INTEGER NOT NULL DEFAULT 0,
                exchanges_json TEXT NOT NULL DEFAULT '[]',
                signal_windows_json TEXT NOT NULL DEFAULT '[]',
                fee_profiles_json TEXT NOT NULL DEFAULT '[]',
                mean_gross_hypothesis_return_pct REAL,
                mean_total_transaction_cost_bps REAL,
                mean_full_cost_adjusted_return_pct REAL,
                full_cost_adjusted_positive INTEGER,
                reference_notional_krw REAL NOT NULL,
                cluster_policy TEXT NOT NULL,
                representative_policy TEXT NOT NULL,
                independence_claim INTEGER NOT NULL DEFAULT 0,
                pseudo_replication_reduced INTEGER NOT NULL DEFAULT 1,
                source TEXT NOT NULL DEFAULT 'market_flow_full_cost_edge',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_full_cost_event_cluster_group
            ON research_market_flow_full_cost_event_cluster_mx(
                market,regime_label,horizon_label,event_anchor_signal_ts DESC
            );

            CREATE TABLE IF NOT EXISTS research_market_flow_full_cost_event_cluster_member_mx(
                event_id TEXT NOT NULL,
                market TEXT NOT NULL,
                regime_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                exchange TEXT NOT NULL,
                signal_window_label TEXT NOT NULL,
                signal_feature_ts REAL NOT NULL,
                signal_evidence_label TEXT NOT NULL,
                reaction_end_ts REAL NOT NULL,
                gross_hypothesis_return_pct REAL NOT NULL,
                total_transaction_cost_bps REAL NOT NULL,
                full_cost_adjusted_return_pct REAL NOT NULL,
                reference_notional_krw REAL NOT NULL,
                fee_profile TEXT NOT NULL,
                representative_for_exchange INTEGER NOT NULL DEFAULT 0,
                suppressed_overlap_member INTEGER NOT NULL DEFAULT 1,
                cluster_policy TEXT NOT NULL,
                representative_policy TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'market_flow_full_cost_edge',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(event_id,exchange,signal_window_label,signal_feature_ts,signal_evidence_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_full_cost_event_cluster_member_rep
            ON research_market_flow_full_cost_event_cluster_member_mx(
                event_id,representative_for_exchange DESC,exchange,signal_feature_ts
            );

            CREATE TABLE IF NOT EXISTS research_market_flow_full_cost_event_cluster_stats_mx(
                market TEXT NOT NULL,
                regime_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                source_member_count INTEGER NOT NULL DEFAULT 0,
                event_count INTEGER NOT NULL DEFAULT 0,
                venue_representative_count INTEGER NOT NULL DEFAULT 0,
                suppressed_overlap_member_count INTEGER NOT NULL DEFAULT 0,
                event_count_reduction_pct REAL NOT NULL DEFAULT 0,
                member_suppression_pct REAL NOT NULL DEFAULT 0,
                cross_exchange_event_count INTEGER NOT NULL DEFAULT 0,
                cross_exchange_event_share_pct REAL NOT NULL DEFAULT 0,
                mean_event_full_cost_adjusted_return_pct REAL,
                event_full_cost_adjusted_hit_rate_pct REAL,
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(market,regime_label,horizon_label)
            );
            """
        )
        self.conn.commit()

    def _source_rows(self) -> list[dict[str, Any]]:
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_full_cost_edge_mx'"
        ).fetchone()
        if not exists:
            return []
        rows = self.conn.execute(
            """SELECT exchange,market,signal_window_label,signal_feature_ts,
                      signal_evidence_label,horizon_label,reaction_end_ts,
                      gross_hypothesis_return_pct,total_transaction_cost_bps,
                      full_cost_adjusted_return_pct,reference_notional_krw,fee_profile
               FROM research_market_flow_full_cost_edge_mx
               WHERE full_cost_edge_ready=1
                 AND fee_model_ready=1
                 AND ladder_slippage_ready=1
                 AND total_transaction_cost_bps IS NOT NULL
                 AND full_cost_adjusted_return_pct IS NOT NULL
                 AND fee_profile IS NOT NULL
                 AND reaction_end_ts>signal_feature_ts
               ORDER BY market,signal_feature_ts,horizon_label,exchange,signal_window_label"""
        ).fetchall()
        result: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw)
            regime = REGIME_BY_EVIDENCE.get(str(row.get("signal_evidence_label") or ""))
            if regime is None:
                continue
            row["regime_label"] = regime
            result.append(row)
        return result

    @staticmethod
    def _event_id(market: str, regime: str, horizon: str, anchor_ts: float) -> str:
        return f"{market}|{regime}|{horizon}|full-cost|{anchor_ts:.6f}"

    @staticmethod
    def _representative_key(row: dict[str, Any]) -> tuple[float, int, str, str]:
        window = str(row.get("signal_window_label") or "")
        return (
            float(row["signal_feature_ts"]),
            int(WINDOW_SECONDS.get(window, 10**9)),
            window,
            str(row.get("signal_evidence_label") or ""),
        )

    @staticmethod
    def _fixed_anchor_clusters(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        ordered = sorted(
            rows,
            key=lambda row: (
                float(row["signal_feature_ts"]),
                float(row["reaction_end_ts"]),
                str(row["exchange"]),
                int(WINDOW_SECONDS.get(str(row["signal_window_label"]), 10**9)),
                str(row["signal_window_label"]),
            ),
        )
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

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(now or time.time())
        rows = self._source_rows()
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[(str(row["market"]), str(row["regime_label"]), str(row["horizon_label"]))].append(row)

        self.conn.execute("DELETE FROM research_market_flow_full_cost_event_cluster_member_mx")
        self.conn.execute("DELETE FROM research_market_flow_full_cost_event_cluster_mx")
        self.conn.execute("DELETE FROM research_market_flow_full_cost_event_cluster_stats_mx")

        total_events = 0
        total_representatives = 0
        total_suppressed = 0
        total_cross_exchange = 0

        for key, group_rows in grouped.items():
            market, regime, horizon = key
            event_summaries: list[dict[str, Any]] = []
            for members in self._fixed_anchor_clusters(group_rows):
                anchor = min(members, key=self._representative_key)
                anchor_ts = float(anchor["signal_feature_ts"])
                anchor_end = float(anchor["reaction_end_ts"])
                event_id = self._event_id(market, regime, horizon, anchor_ts)

                by_exchange: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for member in members:
                    by_exchange[str(member["exchange"])].append(member)
                representatives = {
                    exchange: min(exchange_rows, key=self._representative_key)
                    for exchange, exchange_rows in by_exchange.items()
                }
                representative_rows = list(representatives.values())
                representative_ids = {id(row) for row in representative_rows}
                exchanges = sorted(representatives)
                windows = sorted({str(member["signal_window_label"]) for member in members})
                fee_profiles = sorted({
                    f'{str(row["exchange"])}:{str(row["fee_profile"])}'
                    for row in representative_rows
                })
                cross_exchange = all(exchange in representatives for exchange in EXPECTED_EXCHANGES)

                gross_values = [float(row["gross_hypothesis_return_pct"]) for row in representative_rows]
                total_costs = [float(row["total_transaction_cost_bps"]) for row in representative_rows]
                adjusted_values = [float(row["full_cost_adjusted_return_pct"]) for row in representative_rows]
                notionals = [float(row["reference_notional_krw"]) for row in representative_rows]
                mean_gross = statistics.fmean(gross_values)
                mean_cost = statistics.fmean(total_costs)
                mean_adjusted = statistics.fmean(adjusted_values)
                reference_notional = min(notionals)

                self.conn.execute(
                    """INSERT INTO research_market_flow_full_cost_event_cluster_mx(
                           event_id,market,regime_label,horizon_label,event_anchor_signal_ts,event_anchor_end_ts,
                           member_count,representative_count,exchange_count,cross_exchange_confirmed,
                           exchanges_json,signal_windows_json,fee_profiles_json,
                           mean_gross_hypothesis_return_pct,mean_total_transaction_cost_bps,
                           mean_full_cost_adjusted_return_pct,full_cost_adjusted_positive,
                           reference_notional_krw,cluster_policy,representative_policy,
                           independence_claim,pseudo_replication_reduced,source,received_at,
                           feature_version,schema_version
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, ?,0,1,
                                'market_flow_full_cost_edge',?,?,?)""",
                    (
                        event_id,market,regime,horizon,anchor_ts,anchor_end,len(members),
                        len(representative_rows),len(exchanges),1 if cross_exchange else 0,
                        json.dumps(exchanges,ensure_ascii=False),json.dumps(windows,ensure_ascii=False),
                        json.dumps(fee_profiles,ensure_ascii=False),mean_gross,mean_cost,mean_adjusted,
                        1 if mean_adjusted > 0 else 0,reference_notional,
                        CLUSTER_POLICY,REPRESENTATIVE_POLICY,stamp,FEATURE_VERSION,SCHEMA_VERSION,
                    ),
                )

                for member in members:
                    is_rep = id(member) in representative_ids
                    self.conn.execute(
                        """INSERT INTO research_market_flow_full_cost_event_cluster_member_mx(
                               event_id,market,regime_label,horizon_label,exchange,signal_window_label,
                               signal_feature_ts,signal_evidence_label,reaction_end_ts,
                               gross_hypothesis_return_pct,total_transaction_cost_bps,
                               full_cost_adjusted_return_pct,reference_notional_krw,fee_profile,
                               representative_for_exchange,suppressed_overlap_member,
                               cluster_policy,representative_policy,source,received_at,
                               feature_version,schema_version
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                                    'market_flow_full_cost_edge',?,?,?)""",
                        (
                            event_id,market,regime,horizon,str(member["exchange"]),
                            str(member["signal_window_label"]),float(member["signal_feature_ts"]),
                            str(member["signal_evidence_label"]),float(member["reaction_end_ts"]),
                            float(member["gross_hypothesis_return_pct"]),
                            float(member["total_transaction_cost_bps"]),
                            float(member["full_cost_adjusted_return_pct"]),
                            float(member["reference_notional_krw"]),str(member["fee_profile"]),
                            1 if is_rep else 0,0 if is_rep else 1,
                            CLUSTER_POLICY,REPRESENTATIVE_POLICY,stamp,FEATURE_VERSION,SCHEMA_VERSION,
                        ),
                    )

                event_summaries.append({
                    "mean_adjusted": mean_adjusted,
                    "cross_exchange": cross_exchange,
                    "representative_count": len(representative_rows),
                })
                total_events += 1
                total_representatives += len(representative_rows)
                total_suppressed += len(members) - len(representative_rows)
                total_cross_exchange += 1 if cross_exchange else 0

            event_count = len(event_summaries)
            representative_count = sum(int(item["representative_count"]) for item in event_summaries)
            suppressed_count = len(group_rows) - representative_count
            cross_count = sum(1 for item in event_summaries if item["cross_exchange"])
            adjusted = [float(item["mean_adjusted"]) for item in event_summaries]
            self.conn.execute(
                """INSERT INTO research_market_flow_full_cost_event_cluster_stats_mx(
                       market,regime_label,horizon_label,source_member_count,event_count,
                       venue_representative_count,suppressed_overlap_member_count,
                       event_count_reduction_pct,member_suppression_pct,cross_exchange_event_count,
                       cross_exchange_event_share_pct,mean_event_full_cost_adjusted_return_pct,
                       event_full_cost_adjusted_hit_rate_pct,received_at,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    market,regime,horizon,len(group_rows),event_count,representative_count,suppressed_count,
                    (1.0 - event_count / len(group_rows)) * 100.0 if group_rows else 0.0,
                    suppressed_count / len(group_rows) * 100.0 if group_rows else 0.0,
                    cross_count,cross_count / event_count * 100.0 if event_count else 0.0,
                    statistics.fmean(adjusted) if adjusted else None,
                    sum(1 for value in adjusted if value > 0.0) / len(adjusted) * 100.0 if adjusted else None,
                    stamp,FEATURE_VERSION,SCHEMA_VERSION,
                ),
            )

        self.conn.commit()
        return {
            "ok": True,
            "status": "computed" if rows else "waiting_for_forward_full_cost_rows",
            "source_full_cost_ready_members": len(rows),
            "events_written": total_events,
            "venue_representatives": total_representatives,
            "suppressed_overlap_members": total_suppressed,
            "cross_exchange_events": total_cross_exchange,
            "event_count_reduction_pct": ((1.0 - total_events / len(rows)) * 100.0 if rows else 0.0),
            "cluster_policy": CLUSTER_POLICY,
            "representative_policy": REPRESENTATIVE_POLICY,
            "statistical_independence_claim": False,
            "historical_full_cost_backfill": False,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }

    def audit(self) -> dict[str, Any]:
        exists = bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_full_cost_event_cluster_mx'"
        ).fetchone())
        if not exists:
            return {"ok": True, "status": "waiting_for_table", "tables_ready": False, "event_count": 0}

        event_count = int(self.conn.execute("SELECT COUNT(*) FROM research_market_flow_full_cost_event_cluster_mx").fetchone()[0])
        member_count = int(self.conn.execute("SELECT COUNT(*) FROM research_market_flow_full_cost_event_cluster_member_mx").fetchone()[0])
        rep_count = int(self.conn.execute("SELECT COUNT(*) FROM research_market_flow_full_cost_event_cluster_member_mx WHERE representative_for_exchange=1").fetchone()[0])
        suppressed_count = int(self.conn.execute("SELECT COUNT(*) FROM research_market_flow_full_cost_event_cluster_member_mx WHERE suppressed_overlap_member=1").fetchone()[0])
        cross_count = int(self.conn.execute("SELECT COUNT(*) FROM research_market_flow_full_cost_event_cluster_mx WHERE cross_exchange_confirmed=1").fetchone()[0])

        membership_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_full_cost_event_cluster_member_mx m
               LEFT JOIN research_market_flow_full_cost_event_cluster_mx e ON e.event_id=m.event_id
               WHERE e.event_id IS NULL OR m.market!=e.market OR m.regime_label!=e.regime_label
                  OR m.horizon_label!=e.horizon_label OR m.signal_feature_ts<e.event_anchor_signal_ts
                  OR m.signal_feature_ts>=e.event_anchor_end_ts"""
        ).fetchone()[0])
        representative_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM (
                   SELECT event_id,exchange,SUM(representative_for_exchange) AS reps
                   FROM research_market_flow_full_cost_event_cluster_member_mx GROUP BY event_id,exchange
               ) WHERE reps!=1"""
        ).fetchone()[0])
        event_mean_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_full_cost_event_cluster_mx e
               WHERE ABS(e.mean_full_cost_adjusted_return_pct - (
                   SELECT AVG(m.full_cost_adjusted_return_pct)
                   FROM research_market_flow_full_cost_event_cluster_member_mx m
                   WHERE m.event_id=e.event_id AND m.representative_for_exchange=1
               ))>0.000001"""
        ).fetchone()[0])
        cross_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_full_cost_event_cluster_mx e
               WHERE e.cross_exchange_confirmed != CASE WHEN (
                   EXISTS(SELECT 1 FROM research_market_flow_full_cost_event_cluster_member_mx m
                          WHERE m.event_id=e.event_id AND m.exchange='bithumb' AND m.representative_for_exchange=1)
                   AND EXISTS(SELECT 1 FROM research_market_flow_full_cost_event_cluster_member_mx m
                          WHERE m.event_id=e.event_id AND m.exchange='upbit' AND m.representative_for_exchange=1)
               ) THEN 1 ELSE 0 END"""
        ).fetchone()[0])
        source_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_full_cost_event_cluster_member_mx m
               LEFT JOIN research_market_flow_full_cost_edge_mx s
                 ON s.exchange=m.exchange AND s.market=m.market
                AND s.signal_window_label=m.signal_window_label AND s.signal_feature_ts=m.signal_feature_ts
                AND s.signal_evidence_label=m.signal_evidence_label AND s.horizon_label=m.horizon_label
               WHERE s.full_cost_edge_ready!=1 OR s.total_transaction_cost_bps IS NULL
                  OR s.full_cost_adjusted_return_pct IS NULL"""
        ).fetchone()[0])
        columns = {str(row[1]) for row in self.conn.execute("PRAGMA table_info(research_market_flow_full_cost_event_cluster_mx)").fetchall()}
        suspicious = sorted(column for column in columns if "trade_intent" in column.lower() or "order_qty" in column.lower() or "position_size" in column.lower() or "strategy_action" in column.lower())
        stats = [dict(row) for row in self.conn.execute("SELECT * FROM research_market_flow_full_cost_event_cluster_stats_mx ORDER BY event_count DESC,market,regime_label,horizon_label").fetchall()]
        samples = [dict(row) for row in self.conn.execute("SELECT * FROM research_market_flow_full_cost_event_cluster_mx ORDER BY event_anchor_signal_ts DESC LIMIT 12").fetchall()]
        ok = membership_violations == 0 and representative_violations == 0 and event_mean_violations == 0 and cross_violations == 0 and source_violations == 0 and not suspicious
        return {
            "ok": ok,
            "status": "ready" if event_count else "waiting_for_forward_full_cost_rows",
            "tables_ready": True,
            "event_count": event_count,
            "member_count": member_count,
            "venue_representative_count": rep_count,
            "suppressed_overlap_member_count": suppressed_count,
            "cross_exchange_event_count": cross_count,
            "membership_contract_violations": membership_violations,
            "representative_contract_violations": representative_violations,
            "event_mean_contract_violations": event_mean_violations,
            "cross_exchange_contract_violations": cross_violations,
            "full_cost_source_contract_violations": source_violations,
            "suspicious_wiring_columns": suspicious,
            "stats": stats,
            "sample_events": samples,
            "cluster_policy": CLUSTER_POLICY,
            "representative_policy": REPRESENTATIVE_POLICY,
            "interpretation": "forward_full_cost_overlap_clustered_events_not_independence_claim_not_trading_score",
            "historical_full_cost_backfill": False,
            "raw_cloud_projection": False,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
