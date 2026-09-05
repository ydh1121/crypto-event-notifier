from __future__ import annotations

import math
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .market_fee_schedule import MarketFeeScheduleStore
from .market_orderbook_ladder import MAX_PRIOR_AGE_SECONDS, MarketOrderbookLadderStore

SCHEMA_VERSION = 1
FEATURE_VERSION = 1
REFERENCE_NOTIONAL_KRW = 750_000.0
ENTRY_BOUNDARY_SECONDS = 5 * 60
SOURCE_RETENTION_BARS = 400
EXPECTED_EXCHANGES = ("bithumb", "upbit")
HORIZONS = {
    "15m": 15 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
    "1d": 24 * 60 * 60,
}
REACTION_SOURCE = {
    "15m": ("1m", 60),
    "1h": ("1m", 60),
    "4h": ("1m", 60),
    "1d": ("5m", 5 * 60),
}
OBSERVATION_MIN_EVENTS = 30
OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS = 20
PROMOTION_MIN_EVENTS = 60
PROMOTION_MIN_CROSS_EXCHANGE_EVENTS = 40
PROMOTION_EVENT_WILSON_LOWER_PCT = 50.0
PROMOTION_CROSS_POSITIVE_WILSON_LOWER_PCT = 50.0


def _strict_next_boundary(ts: float, seconds: int = ENTRY_BOUNDARY_SECONDS) -> float:
    return float((math.floor(float(ts) / float(seconds)) + 1) * int(seconds))


def _regime_label(evidence_label: str) -> str:
    if evidence_label == "passive_buy_absorption_candidate":
        return "accumulation_candidate"
    if evidence_label == "passive_sell_absorption_candidate":
        return "distribution_candidate"
    return "unsupported"


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


