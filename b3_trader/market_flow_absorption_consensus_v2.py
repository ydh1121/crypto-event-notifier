from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 1
FEATURE_VERSION = 2
CONSENSUS_WINDOW_LABEL = "5m"
IDENTITY_BASIS = "symbol+official_name_exact"
REQUIRED_EXCHANGES = ("bithumb", "upbit")
EVIDENCE_DIRECTIONS = {
    "passive_buy_absorption_candidate": 1,
    "passive_sell_absorption_candidate": -1,
}


class MarketFlowAbsorptionConsensusV2Store:
    """Forward-only cross-exchange consensus layer over frozen v1 absorption evidence.

    This layer does not retune the v1 heuristic. It only records a new v2
    observation when Bithumb and Upbit independently emit the same 5m v1
    absorption label for the same market and exact feature timestamp, and the
    existing cross-exchange market identity layer verifies the pair.

    The first compute call fixes an activation timestamp. v1 evidence whose
    feature/received timestamp predates that activation can never be promoted
    into this v2 table. Existing rows are append-only and never performance-
    selected, rewritten, or projected into PAPER/score/order paths.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_absorption_consensus_v2_control_mx(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                activation_ts REAL NOT NULL,
                last_checked_at REAL NOT NULL,
                source_window_label TEXT NOT NULL DEFAULT '5m',
                required_exchanges TEXT NOT NULL DEFAULT 'bithumb+upbit',
                historical_backfill INTEGER NOT NULL DEFAULT 0,
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 2,
                schema_version INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS research_market_flow_absorption_consensus_v2_mx(
                market TEXT NOT NULL,
                feature_ts REAL NOT NULL,
                window_label TEXT NOT NULL,
                evidence_label TEXT NOT NULL,
                hypothesis_direction INTEGER NOT NULL,
                bithumb_delta_pct REAL NOT NULL,
                upbit_delta_pct REAL NOT NULL,
                bithumb_price_return_bps REAL NOT NULL,
                upbit_price_return_bps REAL NOT NULL,
                bithumb_replenishment_ratio REAL NOT NULL,
                upbit_replenishment_ratio REAL NOT NULL,
                bithumb_same_best_pairs INTEGER NOT NULL,
                upbit_same_best_pairs INTEGER NOT NULL,
                bithumb_received_at REAL NOT NULL,
                upbit_received_at REAL NOT NULL,
                identity_verified INTEGER NOT NULL DEFAULT 1,
                identity_basis TEXT NOT NULL,
                identity_received_at REAL NOT NULL,
                activation_ts REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'exact_5m_bithumb+upbit_v1_absorption_consensus',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 2,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(market,feature_ts)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_absorption_consensus_v2_time
            ON research_market_flow_absorption_consensus_v2_mx(feature_ts DESC,market);
            CREATE INDEX IF NOT EXISTS idx_market_flow_absorption_consensus_v2_label
            ON research_market_flow_absorption_consensus_v2_mx(evidence_label,feature_ts DESC);
            """
        )
        self.conn.commit()

    def _activation(self, stamp: float) -> float:
        row = self.conn.execute(
            "SELECT activation_ts FROM research_market_flow_absorption_consensus_v2_control_mx WHERE singleton=1"
        ).fetchone()
        if row:
            return float(row["activation_ts"])

        existing = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_mx"
            ).fetchone()[0]
        )
        if existing:
            raise RuntimeError("consensus_v2_rows_exist_without_activation_control")

        self.conn.execute(
            """INSERT INTO research_market_flow_absorption_consensus_v2_control_mx(
                   singleton,activation_ts,last_checked_at,source_window_label,
                   required_exchanges,historical_backfill,received_at,feature_version,schema_version
               ) VALUES(1,?,?,?,'bithumb+upbit',0,?,?,?)""",
            (stamp, stamp, CONSENSUS_WINDOW_LABEL, stamp, FEATURE_VERSION, SCHEMA_VERSION),
        )
        self.conn.commit()
        return stamp

    def _source_tables_present(self) -> bool:
        names = {
            str(row[0])
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        return {
            "research_market_price_flow_divergence_mx",
            "research_market_cross_exchange_gap_mx",
        }.issubset(names)

    def _eligible_pairs(self, activation_ts: float) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT
                   b.market,
                   b.feature_ts,
                   b.evidence_label,
                   b.delta_pct AS bithumb_delta_pct,
                   u.delta_pct AS upbit_delta_pct,
                   b.price_return_bps AS bithumb_price_return_bps,
                   u.price_return_bps AS upbit_price_return_bps,
                   CASE
                       WHEN b.evidence_label='passive_buy_absorption_candidate'
                       THEN b.bid_replenishment_ratio
                       ELSE b.ask_replenishment_ratio
                   END AS bithumb_replenishment_ratio,
                   CASE
                       WHEN u.evidence_label='passive_buy_absorption_candidate'
                       THEN u.bid_replenishment_ratio
                       ELSE u.ask_replenishment_ratio
                   END AS upbit_replenishment_ratio,
                   CASE
                       WHEN b.evidence_label='passive_buy_absorption_candidate'
                       THEN b.bid_same_best_pairs
                       ELSE b.ask_same_best_pairs
                   END AS bithumb_same_best_pairs,
                   CASE
                       WHEN u.evidence_label='passive_buy_absorption_candidate'
                       THEN u.bid_same_best_pairs
                       ELSE u.ask_same_best_pairs
                   END AS upbit_same_best_pairs,
                   b.received_at AS bithumb_received_at,
                   u.received_at AS upbit_received_at,
                   g.identity_basis,
                   g.received_at AS identity_received_at
               FROM research_market_price_flow_divergence_mx b
               JOIN research_market_price_flow_divergence_mx u
                 ON u.exchange='upbit'
                AND u.market=b.market
                AND u.window_label=b.window_label
                AND u.feature_ts=b.feature_ts
               JOIN research_market_cross_exchange_gap_mx g
                 ON g.market=b.market
                AND g.bithumb_market=b.market
                AND g.upbit_market=u.market
               WHERE b.exchange='bithumb'
                 AND b.window_label=?
                 AND b.data_ready=1
                 AND u.data_ready=1
                 AND b.evidence_label=u.evidence_label
                 AND b.evidence_label IN (
                     'passive_buy_absorption_candidate',
                     'passive_sell_absorption_candidate'
                 )
                 AND b.feature_ts>=?
                 AND u.feature_ts>=?
                 AND b.received_at>=?
                 AND u.received_at>=?
                 AND g.identity_verified=1
                 AND g.identity_basis=?
               ORDER BY b.feature_ts ASC,b.market ASC""",
            (
                CONSENSUS_WINDOW_LABEL,
                activation_ts,
                activation_ts,
                activation_ts,
                activation_ts,
                IDENTITY_BASIS,
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(time.time() if now is None else now)
        activation_ts = self._activation(stamp)
        source_present = self._source_tables_present()
        eligible_pairs = self._eligible_pairs(activation_ts) if source_present else []
        rows_written = 0

        for row in eligible_pairs:
            label = str(row["evidence_label"])
            direction = int(EVIDENCE_DIRECTIONS[label])
            values = (
                str(row["market"]),
                float(row["feature_ts"]),
                CONSENSUS_WINDOW_LABEL,
                label,
                direction,
                float(row["bithumb_delta_pct"]),
                float(row["upbit_delta_pct"]),
                float(row["bithumb_price_return_bps"]),
                float(row["upbit_price_return_bps"]),
                float(row["bithumb_replenishment_ratio"]),
                float(row["upbit_replenishment_ratio"]),
                int(row["bithumb_same_best_pairs"]),
                int(row["upbit_same_best_pairs"]),
                float(row["bithumb_received_at"]),
                float(row["upbit_received_at"]),
                1,
                str(row["identity_basis"]),
                float(row["identity_received_at"]),
                activation_ts,
                stamp,
                FEATURE_VERSION,
                SCHEMA_VERSION,
            )
            cursor = self.conn.execute(
                """INSERT OR IGNORE INTO research_market_flow_absorption_consensus_v2_mx(
                       market,feature_ts,window_label,evidence_label,hypothesis_direction,
                       bithumb_delta_pct,upbit_delta_pct,bithumb_price_return_bps,upbit_price_return_bps,
                       bithumb_replenishment_ratio,upbit_replenishment_ratio,
                       bithumb_same_best_pairs,upbit_same_best_pairs,
                       bithumb_received_at,upbit_received_at,identity_verified,identity_basis,
                       identity_received_at,activation_ts,source,received_at,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                            'exact_5m_bithumb+upbit_v1_absorption_consensus',?,?,?)""",
                values,
            )
            rows_written += 1 if int(cursor.rowcount or 0) > 0 else 0

        self.conn.execute(
            """UPDATE research_market_flow_absorption_consensus_v2_control_mx
               SET last_checked_at=?,received_at=?,feature_version=?,schema_version=?
               WHERE singleton=1""",
            (stamp, stamp, FEATURE_VERSION, SCHEMA_VERSION),
        )
        self.conn.commit()
        total_rows = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_mx"
            ).fetchone()[0]
        )
        return {
            "ok": True,
            "status": (
                "computed"
                if source_present
                else "waiting_for_v1_divergence_and_identity_sources"
            ),
            "activation_ts": activation_ts,
            "last_checked_at": stamp,
            "source_tables_present": source_present,
            "eligible_exact_consensus_pairs": len(eligible_pairs),
            "rows_written": rows_written,
            "consensus_rows": total_rows,
            "window_label": CONSENSUS_WINDOW_LABEL,
            "required_exchanges": list(REQUIRED_EXCHANGES),
            "identity_basis": IDENTITY_BASIS,
            "historical_v1_backfill": False,
            "v1_threshold_retuning": False,
            "network_fetches": False,
            "raw_cloud_projection": False,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }

    def audit(self) -> dict[str, Any]:
        control = self.conn.execute(
            "SELECT * FROM research_market_flow_absorption_consensus_v2_control_mx WHERE singleton=1"
        ).fetchone()
        activation_ts = float(control["activation_ts"]) if control else None
        row_count = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_mx"
            ).fetchone()[0]
        )
        pre_activation = int(
            self.conn.execute(
                """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_mx
                   WHERE feature_ts<activation_ts
                      OR bithumb_received_at<activation_ts
                      OR upbit_received_at<activation_ts"""
            ).fetchone()[0]
        )
        non_5m = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_mx WHERE window_label<>?",
                (CONSENSUS_WINDOW_LABEL,),
            ).fetchone()[0]
        )
        invalid_label_or_direction = int(
            self.conn.execute(
                """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_mx
                   WHERE (evidence_label='passive_buy_absorption_candidate' AND hypothesis_direction<>1)
                      OR (evidence_label='passive_sell_absorption_candidate' AND hypothesis_direction<>-1)
                      OR evidence_label NOT IN (
                          'passive_buy_absorption_candidate',
                          'passive_sell_absorption_candidate'
                      )"""
            ).fetchone()[0]
        )
        identity_violations = int(
            self.conn.execute(
                """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_mx
                   WHERE identity_verified<>1 OR identity_basis<>?""",
                (IDENTITY_BASIS,),
            ).fetchone()[0]
        )
        activation_mismatch = int(
            self.conn.execute(
                """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_mx
                   WHERE activation_ts<>?""",
                (activation_ts if activation_ts is not None else -1.0,),
            ).fetchone()[0]
        ) if row_count else 0
        historical_backfill = bool(control["historical_backfill"]) if control else False
        checks_clean = bool(
            control
            and not historical_backfill
            and pre_activation == 0
            and non_5m == 0
            and invalid_label_or_direction == 0
            and identity_violations == 0
            and activation_mismatch == 0
        )
        return {
            "ok": checks_clean,
            "activation_present": control is not None,
            "activation_ts": activation_ts,
            "last_checked_at": float(control["last_checked_at"]) if control else None,
            "row_count": row_count,
            "pre_activation_rows": pre_activation,
            "non_5m_rows": non_5m,
            "invalid_label_or_direction_rows": invalid_label_or_direction,
            "identity_violation_rows": identity_violations,
            "activation_mismatch_rows": activation_mismatch,
            "historical_v1_backfill": historical_backfill,
            "v1_threshold_retuning": False,
            "window_label": CONSENSUS_WINDOW_LABEL,
            "required_exchanges": list(REQUIRED_EXCHANGES),
            "identity_basis": IDENTITY_BASIS,
            "network_fetches": False,
            "raw_cloud_projection": False,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }
