from __future__ import annotations

import json
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
REGIME_BY_EVIDENCE = {
    "passive_buy_absorption_candidate": "accumulation_candidate",
    "passive_sell_absorption_candidate": "distribution_candidate",
}
WINDOW_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}
CLUSTER_POLICY = "same_market+same_regime+same_horizon+fixed_anchor_reaction_overlap_v1"
REPRESENTATIVE_POLICY = "earliest_signal_per_exchange_then_shortest_window_no_performance_selection"


class MarketFlowEventClusterStore:
    """Reduce overlapping cost-edge rows into conservative market events.

    This layer addresses pseudo-replication only. Within the same market, regime
    direction and reaction horizon, an event is anchored to the earliest signal.
    Any later signal that starts strictly before that anchor reaction end belongs
    to the same event. The anchor end is never extended by later members, so a
    transitive chain cannot merge an arbitrarily long sequence into one event.

    One representative is retained per exchange using only timing/window metadata:
    earliest signal first, then shortest signal window. Performance never enters
    representative selection. Event returns are simple means across those exchange
    representatives, preventing one venue with many repeated signals from receiving
    extra weight. Cross-exchange presence is preserved as confirmation metadata.

    The resulting events are "independent-ish" research units, not a claim of
    statistical independence, probability or trading score. Nothing here is wired
    to PAPER strategy decisions or orders.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_event_cluster_mx(
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
                mean_gross_hypothesis_return_pct REAL,
                mean_roundtrip_spread_cost_bps REAL,
                mean_spread_adjusted_hypothesis_return_pct REAL,
                spread_adjusted_positive INTEGER,
                max_reference_notional_share_pct REAL,
                cluster_policy TEXT NOT NULL,
                representative_policy TEXT NOT NULL,
                independence_claim INTEGER NOT NULL DEFAULT 0,
                pseudo_replication_reduced INTEGER NOT NULL DEFAULT 1,
                source TEXT NOT NULL DEFAULT 'market_flow_cost_edge',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_event_cluster_group
            ON research_market_flow_event_cluster_mx(
                market,regime_label,horizon_label,event_anchor_signal_ts DESC
            );

            CREATE TABLE IF NOT EXISTS research_market_flow_event_cluster_member_mx(
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
                roundtrip_spread_cost_bps REAL NOT NULL,
                spread_adjusted_hypothesis_return_pct REAL NOT NULL,
                max_reference_notional_share_pct REAL,
                representative_for_exchange INTEGER NOT NULL DEFAULT 0,
                suppressed_overlap_member INTEGER NOT NULL DEFAULT 1,
                cluster_policy TEXT NOT NULL,
                representative_policy TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'market_flow_cost_edge',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(event_id,exchange,signal_window_label,signal_feature_ts,signal_evidence_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_event_cluster_member_rep
            ON research_market_flow_event_cluster_member_mx(
                event_id,representative_for_exchange DESC,exchange,signal_feature_ts
            );

            CREATE TABLE IF NOT EXISTS research_market_flow_event_cluster_stats_mx(
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
                mean_event_spread_adjusted_return_pct REAL,
                event_spread_adjusted_hit_rate_pct REAL,
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
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_cost_edge_mx'"
        ).fetchone()
        if not exists:
            return []
        rows = self.conn.execute(
            """SELECT exchange,market,signal_window_label,signal_feature_ts,
                      signal_evidence_label,horizon_label,reaction_end_ts,
                      gross_hypothesis_return_pct,roundtrip_spread_cost_bps,
                      spread_adjusted_hypothesis_return_pct,max_reference_notional_share_pct
               FROM research_market_flow_cost_edge_mx
               WHERE orderbook_friction_ready=1
                 AND spread_adjusted_hypothesis_return_pct IS NOT NULL
                 AND roundtrip_spread_cost_bps IS NOT NULL
                 AND reaction_end_ts>signal_feature_ts
               ORDER BY market,signal_feature_ts,horizon_label,exchange,signal_window_label"""
        ).fetchall()
        result: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw)
            evidence = str(row.get("signal_evidence_label") or "")
            regime = REGIME_BY_EVIDENCE.get(evidence)
            if regime is None:
                continue
            row["regime_label"] = regime
            result.append(row)
        return result

    @staticmethod
    def _event_id(market: str, regime: str, horizon: str, anchor_ts: float) -> str:
        return f"{market}|{regime}|{horizon}|{anchor_ts:.6f}"

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
            grouped[(
                str(row["market"]),
                str(row["regime_label"]),
                str(row["horizon_label"]),
            )].append(row)

        self.conn.execute("DELETE FROM research_market_flow_event_cluster_member_mx")
        self.conn.execute("DELETE FROM research_market_flow_event_cluster_mx")
        self.conn.execute("DELETE FROM research_market_flow_event_cluster_stats_mx")

        total_events = 0
        total_representatives = 0
        total_suppressed = 0
        total_cross_exchange = 0
        group_event_rows: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)

        for key, group_rows in grouped.items():
            market, regime, horizon = key
            clusters = self._fixed_anchor_clusters(group_rows)
            for members in clusters:
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
                exchanges = sorted(representatives)
                windows = sorted({str(member["signal_window_label"]) for member in members})
                cross_exchange = all(exchange in representatives for exchange in EXPECTED_EXCHANGES)

                gross_values = [float(row["gross_hypothesis_return_pct"]) for row in representative_rows]
                spread_costs = [float(row["roundtrip_spread_cost_bps"]) for row in representative_rows]
                adjusted_values = [float(row["spread_adjusted_hypothesis_return_pct"]) for row in representative_rows]
                depth_shares = [
                    float(row["max_reference_notional_share_pct"])
                    for row in representative_rows
                    if row.get("max_reference_notional_share_pct") is not None
                ]
                mean_gross = statistics.fmean(gross_values) if gross_values else None
                mean_spread_cost = statistics.fmean(spread_costs) if spread_costs else None
                mean_adjusted = statistics.fmean(adjusted_values) if adjusted_values else None
                max_depth_share = max(depth_shares) if depth_shares else None

                self.conn.execute(
                    """INSERT INTO research_market_flow_event_cluster_mx(
                           event_id,market,regime_label,horizon_label,
                           event_anchor_signal_ts,event_anchor_end_ts,member_count,
                           representative_count,exchange_count,cross_exchange_confirmed,
                           exchanges_json,signal_windows_json,mean_gross_hypothesis_return_pct,
                           mean_roundtrip_spread_cost_bps,mean_spread_adjusted_hypothesis_return_pct,
                           spread_adjusted_positive,max_reference_notional_share_pct,
                           cluster_policy,representative_policy,independence_claim,
                           pseudo_replication_reduced,source,received_at,feature_version,schema_version
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,1,
                                'market_flow_cost_edge',?,?,?)""",
                    (
                        event_id,market,regime,horizon,anchor_ts,anchor_end,len(members),
                        len(representative_rows),len(exchanges),1 if cross_exchange else 0,
                        json.dumps(exchanges,ensure_ascii=False),json.dumps(windows,ensure_ascii=False),
                        mean_gross,mean_spread_cost,mean_adjusted,
                        1 if mean_adjusted is not None and mean_adjusted > 0 else 0,
                        max_depth_share,CLUSTER_POLICY,REPRESENTATIVE_POLICY,
                        stamp,FEATURE_VERSION,SCHEMA_VERSION,
                    ),
                )

                representative_ids = {id(row) for row in representative_rows}
                for member in members:
                    is_rep = id(member) in representative_ids
                    self.conn.execute(
                        """INSERT INTO research_market_flow_event_cluster_member_mx(
                               event_id,market,regime_label,horizon_label,exchange,
                               signal_window_label,signal_feature_ts,signal_evidence_label,
                               reaction_end_ts,gross_hypothesis_return_pct,
                               roundtrip_spread_cost_bps,spread_adjusted_hypothesis_return_pct,
                               max_reference_notional_share_pct,representative_for_exchange,
                               suppressed_overlap_member,cluster_policy,representative_policy,
                               source,received_at,feature_version,schema_version
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                                    'market_flow_cost_edge',?,?,?)""",
                        (
                            event_id,market,regime,horizon,str(member["exchange"]),
                            str(member["signal_window_label"]),float(member["signal_feature_ts"]),
                            str(member["signal_evidence_label"]),float(member["reaction_end_ts"]),
                            float(member["gross_hypothesis_return_pct"]),
                            float(member["roundtrip_spread_cost_bps"]),
                            float(member["spread_adjusted_hypothesis_return_pct"]),
                            member.get("max_reference_notional_share_pct"),1 if is_rep else 0,
                            0 if is_rep else 1,CLUSTER_POLICY,REPRESENTATIVE_POLICY,
                            stamp,FEATURE_VERSION,SCHEMA_VERSION,
                        ),
                    )

                event_row = {
                    "mean_adjusted": mean_adjusted,
                    "cross_exchange": cross_exchange,
                    "member_count": len(members),
                    "representative_count": len(representative_rows),
                }
                group_event_rows[key].append(event_row)
                total_events += 1
                total_representatives += len(representative_rows)
                total_suppressed += len(members) - len(representative_rows)
                total_cross_exchange += 1 if cross_exchange else 0

            event_rows = group_event_rows[key]
            event_count = len(event_rows)
            representative_count = sum(int(row["representative_count"]) for row in event_rows)
            suppressed_count = len(group_rows) - representative_count
            adjusted = [
                float(row["mean_adjusted"])
                for row in event_rows
                if row.get("mean_adjusted") is not None
            ]
            cross_count = sum(1 for row in event_rows if row["cross_exchange"])
            self.conn.execute(
                """INSERT INTO research_market_flow_event_cluster_stats_mx(
                       market,regime_label,horizon_label,source_member_count,event_count,
                       venue_representative_count,suppressed_overlap_member_count,
                       event_count_reduction_pct,member_suppression_pct,
                       cross_exchange_event_count,cross_exchange_event_share_pct,
                       mean_event_spread_adjusted_return_pct,event_spread_adjusted_hit_rate_pct,
                       received_at,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    market,regime,horizon,len(group_rows),event_count,representative_count,
                    suppressed_count,
                    (1.0 - event_count / len(group_rows)) * 100.0 if group_rows else 0.0,
                    suppressed_count / len(group_rows) * 100.0 if group_rows else 0.0,
                    cross_count,cross_count / event_count * 100.0 if event_count else 0.0,
                    statistics.fmean(adjusted) if adjusted else None,
                    sum(1 for value in adjusted if value > 0) / len(adjusted) * 100.0 if adjusted else None,
                    stamp,FEATURE_VERSION,SCHEMA_VERSION,
                ),
            )

        self.conn.commit()
        return {
            "ok": True,
            "status": "computed" if rows else "waiting_for_spread_ready_cost_edge_rows",
            "source_spread_ready_members": len(rows),
            "events_written": total_events,
            "venue_representatives": total_representatives,
            "suppressed_overlap_members": total_suppressed,
            "cross_exchange_events": total_cross_exchange,
            "event_count_reduction_pct": (
                (1.0 - total_events / len(rows)) * 100.0 if rows else 0.0
            ),
            "cluster_contract": {
                "policy": CLUSTER_POLICY,
                "representative_policy": REPRESENTATIVE_POLICY,
                "anchor_end_never_extended": True,
                "same_market_regime_horizon_only": True,
                "boundary_signal_starts_new_event": True,
                "one_representative_per_exchange_per_event": True,
                "representative_selection_uses_performance": False,
                "event_return_equal_weights_exchange_representatives": True,
                "statistical_independence_claim": False,
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
        required_tables = {
            "research_market_flow_event_cluster_mx",
            "research_market_flow_event_cluster_member_mx",
            "research_market_flow_event_cluster_stats_mx",
        }
        if not required_tables.issubset(tables):
            return {
                "ok": True,"status": "waiting_for_tables","tables_ready": False,
                "event_count": 0,"member_count": 0,"paper_only": True,
                "shadow_only": True,"score_wired": False,"can_place_orders": False,
            }

        events = [dict(row) for row in self.conn.execute(
            "SELECT * FROM research_market_flow_event_cluster_mx ORDER BY market,regime_label,horizon_label,event_anchor_signal_ts"
        ).fetchall()]
        members = [dict(row) for row in self.conn.execute(
            "SELECT * FROM research_market_flow_event_cluster_member_mx ORDER BY event_id,exchange,signal_feature_ts,signal_window_label"
        ).fetchall()]
        stats = [dict(row) for row in self.conn.execute(
            "SELECT * FROM research_market_flow_event_cluster_stats_mx ORDER BY source_member_count DESC,market,regime_label,horizon_label"
        ).fetchall()]

        event_by_id = {str(row["event_id"]): row for row in events}
        members_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in members:
            members_by_event[str(row["event_id"])].append(row)

        membership_violations = 0
        representative_violations = 0
        representative_selection_violations = 0
        event_mean_violations = 0
        cross_exchange_violations = 0
        for event_id, event_members in members_by_event.items():
            event = event_by_id.get(event_id)
            if event is None:
                membership_violations += len(event_members)
                continue
            anchor_start = float(event["event_anchor_signal_ts"])
            anchor_end = float(event["event_anchor_end_ts"])
            membership_violations += sum(
                1 for member in event_members
                if float(member["signal_feature_ts"]) < anchor_start
                or float(member["signal_feature_ts"]) >= anchor_end
            )
            by_exchange: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for member in event_members:
                by_exchange[str(member["exchange"])].append(member)
            reps: list[dict[str, Any]] = []
            for exchange_rows in by_exchange.values():
                actual = [row for row in exchange_rows if int(row["representative_for_exchange"]) == 1]
                if len(actual) != 1:
                    representative_violations += 1
                    continue
                expected = min(exchange_rows, key=self._representative_key)
                representative_selection_violations += 0 if actual[0] is expected else 1
                reps.append(actual[0])
            if reps:
                expected_mean = statistics.fmean(float(row["spread_adjusted_hypothesis_return_pct"]) for row in reps)
                actual_mean = event.get("mean_spread_adjusted_hypothesis_return_pct")
                if actual_mean is None or abs(float(actual_mean) - expected_mean) > 0.000001:
                    event_mean_violations += 1
            expected_cross = all(exchange in by_exchange for exchange in EXPECTED_EXCHANGES)
            if int(event["cross_exchange_confirmed"]) != (1 if expected_cross else 0):
                cross_exchange_violations += 1

        fixed_anchor_overlap_violations = 0
        events_by_group: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            events_by_group[(str(event["market"]),str(event["regime_label"]),str(event["horizon_label"]))].append(event)
        for group_events in events_by_group.values():
            ordered = sorted(group_events,key=lambda row: float(row["event_anchor_signal_ts"]))
            for previous, current in zip(ordered, ordered[1:]):
                if float(current["event_anchor_signal_ts"]) < float(previous["event_anchor_end_ts"]):
                    fixed_anchor_overlap_violations += 1

        stats_violations = 0
        for row in stats:
            source_count = int(row["source_member_count"])
            event_count = int(row["event_count"])
            rep_count = int(row["venue_representative_count"])
            suppressed = int(row["suppressed_overlap_member_count"])
            if source_count < event_count or source_count < rep_count or suppressed != source_count - rep_count:
                stats_violations += 1

        columns = {
            str(row[1])
            for row in self.conn.execute("PRAGMA table_info(research_market_flow_event_cluster_mx)").fetchall()
        }
        suspicious_columns = sorted(
            column for column in columns
            if "trade_intent" in column.lower() or "order_qty" in column.lower()
            or "position_size" in column.lower() or "score" in column.lower()
        )
        event_count = len(events)
        member_count = len(members)
        representative_count = sum(int(row["representative_for_exchange"]) for row in members)
        suppressed_count = sum(int(row["suppressed_overlap_member"]) for row in members)
        cross_exchange_count = sum(int(row["cross_exchange_confirmed"]) for row in events)
        violations = (
            membership_violations + representative_violations + representative_selection_violations
            + event_mean_violations + cross_exchange_violations + fixed_anchor_overlap_violations
            + stats_violations + len(suspicious_columns)
        )
        return {
            "ok": violations == 0,
            "status": "ready" if events else "waiting_for_cluster_rows",
            "tables_ready": True,
            "event_count": event_count,
            "member_count": member_count,
            "venue_representative_count": representative_count,
            "suppressed_overlap_member_count": suppressed_count,
            "cross_exchange_event_count": cross_exchange_count,
            "event_count_reduction_pct": (
                (1.0 - event_count / member_count) * 100.0 if member_count else 0.0
            ),
            "membership_contract_violations": membership_violations,
            "representative_contract_violations": representative_violations,
            "representative_selection_violations": representative_selection_violations,
            "event_mean_contract_violations": event_mean_violations,
            "cross_exchange_contract_violations": cross_exchange_violations,
            "fixed_anchor_overlap_violations": fixed_anchor_overlap_violations,
            "stats_contract_violations": stats_violations,
            "suspicious_wiring_columns": suspicious_columns,
            "stats": stats,
            "sample_events": list(reversed(events[-12:])),
            "cluster_policy": CLUSTER_POLICY,
            "representative_policy": REPRESENTATIVE_POLICY,
            "interpretation": "overlap_clustered_independentish_research_events_not_independence_claim_not_trading_score",
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
            "raw_cloud_projection": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