class MarketFlowAbsorptionConsensusV2ForwardStore:
    """Forward-only causal performance validation for absorption consensus v2.

    This store has its own activation boundary. Consensus observations recorded
    before that boundary are never registered as performance samples.

    For each eligible consensus the simulated decision entry is the *strictly
    next* 5-minute boundary after the consensus row was recorded. This avoids
    using price action from before the cross-exchange agreement was knowable.
    Exact completed OHLCV is then required for 15m/1h/4h/1d outcomes.

    Full transaction cost is evaluated independently for Bithumb and Upbit at
    the PAPER reference notional of 750,000 KRW using versioned taker fees and
    prior-only top-5 ladder snapshots. Event selection is chronological and
    outcome-blind: overlapping events in the same market/direction/horizon are
    suppressed earliest-first before reliability is calculated.

    Nothing here is a probability, trading score, PAPER decision, position
    sizing rule, strategy mutation, or order path.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_absorption_consensus_v2_forward_control_mx(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                activation_ts REAL NOT NULL,
                last_checked_at REAL NOT NULL,
                reference_notional_krw REAL NOT NULL,
                entry_boundary_seconds INTEGER NOT NULL,
                historical_consensus_backfill INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'absorption_consensus_v2_forward_activation',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS research_market_flow_absorption_consensus_v2_reaction_mx(
                market TEXT NOT NULL,
                consensus_feature_ts REAL NOT NULL,
                consensus_received_at REAL NOT NULL,
                evidence_label TEXT NOT NULL,
                hypothesis_direction INTEGER NOT NULL,
                exchange TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                horizon_seconds REAL NOT NULL,
                forward_activation_ts REAL NOT NULL,
                entry_ts REAL NOT NULL,
                reaction_end_ts REAL NOT NULL,
                reaction_source_timeframe TEXT NOT NULL,
                reaction_source_interval_seconds REAL NOT NULL,
                data_ready INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                entry_candle_ts REAL,
                entry_price REAL,
                endpoint_candle_ts REAL,
                endpoint_price REAL,
                gross_hypothesis_return_pct REAL,
                source TEXT NOT NULL DEFAULT 'absorption_consensus_v2+exact_forward_ohlcv',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(market,consensus_feature_ts,exchange,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_absorption_consensus_v2_reaction_ready
            ON research_market_flow_absorption_consensus_v2_reaction_mx(
                data_ready,horizon_label,consensus_feature_ts DESC
            );

            CREATE TABLE IF NOT EXISTS research_market_flow_absorption_consensus_v2_full_cost_mx(
                market TEXT NOT NULL,
                consensus_feature_ts REAL NOT NULL,
                consensus_received_at REAL NOT NULL,
                evidence_label TEXT NOT NULL,
                hypothesis_direction INTEGER NOT NULL,
                exchange TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                entry_ts REAL NOT NULL,
                reaction_end_ts REAL NOT NULL,
                gross_hypothesis_return_pct REAL NOT NULL,
                reference_notional_krw REAL NOT NULL,
                entry_ladder_source_ts REAL,
                exit_ladder_source_ts REAL,
                entry_spread_bps REAL,
                exit_spread_bps REAL,
                roundtrip_spread_cost_bps REAL,
                entry_slippage_bps REAL,
                exit_slippage_bps REAL,
                entry_taker_fee_bps REAL,
                exit_taker_fee_bps REAL,
                fee_profile TEXT,
                fee_profile_source TEXT,
                total_transaction_cost_bps REAL,
                full_cost_adjusted_return_pct REAL,
                full_cost_ready INTEGER NOT NULL DEFAULT 0,
                cost_status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'absorption_consensus_v2_reaction+prior_top5+versioned_fee',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(market,consensus_feature_ts,exchange,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_absorption_consensus_v2_full_cost_ready
            ON research_market_flow_absorption_consensus_v2_full_cost_mx(
                full_cost_ready,horizon_label,consensus_feature_ts DESC
            );

            CREATE TABLE IF NOT EXISTS research_market_flow_absorption_consensus_v2_event_mx(
                event_id TEXT PRIMARY KEY,
                market TEXT NOT NULL,
                consensus_feature_ts REAL NOT NULL,
                consensus_received_at REAL NOT NULL,
                evidence_label TEXT NOT NULL,
                regime_label TEXT NOT NULL,
                hypothesis_direction INTEGER NOT NULL,
                horizon_label TEXT NOT NULL,
                entry_ts REAL NOT NULL,
                reaction_end_ts REAL NOT NULL,
                suppressed_overlap INTEGER NOT NULL DEFAULT 0,
                cross_exchange_full_cost_ready INTEGER NOT NULL DEFAULT 0,
                mean_gross_hypothesis_return_pct REAL,
                mean_total_transaction_cost_bps REAL,
                mean_full_cost_adjusted_return_pct REAL,
                positive_event INTEGER,
                both_exchange_positive INTEGER,
                cross_exchange_sign_agreement INTEGER,
                source TEXT NOT NULL DEFAULT 'absorption_consensus_v2_full_cost_pair',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_absorption_consensus_v2_event_ready
            ON research_market_flow_absorption_consensus_v2_event_mx(
                suppressed_overlap,cross_exchange_full_cost_ready,horizon_label,consensus_feature_ts
            );

            CREATE TABLE IF NOT EXISTS research_market_flow_absorption_consensus_v2_reliability_mx(
                market TEXT NOT NULL,
                regime_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                event_count INTEGER NOT NULL DEFAULT 0,
                positive_event_count INTEGER NOT NULL DEFAULT 0,
                mean_event_full_cost_adjusted_return_pct REAL,
                event_hit_rate_pct REAL,
                event_wilson_lower_pct REAL,
                cross_exchange_event_count INTEGER NOT NULL DEFAULT 0,
                cross_exchange_positive_agreement_count INTEGER NOT NULL DEFAULT 0,
                cross_exchange_sign_agreement_count INTEGER NOT NULL DEFAULT 0,
                mean_cross_exchange_event_return_pct REAL,
                cross_exchange_positive_agreement_rate_pct REAL,
                cross_exchange_positive_wilson_lower_pct REAL,
                cross_exchange_sign_agreement_rate_pct REAL,
                observation_ready INTEGER NOT NULL DEFAULT 0,
                direction_consistent INTEGER NOT NULL DEFAULT 0,
                promotion_ready INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'absorption_consensus_v2_event',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(market,regime_label,horizon_label)
            );
            """
        )
        self.conn.commit()

    def _activation(self, stamp: float) -> float:
        row = self.conn.execute(
            """SELECT activation_ts
               FROM research_market_flow_absorption_consensus_v2_forward_control_mx
               WHERE singleton=1"""
        ).fetchone()
        if row:
            return float(row["activation_ts"])

        existing = sum(
            int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "research_market_flow_absorption_consensus_v2_reaction_mx",
                "research_market_flow_absorption_consensus_v2_full_cost_mx",
                "research_market_flow_absorption_consensus_v2_event_mx",
            )
        )
        if existing:
            raise RuntimeError("consensus_v2_forward_rows_exist_without_activation_control")

        self.conn.execute(
            """INSERT INTO research_market_flow_absorption_consensus_v2_forward_control_mx(
                   singleton,activation_ts,last_checked_at,reference_notional_krw,
                   entry_boundary_seconds,historical_consensus_backfill,
                   source,received_at,feature_version,schema_version
               ) VALUES(1,?,?,?,?,0,'absorption_consensus_v2_forward_activation',?,?,?)""",
            (
                stamp,
                stamp,
                REFERENCE_NOTIONAL_KRW,
                ENTRY_BOUNDARY_SECONDS,
                stamp,
                FEATURE_VERSION,
                SCHEMA_VERSION,
            ),
        )
        self.conn.commit()
        return stamp

    def _consensus_rows(self, activation_ts: float) -> list[dict[str, Any]]:
        exists = self.conn.execute(
            """SELECT 1 FROM sqlite_master
               WHERE type='table'
                 AND name='research_market_flow_absorption_consensus_v2_mx'"""
        ).fetchone()
        if not exists:
            return []
        rows = self.conn.execute(
            """SELECT market,feature_ts,evidence_label,hypothesis_direction,
                      activation_ts AS consensus_activation_ts,received_at
               FROM research_market_flow_absorption_consensus_v2_mx
               WHERE received_at>=?
               ORDER BY received_at ASC,feature_ts ASC,market ASC""",
            (float(activation_ts),),
        ).fetchall()
        return [dict(row) for row in rows]

    def _register_reactions(
        self,
        consensus_rows: list[dict[str, Any]],
        activation_ts: float,
        stamp: float,
    ) -> int:
        written = 0
        for consensus in consensus_rows:
            consensus_received_at = float(consensus["received_at"])
            entry_ts = _strict_next_boundary(consensus_received_at)
            for exchange in EXPECTED_EXCHANGES:
                for horizon_label, horizon_seconds in HORIZONS.items():
                    timeframe, interval = REACTION_SOURCE[horizon_label]
                    end_ts = entry_ts + float(horizon_seconds)
                    cursor = self.conn.execute(
                        """INSERT OR IGNORE INTO
                           research_market_flow_absorption_consensus_v2_reaction_mx(
                               market,consensus_feature_ts,consensus_received_at,evidence_label,
                               hypothesis_direction,exchange,horizon_label,horizon_seconds,
                               forward_activation_ts,entry_ts,reaction_end_ts,
                               reaction_source_timeframe,reaction_source_interval_seconds,
                               data_ready,status,source,received_at,feature_version,schema_version
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0,'waiting_horizon',
                                    'absorption_consensus_v2+exact_forward_ohlcv',?,?,?)""",
                        (
                            str(consensus["market"]),
                            float(consensus["feature_ts"]),
                            consensus_received_at,
                            str(consensus["evidence_label"]),
                            int(consensus["hypothesis_direction"]),
                            exchange,
                            horizon_label,
                            float(horizon_seconds),
                            float(activation_ts),
                            entry_ts,
                            end_ts,
                            timeframe,
                            float(interval),
                            stamp,
                            FEATURE_VERSION,
                            SCHEMA_VERSION,
                        ),
                    )
                    written += 1 if int(cursor.rowcount or 0) > 0 else 0
        self.conn.commit()
        return written

    def _evaluate_reactions(self, stamp: float) -> tuple[int, Counter[str]]:
        rows = self.conn.execute(
            """SELECT * FROM research_market_flow_absorption_consensus_v2_reaction_mx
               WHERE data_ready=0
                 AND status NOT IN ('expired_missing_exact_reaction_path')
               ORDER BY reaction_end_ts ASC,consensus_feature_ts ASC,exchange ASC"""
        ).fetchall()
        ready_written = 0
        status_counts: Counter[str] = Counter()
        for row in rows:
            entry_ts = float(row["entry_ts"])
            end_ts = float(row["reaction_end_ts"])
            interval = int(float(row["reaction_source_interval_seconds"]))
            timeframe = str(row["reaction_source_timeframe"])
            if stamp < end_ts:
                status_counts["waiting_horizon"] += 1
                continue

            expected = int(round((end_ts - entry_ts) / interval))
            candles = self.conn.execute(
                """SELECT candle_ts,open,close,is_closed
                   FROM research_market_ohlcv_mx
                   WHERE exchange=? AND market=? AND timeframe=?
                     AND candle_ts>=? AND candle_ts<? AND is_closed=1
                   ORDER BY candle_ts ASC""",
                (
                    str(row["exchange"]),
                    str(row["market"]),
                    timeframe,
                    entry_ts,
                    end_ts,
                ),
            ).fetchall()
            expected_ts = [entry_ts + offset * interval for offset in range(expected)]
            actual_ts = [float(candle["candle_ts"]) for candle in candles]
            if len(candles) != expected or actual_ts != expected_ts:
                retention_span = SOURCE_RETENTION_BARS * interval
                status = (
                    "expired_missing_exact_reaction_path"
                    if stamp - entry_ts > retention_span
                    else "waiting_exact_closed_reaction_path"
                )
                self.conn.execute(
                    """UPDATE research_market_flow_absorption_consensus_v2_reaction_mx
                       SET status=?,received_at=?,feature_version=?,schema_version=?
                       WHERE market=? AND consensus_feature_ts=? AND exchange=? AND horizon_label=?""",
                    (
                        status,
                        stamp,
                        FEATURE_VERSION,
                        SCHEMA_VERSION,
                        str(row["market"]),
                        float(row["consensus_feature_ts"]),
                        str(row["exchange"]),
                        str(row["horizon_label"]),
                    ),
                )
                status_counts[status] += 1
                continue

            entry_price = float(candles[0]["open"])
            endpoint_price = float(candles[-1]["close"])
            if entry_price <= 0 or endpoint_price <= 0:
                status = "invalid_reaction_price"
                self.conn.execute(
                    """UPDATE research_market_flow_absorption_consensus_v2_reaction_mx
                       SET status=?,received_at=?
                       WHERE market=? AND consensus_feature_ts=? AND exchange=? AND horizon_label=?""",
                    (
                        status,
                        stamp,
                        str(row["market"]),
                        float(row["consensus_feature_ts"]),
                        str(row["exchange"]),
                        str(row["horizon_label"]),
                    ),
                )
                status_counts[status] += 1
                continue

            raw_return_pct = (endpoint_price / entry_price - 1.0) * 100.0
            gross = raw_return_pct * int(row["hypothesis_direction"])
            self.conn.execute(
                """UPDATE research_market_flow_absorption_consensus_v2_reaction_mx
                   SET data_ready=1,status='ready',
                       entry_candle_ts=?,entry_price=?,
                       endpoint_candle_ts=?,endpoint_price=?,
                       gross_hypothesis_return_pct=?,received_at=?,
                       feature_version=?,schema_version=?
                   WHERE market=? AND consensus_feature_ts=? AND exchange=? AND horizon_label=?""",
                (
                    float(candles[0]["candle_ts"]),
                    entry_price,
                    float(candles[-1]["candle_ts"]),
                    endpoint_price,
                    gross,
                    stamp,
                    FEATURE_VERSION,
                    SCHEMA_VERSION,
                    str(row["market"]),
                    float(row["consensus_feature_ts"]),
                    str(row["exchange"]),
                    str(row["horizon_label"]),
                ),
            )
            ready_written += 1
            status_counts["ready"] += 1
        self.conn.commit()
        return ready_written, status_counts

    @staticmethod
    def _execution_estimate(
        ladder: MarketOrderbookLadderStore,
        snapshot: dict[str, Any],
        *,
        direction: int,
        entry: bool,
    ) -> dict[str, float] | None:
        if direction == 1:
            if entry:
                return ladder.estimate_buy(snapshot["ask_levels"], REFERENCE_NOTIONAL_KRW)
            return ladder.estimate_sell(snapshot["bid_levels"], REFERENCE_NOTIONAL_KRW)
        if direction == -1:
            if entry:
                return ladder.estimate_sell(snapshot["bid_levels"], REFERENCE_NOTIONAL_KRW)
            return ladder.estimate_buy(snapshot["ask_levels"], REFERENCE_NOTIONAL_KRW)
        return None

    def _compute_full_cost(self, stamp: float) -> tuple[int, Counter[str]]:
        reaction_rows = self.conn.execute(
            """SELECT * FROM research_market_flow_absorption_consensus_v2_reaction_mx
               WHERE data_ready=1 AND gross_hypothesis_return_pct IS NOT NULL
               ORDER BY consensus_feature_ts,horizon_label,exchange"""
        ).fetchall()
        fee_store = MarketFeeScheduleStore(self.path)
        ladder_store = MarketOrderbookLadderStore(self.path)
        ready_written = 0
        status_counts: Counter[str] = Counter()
        try:
            fee_store.ensure_current_catalog(now=stamp)
            for row in reaction_rows:
                exchange = str(row["exchange"])
                market = str(row["market"])
                entry_ts = float(row["entry_ts"])
                exit_ts = float(row["reaction_end_ts"])
                direction = int(row["hypothesis_direction"])
                gross = float(row["gross_hypothesis_return_pct"])

                entry_fee = fee_store.resolve_taker_fee(exchange, market, entry_ts)
                exit_fee = fee_store.resolve_taker_fee(exchange, market, exit_ts)
                cost_status = "full_cost_ready"
                entry_snapshot = None
                exit_snapshot = None
                entry_exec = None
                exit_exec = None

                if not entry_fee or not exit_fee:
                    cost_status = "waiting_versioned_fee_profile"
                elif str(entry_fee["profile"]) != str(exit_fee["profile"]):
                    cost_status = "waiting_consistent_fee_profile"
                else:
                    entry_snapshot = ladder_store.prior_snapshot(
                        exchange,
                        market,
                        entry_ts,
                        max_age_seconds=MAX_PRIOR_AGE_SECONDS,
                    )
                    exit_snapshot = ladder_store.prior_snapshot(
                        exchange,
                        market,
                        exit_ts,
                        max_age_seconds=MAX_PRIOR_AGE_SECONDS,
                    )
                    if entry_snapshot is None or exit_snapshot is None:
                        cost_status = "waiting_prior_only_ladder"
                    else:
                        entry_exec = self._execution_estimate(
                            ladder_store,
                            entry_snapshot,
                            direction=direction,
                            entry=True,
                        )
                        exit_exec = self._execution_estimate(
                            ladder_store,
                            exit_snapshot,
                            direction=direction,
                            entry=False,
                        )
                        if entry_exec is None or exit_exec is None:
                            cost_status = "waiting_top5_depth"

                ready = cost_status == "full_cost_ready"
                entry_spread = ladder_store.spread_bps(entry_snapshot) if entry_snapshot else None
                exit_spread = ladder_store.spread_bps(exit_snapshot) if exit_snapshot else None
                roundtrip_spread = (
                    (float(entry_spread) + float(exit_spread)) / 2.0
                    if entry_spread is not None and exit_spread is not None
                    else None
                )
                entry_fee_bps = float(entry_fee["taker_fee_bps"]) if entry_fee else None
                exit_fee_bps = float(exit_fee["taker_fee_bps"]) if exit_fee else None
                entry_slippage = float(entry_exec["slippage_bps"]) if entry_exec else None
                exit_slippage = float(exit_exec["slippage_bps"]) if exit_exec else None
                total_cost = (
                    float(roundtrip_spread)
                    + float(entry_slippage)
                    + float(exit_slippage)
                    + float(entry_fee_bps)
                    + float(exit_fee_bps)
                    if ready
                    and roundtrip_spread is not None
                    and entry_slippage is not None
                    and exit_slippage is not None
                    and entry_fee_bps is not None
                    and exit_fee_bps is not None
                    else None
                )
                net = gross - total_cost / 100.0 if total_cost is not None else None
                profile = str(entry_fee["profile"]) if entry_fee else None
                profile_source = str(entry_fee.get("profile_source") or "") if entry_fee else None

                self.conn.execute(
                    """INSERT INTO research_market_flow_absorption_consensus_v2_full_cost_mx(
                           market,consensus_feature_ts,consensus_received_at,evidence_label,
                           hypothesis_direction,exchange,horizon_label,entry_ts,reaction_end_ts,
                           gross_hypothesis_return_pct,reference_notional_krw,
                           entry_ladder_source_ts,exit_ladder_source_ts,
                           entry_spread_bps,exit_spread_bps,roundtrip_spread_cost_bps,
                           entry_slippage_bps,exit_slippage_bps,
                           entry_taker_fee_bps,exit_taker_fee_bps,
                           fee_profile,fee_profile_source,total_transaction_cost_bps,
                           full_cost_adjusted_return_pct,full_cost_ready,cost_status,
                           source,received_at,feature_version,schema_version
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                                'absorption_consensus_v2_reaction+prior_top5+versioned_fee',?,?,?)
                       ON CONFLICT(market,consensus_feature_ts,exchange,horizon_label) DO UPDATE SET
                           gross_hypothesis_return_pct=excluded.gross_hypothesis_return_pct,
                           reference_notional_krw=excluded.reference_notional_krw,
                           entry_ladder_source_ts=excluded.entry_ladder_source_ts,
                           exit_ladder_source_ts=excluded.exit_ladder_source_ts,
                           entry_spread_bps=excluded.entry_spread_bps,
                           exit_spread_bps=excluded.exit_spread_bps,
                           roundtrip_spread_cost_bps=excluded.roundtrip_spread_cost_bps,
                           entry_slippage_bps=excluded.entry_slippage_bps,
                           exit_slippage_bps=excluded.exit_slippage_bps,
                           entry_taker_fee_bps=excluded.entry_taker_fee_bps,
                           exit_taker_fee_bps=excluded.exit_taker_fee_bps,
                           fee_profile=excluded.fee_profile,
                           fee_profile_source=excluded.fee_profile_source,
                           total_transaction_cost_bps=excluded.total_transaction_cost_bps,
                           full_cost_adjusted_return_pct=excluded.full_cost_adjusted_return_pct,
                           full_cost_ready=excluded.full_cost_ready,
                           cost_status=excluded.cost_status,
                           received_at=excluded.received_at,
                           feature_version=excluded.feature_version,
                           schema_version=excluded.schema_version""",
                    (
                        market,
                        float(row["consensus_feature_ts"]),
                        float(row["consensus_received_at"]),
                        str(row["evidence_label"]),
                        direction,
                        exchange,
                        str(row["horizon_label"]),
                        entry_ts,
                        exit_ts,
                        gross,
                        REFERENCE_NOTIONAL_KRW,
                        float(entry_snapshot["source_ts"]) if entry_snapshot else None,
                        float(exit_snapshot["source_ts"]) if exit_snapshot else None,
                        entry_spread,
                        exit_spread,
                        roundtrip_spread,
                        entry_slippage,
                        exit_slippage,
                        entry_fee_bps,
                        exit_fee_bps,
                        profile,
                        profile_source,
                        total_cost,
                        net,
                        1 if ready else 0,
                        cost_status,
                        stamp,
                        FEATURE_VERSION,
                        SCHEMA_VERSION,
                    ),
                )
                status_counts[cost_status] += 1
                ready_written += 1 if ready else 0
            self.conn.commit()
        finally:
            ladder_store.close()
            fee_store.close()
        return ready_written, status_counts

    def _refresh_events(self, stamp: float) -> dict[str, int]:
        reaction_rows = self.conn.execute(
            """SELECT market,consensus_feature_ts,consensus_received_at,evidence_label,
                      hypothesis_direction,horizon_label,entry_ts,reaction_end_ts,exchange
               FROM research_market_flow_absorption_consensus_v2_reaction_mx
               ORDER BY market,evidence_label,horizon_label,entry_ts,exchange"""
        ).fetchall()
        by_event: dict[tuple[str, float, str, str], list[sqlite3.Row]] = defaultdict(list)
        for row in reaction_rows:
            key = (
                str(row["market"]),
                float(row["consensus_feature_ts"]),
                str(row["evidence_label"]),
                str(row["horizon_label"]),
            )
            by_event[key].append(row)

        grouped_keys: dict[tuple[str, str, str], list[tuple[str, float, str, str]]] = defaultdict(list)
        for key in by_event:
            grouped_keys[(key[0], key[2], key[3])].append(key)

        suppressed: set[tuple[str, float, str, str]] = set()
        for group_keys in grouped_keys.values():
            ordered = sorted(group_keys, key=lambda key: float(by_event[key][0]["entry_ts"]))
            last_accepted_end: float | None = None
            for key in ordered:
                entry_ts = float(by_event[key][0]["entry_ts"])
                end_ts = float(by_event[key][0]["reaction_end_ts"])
                if last_accepted_end is not None and entry_ts < last_accepted_end:
                    suppressed.add(key)
                    continue
                last_accepted_end = end_ts

        cost_rows = self.conn.execute(
            """SELECT market,consensus_feature_ts,evidence_label,horizon_label,exchange,
                      full_cost_ready,gross_hypothesis_return_pct,total_transaction_cost_bps,
                      full_cost_adjusted_return_pct
               FROM research_market_flow_absorption_consensus_v2_full_cost_mx"""
        ).fetchall()
        cost_by_key = {
            (
                str(row["market"]),
                float(row["consensus_feature_ts"]),
                str(row["evidence_label"]),
                str(row["horizon_label"]),
                str(row["exchange"]),
            ): row
            for row in cost_rows
        }

        self.conn.execute("DELETE FROM research_market_flow_absorption_consensus_v2_event_mx")
        ready_events = 0
        suppressed_events = 0
        for key, event_rows in by_event.items():
            market, feature_ts, evidence_label, horizon_label = key
            event_rows = sorted(event_rows, key=lambda row: str(row["exchange"]))
            suppressed_overlap = key in suppressed
            suppressed_events += 1 if suppressed_overlap else 0
            costs = {
                exchange: cost_by_key.get(
                    (market, feature_ts, evidence_label, horizon_label, exchange)
                )
                for exchange in EXPECTED_EXCHANGES
            }
            pair_ready = bool(
                all(costs[exchange] is not None for exchange in EXPECTED_EXCHANGES)
                and all(int(costs[exchange]["full_cost_ready"] or 0) == 1 for exchange in EXPECTED_EXCHANGES)
            )
            gross_values: list[float] = []
            cost_values: list[float] = []
            net_values: list[float] = []
            if pair_ready:
                gross_values = [
                    float(costs[exchange]["gross_hypothesis_return_pct"])
                    for exchange in EXPECTED_EXCHANGES
                ]
                cost_values = [
                    float(costs[exchange]["total_transaction_cost_bps"])
                    for exchange in EXPECTED_EXCHANGES
                ]
                net_values = [
                    float(costs[exchange]["full_cost_adjusted_return_pct"])
                    for exchange in EXPECTED_EXCHANGES
                ]
            mean_gross = statistics.fmean(gross_values) if gross_values else None
            mean_cost = statistics.fmean(cost_values) if cost_values else None
            mean_net = statistics.fmean(net_values) if net_values else None
            positive_event = 1 if mean_net is not None and mean_net > 0.0 else 0 if pair_ready else None
            both_positive = (
                1 if pair_ready and all(value > 0.0 for value in net_values) else 0 if pair_ready else None
            )
            sign_agreement = (
                1
                if pair_ready and ((net_values[0] > 0.0 and net_values[1] > 0.0)
                                   or (net_values[0] <= 0.0 and net_values[1] <= 0.0))
                else 0 if pair_ready else None
            )
            first = event_rows[0]
            event_id = f"{market}|{evidence_label}|{horizon_label}|v2|{feature_ts:.6f}"
            self.conn.execute(
                """INSERT INTO research_market_flow_absorption_consensus_v2_event_mx(
                       event_id,market,consensus_feature_ts,consensus_received_at,evidence_label,
                       regime_label,hypothesis_direction,horizon_label,entry_ts,reaction_end_ts,
                       suppressed_overlap,cross_exchange_full_cost_ready,
                       mean_gross_hypothesis_return_pct,mean_total_transaction_cost_bps,
                       mean_full_cost_adjusted_return_pct,positive_event,both_exchange_positive,
                       cross_exchange_sign_agreement,source,received_at,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                            'absorption_consensus_v2_full_cost_pair',?,?,?)""",
                (
                    event_id,
                    market,
                    feature_ts,
                    float(first["consensus_received_at"]),
                    evidence_label,
                    _regime_label(evidence_label),
                    int(first["hypothesis_direction"]),
                    horizon_label,
                    float(first["entry_ts"]),
                    float(first["reaction_end_ts"]),
                    1 if suppressed_overlap else 0,
                    1 if pair_ready else 0,
                    mean_gross,
                    mean_cost,
                    mean_net,
                    positive_event,
                    both_positive,
                    sign_agreement,
                    stamp,
                    FEATURE_VERSION,
                    SCHEMA_VERSION,
                ),
            )
            ready_events += 1 if pair_ready and not suppressed_overlap else 0
        self.conn.commit()
        return {
            "events_written": len(by_event),
            "ready_nonoverlap_events": ready_events,
            "suppressed_overlap_events": suppressed_events,
        }

    def _refresh_reliability(self, stamp: float) -> dict[str, Any]:
        rows = self.conn.execute(
            """SELECT *
               FROM research_market_flow_absorption_consensus_v2_event_mx
               WHERE suppressed_overlap=0
                 AND cross_exchange_full_cost_ready=1
                 AND mean_full_cost_adjusted_return_pct IS NOT NULL
               ORDER BY market,regime_label,horizon_label,entry_ts"""
        ).fetchall()
        grouped: dict[tuple[str, str, str], list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            grouped[(str(row["market"]), str(row["regime_label"]), str(row["horizon_label"]))].append(row)

        self.conn.execute("DELETE FROM research_market_flow_absorption_consensus_v2_reliability_mx")
        status_counts: Counter[str] = Counter()
        observation_ready_rows = 0
        promotion_ready_rows = 0
        for key, group in grouped.items():
            values = [float(row["mean_full_cost_adjusted_return_pct"]) for row in group]
            event_count = len(values)
            positive_events = sum(1 for value in values if value > 0.0)
            mean_return = statistics.fmean(values) if values else None
            hit_rate = positive_events / event_count * 100.0 if event_count else None
            event_wilson = _wilson_lower_pct(positive_events, event_count)
            cross_count = event_count
            cross_positive = sum(int(row["both_exchange_positive"] or 0) for row in group)
            cross_sign = sum(int(row["cross_exchange_sign_agreement"] or 0) for row in group)
            cross_positive_rate = cross_positive / cross_count * 100.0 if cross_count else None
            cross_positive_wilson = _wilson_lower_pct(cross_positive, cross_count)
            cross_sign_rate = cross_sign / cross_count * 100.0 if cross_count else None

            observation_ready = bool(
                event_count >= OBSERVATION_MIN_EVENTS
                and cross_count >= OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS
            )
            direction_consistent = bool(
                observation_ready
                and mean_return is not None and mean_return > 0.0
                and hit_rate is not None and hit_rate > 50.0
                and cross_positive_rate is not None and cross_positive_rate > 50.0
            )
            promotion_ready = bool(
                direction_consistent
                and event_count >= PROMOTION_MIN_EVENTS
                and cross_count >= PROMOTION_MIN_CROSS_EXCHANGE_EVENTS
                and event_wilson is not None
                and event_wilson > PROMOTION_EVENT_WILSON_LOWER_PCT
                and cross_positive_wilson is not None
                and cross_positive_wilson > PROMOTION_CROSS_POSITIVE_WILSON_LOWER_PCT
            )
            if promotion_ready:
                status = "validated_v2_full_cost_candidate"
            elif direction_consistent:
                status = "v2_full_cost_directional_watch"
            elif observation_ready:
                status = "mixed_v2_full_cost_edge"
            else:
                status = "collecting_v2_full_cost"

            self.conn.execute(
                """INSERT INTO research_market_flow_absorption_consensus_v2_reliability_mx(
                       market,regime_label,horizon_label,event_count,positive_event_count,
                       mean_event_full_cost_adjusted_return_pct,event_hit_rate_pct,event_wilson_lower_pct,
                       cross_exchange_event_count,cross_exchange_positive_agreement_count,
                       cross_exchange_sign_agreement_count,mean_cross_exchange_event_return_pct,
                       cross_exchange_positive_agreement_rate_pct,
                       cross_exchange_positive_wilson_lower_pct,
                       cross_exchange_sign_agreement_rate_pct,observation_ready,
                       direction_consistent,promotion_ready,status,source,received_at,
                       feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                            'absorption_consensus_v2_event',?,?,?)""",
                (
                    *key,
                    event_count,
                    positive_events,
                    mean_return,
                    hit_rate,
                    event_wilson,
                    cross_count,
                    cross_positive,
                    cross_sign,
                    mean_return,
                    cross_positive_rate,
                    cross_positive_wilson,
                    cross_sign_rate,
                    1 if observation_ready else 0,
                    1 if direction_consistent else 0,
                    1 if promotion_ready else 0,
                    status,
                    stamp,
                    FEATURE_VERSION,
                    SCHEMA_VERSION,
                ),
            )
            status_counts[status] += 1
            observation_ready_rows += 1 if observation_ready else 0
            promotion_ready_rows += 1 if promotion_ready else 0
        self.conn.commit()
        return {
            "groups_written": len(grouped),
            "source_ready_event_count": len(rows),
            "observation_ready_rows": observation_ready_rows,
            "promotion_ready_rows": promotion_ready_rows,
            "status_counts": dict(status_counts),
        }

    def compute(self, *, now: float | None = None) -> dict[str, Any]:
        stamp = float(time.time() if now is None else now)
        activation_ts = self._activation(stamp)
        source_rows = self._consensus_rows(activation_ts)
        registered = self._register_reactions(source_rows, activation_ts, stamp)
        reaction_ready_written, reaction_status_counts = self._evaluate_reactions(stamp)
        full_cost_ready_rows, full_cost_status_counts = self._compute_full_cost(stamp)
        event_result = self._refresh_events(stamp)
        reliability_result = self._refresh_reliability(stamp)
        self.conn.execute(
            """UPDATE research_market_flow_absorption_consensus_v2_forward_control_mx
               SET last_checked_at=?,received_at=?,feature_version=?,schema_version=?
               WHERE singleton=1""",
            (stamp, stamp, FEATURE_VERSION, SCHEMA_VERSION),
        )
        self.conn.commit()
        return {
            "ok": True,
            "status": "computed",
            "activation_ts": activation_ts,
            "last_checked_at": stamp,
            "eligible_post_activation_consensus_rows": len(source_rows),
            "reaction_rows_registered": registered,
            "reaction_ready_written": reaction_ready_written,
            "reaction_status_counts": dict(reaction_status_counts),
            "full_cost_ready_rows": full_cost_ready_rows,
            "full_cost_status_counts": dict(full_cost_status_counts),
            **event_result,
            "reliability": reliability_result,
            "reference_notional_krw": REFERENCE_NOTIONAL_KRW,
            "entry_policy": "strict_next_5m_boundary_after_consensus_recorded",
            "historical_consensus_backfill": False,
            "overlap_policy": "same_market+direction+horizon_earliest_nonoverlap_outcome_blind",
            "network_fetches": False,
            "raw_cloud_projection": False,
            "paper_only": True,
            "shadow_only": True,
            "probability_interpretation": False,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }

    def audit(self) -> dict[str, Any]:
        control = self.conn.execute(
            """SELECT * FROM research_market_flow_absorption_consensus_v2_forward_control_mx
               WHERE singleton=1"""
        ).fetchone()
        activation_ts = float(control["activation_ts"]) if control else None
        source_before_activation = 0
        source_after_activation = 0
        if activation_ts is not None and self.conn.execute(
            """SELECT 1 FROM sqlite_master
               WHERE type='table' AND name='research_market_flow_absorption_consensus_v2_mx'"""
        ).fetchone():
            source_before_activation = int(self.conn.execute(
                """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_mx
                   WHERE received_at<?""",
                (activation_ts,),
            ).fetchone()[0])
            source_after_activation = int(self.conn.execute(
                """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_mx
                   WHERE received_at>=?""",
                (activation_ts,),
            ).fetchone()[0])

        reaction_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_reaction_mx"
        ).fetchone()[0])
        ready_reactions = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_reaction_mx
               WHERE data_ready=1"""
        ).fetchone()[0])
        pre_activation_reactions = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_reaction_mx
               WHERE consensus_received_at<forward_activation_ts"""
        ).fetchone()[0])
        causal_entry_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_reaction_mx
               WHERE entry_ts<=consensus_received_at
                  OR entry_ts-consensus_received_at>?
                  OR ABS(entry_ts/CAST(? AS REAL)-ROUND(entry_ts/CAST(? AS REAL)))>0.000001""",
            (ENTRY_BOUNDARY_SECONDS, ENTRY_BOUNDARY_SECONDS, ENTRY_BOUNDARY_SECONDS),
        ).fetchone()[0])
        horizon_contract_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_reaction_mx
               WHERE (horizon_label='15m' AND
                         (horizon_seconds<>900 OR reaction_source_timeframe<>'1m'
                          OR reaction_source_interval_seconds<>60))
                  OR (horizon_label='1h' AND
                         (horizon_seconds<>3600 OR reaction_source_timeframe<>'1m'
                          OR reaction_source_interval_seconds<>60))
                  OR (horizon_label='4h' AND
                         (horizon_seconds<>14400 OR reaction_source_timeframe<>'1m'
                          OR reaction_source_interval_seconds<>60))
                  OR (horizon_label='1d' AND
                         (horizon_seconds<>86400 OR reaction_source_timeframe<>'5m'
                          OR reaction_source_interval_seconds<>300))
                  OR horizon_label NOT IN ('15m','1h','4h','1d')"""
        ).fetchone()[0])
        full_cost_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_full_cost_mx"
        ).fetchone()[0])
        full_cost_ready = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_full_cost_mx
               WHERE full_cost_ready=1"""
        ).fetchone()[0])
        notional_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_full_cost_mx
               WHERE ABS(reference_notional_krw-?)>0.000001""",
            (REFERENCE_NOTIONAL_KRW,),
        ).fetchone()[0])
        prior_ladder_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_full_cost_mx
               WHERE full_cost_ready=1 AND (
                    entry_ladder_source_ts IS NULL OR exit_ladder_source_ts IS NULL
                    OR entry_ladder_source_ts>=entry_ts
                    OR exit_ladder_source_ts>=reaction_end_ts
                    OR entry_ts-entry_ladder_source_ts>?
                    OR reaction_end_ts-exit_ladder_source_ts>?
               )""",
            (MAX_PRIOR_AGE_SECONDS, MAX_PRIOR_AGE_SECONDS),
        ).fetchone()[0])
        formula_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_full_cost_mx
               WHERE full_cost_ready=1 AND (
                   total_transaction_cost_bps IS NULL
                   OR full_cost_adjusted_return_pct IS NULL
                   OR ABS(
                       total_transaction_cost_bps - (
                           roundtrip_spread_cost_bps
                           + entry_slippage_bps + exit_slippage_bps
                           + entry_taker_fee_bps + exit_taker_fee_bps
                       )
                   )>0.000001
                   OR ABS(
                       full_cost_adjusted_return_pct
                       - (gross_hypothesis_return_pct-total_transaction_cost_bps/100.0)
                   )>0.000001
               )"""
        ).fetchone()[0])
        event_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_event_mx"
        ).fetchone()[0])
        ready_events = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_event_mx
               WHERE suppressed_overlap=0 AND cross_exchange_full_cost_ready=1"""
        ).fetchone()[0])
        suppressed_events = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_event_mx
               WHERE suppressed_overlap=1"""
        ).fetchone()[0])
        reliability_count = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_reliability_mx"
        ).fetchone()[0])
        promotion_ready = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_reliability_mx
               WHERE promotion_ready=1"""
        ).fetchone()[0])
        promotion_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_absorption_consensus_v2_reliability_mx
               WHERE promotion_ready=1 AND (
                   event_count<? OR cross_exchange_event_count<?
                   OR COALESCE(mean_event_full_cost_adjusted_return_pct,0)<=0
                   OR COALESCE(event_hit_rate_pct,0)<=50
                   OR COALESCE(event_wilson_lower_pct,0)<=?
                   OR COALESCE(cross_exchange_positive_agreement_rate_pct,0)<=50
                   OR COALESCE(cross_exchange_positive_wilson_lower_pct,0)<=?
                   OR observation_ready<>1 OR direction_consistent<>1
               )""",
            (
                PROMOTION_MIN_EVENTS,
                PROMOTION_MIN_CROSS_EXCHANGE_EVENTS,
                PROMOTION_EVENT_WILSON_LOWER_PCT,
                PROMOTION_CROSS_POSITIVE_WILSON_LOWER_PCT,
            ),
        ).fetchone()[0])

        suspicious: list[str] = []
        for table in (
            "research_market_flow_absorption_consensus_v2_reaction_mx",
            "research_market_flow_absorption_consensus_v2_full_cost_mx",
            "research_market_flow_absorption_consensus_v2_event_mx",
            "research_market_flow_absorption_consensus_v2_reliability_mx",
        ):
            columns = {str(row[1]) for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
            suspicious.extend(
                f"{table}.{column}"
                for column in columns
                if any(token in column.lower() for token in (
                    "trade_intent", "order_qty", "position_size", "strategy_action"
                ))
            )

        horizon_rows = {
            str(row["horizon_label"]): {
                "rows": int(row["rows"]),
                "ready": int(row["ready"]),
            }
            for row in self.conn.execute(
                """SELECT horizon_label,COUNT(*) AS rows,
                          SUM(CASE WHEN data_ready=1 THEN 1 ELSE 0 END) AS ready
                   FROM research_market_flow_absorption_consensus_v2_reaction_mx
                   GROUP BY horizon_label ORDER BY horizon_label"""
            ).fetchall()
        }
        full_cost_status_counts = {
            str(row["cost_status"]): int(row["rows"])
            for row in self.conn.execute(
                """SELECT cost_status,COUNT(*) AS rows
                   FROM research_market_flow_absorption_consensus_v2_full_cost_mx
                   GROUP BY cost_status ORDER BY cost_status"""
            ).fetchall()
        }

        clean = bool(
            control
            and int(control["historical_consensus_backfill"] or 0) == 0
            and abs(float(control["reference_notional_krw"]) - REFERENCE_NOTIONAL_KRW) <= 0.000001
            and int(control["entry_boundary_seconds"]) == ENTRY_BOUNDARY_SECONDS
            and pre_activation_reactions == 0
            and causal_entry_violations == 0
            and horizon_contract_violations == 0
            and notional_violations == 0
            and prior_ladder_violations == 0
            and formula_violations == 0
            and promotion_violations == 0
            and not suspicious
        )
        return {
            "ok": clean,
            "activation_present": control is not None,
            "activation_ts": activation_ts,
            "last_checked_at": float(control["last_checked_at"]) if control else None,
            "consensus_source_rows_before_forward_activation": source_before_activation,
            "consensus_source_rows_after_forward_activation": source_after_activation,
            "reaction_rows": reaction_count,
            "reaction_ready_rows": ready_reactions,
            "reaction_rows_by_horizon": horizon_rows,
            "pre_forward_activation_reaction_rows": pre_activation_reactions,
            "causal_entry_boundary_violations": causal_entry_violations,
            "horizon_contract_violations": horizon_contract_violations,
            "full_cost_rows": full_cost_count,
            "full_cost_ready_rows": full_cost_ready,
            "full_cost_status_counts": full_cost_status_counts,
            "reference_notional_krw": REFERENCE_NOTIONAL_KRW,
            "reference_notional_violations": notional_violations,
            "prior_only_ladder_violations": prior_ladder_violations,
            "full_cost_formula_violations": formula_violations,
            "event_rows": event_count,
            "ready_nonoverlap_event_rows": ready_events,
            "suppressed_overlap_event_rows": suppressed_events,
            "reliability_rows": reliability_count,
            "promotion_ready_rows": promotion_ready,
            "promotion_contract_violations": promotion_violations,
            "suspicious_wiring_columns": sorted(suspicious),
            "historical_consensus_backfill": bool(control["historical_consensus_backfill"]) if control else False,
            "entry_policy": "strict_next_5m_boundary_after_consensus_recorded",
            "overlap_policy": "same_market+direction+horizon_earliest_nonoverlap_outcome_blind",
            "thresholds": {
                "observation_min_events": OBSERVATION_MIN_EVENTS,
                "observation_min_cross_exchange_events": OBSERVATION_MIN_CROSS_EXCHANGE_EVENTS,
                "promotion_min_events": PROMOTION_MIN_EVENTS,
                "promotion_min_cross_exchange_events": PROMOTION_MIN_CROSS_EXCHANGE_EVENTS,
                "promotion_event_wilson_lower_pct": PROMOTION_EVENT_WILSON_LOWER_PCT,
                "promotion_cross_positive_wilson_lower_pct": PROMOTION_CROSS_POSITIVE_WILSON_LOWER_PCT,
            },
            "network_fetches": False,
            "raw_cloud_projection": False,
            "paper_only": True,
            "shadow_only": True,
            "probability_interpretation": False,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }
