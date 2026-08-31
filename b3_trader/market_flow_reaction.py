from __future__ import annotations

import math
import sqlite3
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH

SCHEMA_VERSION = 1
FEATURE_VERSION = 1
MAX_SIGNALS_PER_RUN = 240
MAX_REACTIONS_PER_RUN = 720
REACTION_RETENTION = 12000
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
ABSORPTION_DIRECTION = {
    "passive_buy_absorption_candidate": 1,
    "passive_sell_absorption_candidate": -1,
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class MarketFlowReactionStore:
    """Forward-only reaction evidence for price-flow divergence signals.

    A reaction starts only after the divergence window has closed. 15m/1h/4h
    outcomes require exact contiguous completed 1m candles from signal_feature_ts
    through the horizon end. 1d uses exact contiguous completed 5m candles so the
    existing bounded 400-bar retention can cover a full day. Signals whose end
    timestamp is not aligned to the 5m source are skipped for 1d rather than
    approximated.

    The store records both flow-followthrough return and, for preregistered
    passive absorption candidates, hypothesis-directional return. It is research
    evidence only: no score, PAPER decision, or order path reads these tables.
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
            CREATE TABLE IF NOT EXISTS research_market_flow_reaction_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                signal_window_label TEXT NOT NULL,
                signal_feature_ts REAL NOT NULL,
                signal_evidence_label TEXT NOT NULL,
                signal_price REAL NOT NULL,
                signal_delta_quote REAL NOT NULL DEFAULT 0,
                signal_delta_pct REAL,
                signal_price_efficiency_bps_per_100m_quote REAL,
                flow_direction INTEGER NOT NULL DEFAULT 0,
                hypothesis_direction INTEGER NOT NULL DEFAULT 0,
                horizon_label TEXT NOT NULL,
                horizon_seconds REAL NOT NULL,
                reaction_start_ts REAL NOT NULL,
                reaction_end_ts REAL NOT NULL,
                reaction_source_timeframe TEXT NOT NULL,
                reaction_source_interval_seconds REAL NOT NULL,
                data_ready INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                endpoint_candle_ts REAL,
                endpoint_price REAL,
                future_return_pct REAL,
                flow_followthrough_return_pct REAL,
                hypothesis_directional_return_pct REAL,
                source TEXT NOT NULL DEFAULT 'price_flow_divergence+rest_ohlcv',
                received_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,signal_window_label,signal_feature_ts,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_reaction_ready
            ON research_market_flow_reaction_mx(data_ready,horizon_label,signal_feature_ts DESC);
            CREATE INDEX IF NOT EXISTS idx_market_flow_reaction_signal
            ON research_market_flow_reaction_mx(exchange,market,signal_window_label,signal_feature_ts DESC);

            CREATE TABLE IF NOT EXISTS research_market_flow_reaction_stats_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                signal_window_label TEXT NOT NULL,
                signal_evidence_label TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                mean_future_return_pct REAL,
                mean_flow_followthrough_return_pct REAL,
                flow_followthrough_hit_rate_pct REAL,
                hypothesis_sample_count INTEGER NOT NULL DEFAULT 0,
                mean_hypothesis_directional_return_pct REAL,
                hypothesis_hit_rate_pct REAL,
                updated_at REAL NOT NULL,
                feature_version INTEGER NOT NULL DEFAULT 1,
                schema_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(exchange,market,signal_window_label,signal_evidence_label,horizon_label)
            );
            CREATE INDEX IF NOT EXISTS idx_market_flow_reaction_stats_lookup
            ON research_market_flow_reaction_stats_mx(exchange,market,horizon_label,sample_count DESC);
            """
        )
        self.conn.commit()

    def _signal_rows(self, limit: int) -> list[dict[str, Any]]:
        tables = {
            str(row[0])
            for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "research_market_price_flow_divergence_mx" not in tables or "research_market_ohlcv_mx" not in tables:
            return []
        rows = self.conn.execute(
            """SELECT exchange,market,window_label,feature_ts,price_close,delta_quote,delta_pct,
                      price_efficiency_bps_per_100m_quote,evidence_label,received_at
               FROM research_market_price_flow_divergence_mx
               WHERE data_ready=1 AND price_close>0 AND delta_pct IS NOT NULL
               ORDER BY feature_ts DESC
               LIMIT ?""",
            (max(1, min(2000, int(limit))),),
        ).fetchall()
        return [dict(row) for row in rows]

    def _existing_ready(self, signal: dict[str, Any], horizon_label: str) -> bool:
        row = self.conn.execute(
            """SELECT data_ready FROM research_market_flow_reaction_mx
               WHERE exchange=? AND market=? AND signal_window_label=?
                 AND signal_feature_ts=? AND horizon_label=?""",
            (
                str(signal["exchange"]),
                str(signal["market"]),
                str(signal["window_label"]),
                float(signal["feature_ts"]),
                str(horizon_label),
            ),
        ).fetchone()
        return bool(row and row["data_ready"])

    def _reaction_price(
        self,
        signal: dict[str, Any],
        horizon_label: str,
        *,
        now: float,
    ) -> tuple[str, float | None, float | None, str, int]:
        horizon_seconds = int(HORIZONS[horizon_label])
        timeframe, interval = REACTION_SOURCE[horizon_label]
        start = float(signal["feature_ts"])
        end = start + horizon_seconds
        if int(start) % interval != 0:
            return "unsupported_exact_alignment", None, None, timeframe, interval
        if now < end:
            return "waiting_horizon", None, None, timeframe, interval

        expected = horizon_seconds // interval
        rows = self.conn.execute(
            """SELECT candle_ts,close,is_closed
               FROM research_market_ohlcv_mx
               WHERE exchange=? AND market=? AND timeframe=?
                 AND candle_ts>=? AND candle_ts<? AND is_closed=1
               ORDER BY candle_ts ASC""",
            (str(signal["exchange"]), str(signal["market"]), timeframe, start, end),
        ).fetchall()
        if len(rows) != expected:
            return "waiting_exact_closed_reaction_path", None, None, timeframe, interval
        actual_ts = [float(row["candle_ts"] or 0.0) for row in rows]
        expected_ts = [start + offset * interval for offset in range(expected)]
        if actual_ts != expected_ts:
            return "waiting_exact_closed_reaction_path", None, None, timeframe, interval
        endpoint_price = _finite(rows[-1]["close"])
        if endpoint_price is None or endpoint_price <= 0:
            return "invalid_endpoint_price", None, None, timeframe, interval
        return "ready", float(rows[-1]["candle_ts"]), endpoint_price, timeframe, interval

    @staticmethod
    def _derive(
        signal: dict[str, Any],
        horizon_label: str,
        *,
        now: float,
        status: str,
        endpoint_candle_ts: float | None,
        endpoint_price: float | None,
        source_timeframe: str,
        source_interval: int,
    ) -> dict[str, Any]:
        signal_price = float(signal["price_close"])
        delta_quote = float(signal.get("delta_quote") or 0.0)
        flow_direction = 1 if delta_quote > 0 else -1 if delta_quote < 0 else 0
        evidence_label = str(signal.get("evidence_label") or "neutral")
        hypothesis_direction = int(ABSORPTION_DIRECTION.get(evidence_label, 0))
        horizon_seconds = float(HORIZONS[horizon_label])
        start = float(signal["feature_ts"])
        end = start + horizon_seconds
        ready = status == "ready" and endpoint_price is not None and endpoint_price > 0
        future_return = ((float(endpoint_price) / signal_price) - 1.0) * 100.0 if ready else None
        flow_followthrough = future_return * flow_direction if future_return is not None and flow_direction else None
        hypothesis_return = (
            future_return * hypothesis_direction
            if future_return is not None and hypothesis_direction
            else None
        )
        return {
            "exchange": str(signal["exchange"]),
            "market": str(signal["market"]),
            "signal_window_label": str(signal["window_label"]),
            "signal_feature_ts": start,
            "signal_evidence_label": evidence_label,
            "signal_price": signal_price,
            "signal_delta_quote": delta_quote,
            "signal_delta_pct": _finite(signal.get("delta_pct")),
            "signal_price_efficiency_bps_per_100m_quote": _finite(
                signal.get("price_efficiency_bps_per_100m_quote")
            ),
            "flow_direction": flow_direction,
            "hypothesis_direction": hypothesis_direction,
            "horizon_label": str(horizon_label),
            "horizon_seconds": horizon_seconds,
            "reaction_start_ts": start,
            "reaction_end_ts": end,
            "reaction_source_timeframe": source_timeframe,
            "reaction_source_interval_seconds": float(source_interval),
            "data_ready": 1 if ready else 0,
            "status": status,
            "endpoint_candle_ts": endpoint_candle_ts,
            "endpoint_price": endpoint_price,
            "future_return_pct": future_return,
            "flow_followthrough_return_pct": flow_followthrough,
            "hypothesis_directional_return_pct": hypothesis_return,
            "received_at": now,
        }

    def _upsert(self, row: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO research_market_flow_reaction_mx(
                   exchange,market,signal_window_label,signal_feature_ts,signal_evidence_label,
                   signal_price,signal_delta_quote,signal_delta_pct,signal_price_efficiency_bps_per_100m_quote,
                   flow_direction,hypothesis_direction,horizon_label,horizon_seconds,reaction_start_ts,
                   reaction_end_ts,reaction_source_timeframe,reaction_source_interval_seconds,data_ready,status,
                   endpoint_candle_ts,endpoint_price,future_return_pct,flow_followthrough_return_pct,
                   hypothesis_directional_return_pct,source,received_at,feature_version,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(exchange,market,signal_window_label,signal_feature_ts,horizon_label) DO UPDATE SET
                   signal_evidence_label=excluded.signal_evidence_label,
                   signal_price=excluded.signal_price,
                   signal_delta_quote=excluded.signal_delta_quote,
                   signal_delta_pct=excluded.signal_delta_pct,
                   signal_price_efficiency_bps_per_100m_quote=excluded.signal_price_efficiency_bps_per_100m_quote,
                   flow_direction=excluded.flow_direction,
                   hypothesis_direction=excluded.hypothesis_direction,
                   reaction_end_ts=excluded.reaction_end_ts,
                   reaction_source_timeframe=excluded.reaction_source_timeframe,
                   reaction_source_interval_seconds=excluded.reaction_source_interval_seconds,
                   data_ready=excluded.data_ready,status=excluded.status,
                   endpoint_candle_ts=excluded.endpoint_candle_ts,endpoint_price=excluded.endpoint_price,
                   future_return_pct=excluded.future_return_pct,
                   flow_followthrough_return_pct=excluded.flow_followthrough_return_pct,
                   hypothesis_directional_return_pct=excluded.hypothesis_directional_return_pct,
                   received_at=excluded.received_at,feature_version=excluded.feature_version,
                   schema_version=excluded.schema_version""",
            (
                row["exchange"],row["market"],row["signal_window_label"],row["signal_feature_ts"],
                row["signal_evidence_label"],row["signal_price"],row["signal_delta_quote"],row["signal_delta_pct"],
                row["signal_price_efficiency_bps_per_100m_quote"],row["flow_direction"],row["hypothesis_direction"],
                row["horizon_label"],row["horizon_seconds"],row["reaction_start_ts"],row["reaction_end_ts"],
                row["reaction_source_timeframe"],row["reaction_source_interval_seconds"],row["data_ready"],
                row["status"],row["endpoint_candle_ts"],row["endpoint_price"],row["future_return_pct"],
                row["flow_followthrough_return_pct"],row["hypothesis_directional_return_pct"],
                "price_flow_divergence+rest_ohlcv",row["received_at"],FEATURE_VERSION,SCHEMA_VERSION,
            ),
        )

    def _refresh_stats(self, now: float) -> int:
        rows = self.conn.execute(
            """SELECT exchange,market,signal_window_label,signal_evidence_label,horizon_label,
                      future_return_pct,flow_followthrough_return_pct,hypothesis_directional_return_pct
               FROM research_market_flow_reaction_mx
               WHERE data_ready=1"""
        ).fetchall()
        grouped: dict[tuple[str, str, str, str, str], list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            key = (
                str(row["exchange"]),str(row["market"]),str(row["signal_window_label"]),
                str(row["signal_evidence_label"]),str(row["horizon_label"]),
            )
            grouped[key].append(row)

        self.conn.execute("DELETE FROM research_market_flow_reaction_stats_mx")
        written = 0
        for key, group in grouped.items():
            future = [float(row["future_return_pct"]) for row in group if row["future_return_pct"] is not None]
            follow = [
                float(row["flow_followthrough_return_pct"])
                for row in group if row["flow_followthrough_return_pct"] is not None
            ]
            hypothesis = [
                float(row["hypothesis_directional_return_pct"])
                for row in group if row["hypothesis_directional_return_pct"] is not None
            ]
            self.conn.execute(
                """INSERT INTO research_market_flow_reaction_stats_mx(
                       exchange,market,signal_window_label,signal_evidence_label,horizon_label,
                       sample_count,mean_future_return_pct,mean_flow_followthrough_return_pct,
                       flow_followthrough_hit_rate_pct,hypothesis_sample_count,
                       mean_hypothesis_directional_return_pct,hypothesis_hit_rate_pct,
                       updated_at,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    *key,
                    len(future),
                    statistics.fmean(future) if future else None,
                    statistics.fmean(follow) if follow else None,
                    (sum(1 for value in follow if value > 0) / len(follow) * 100.0) if follow else None,
                    len(hypothesis),
                    statistics.fmean(hypothesis) if hypothesis else None,
                    (sum(1 for value in hypothesis if value > 0) / len(hypothesis) * 100.0) if hypothesis else None,
                    now,FEATURE_VERSION,SCHEMA_VERSION,
                ),
            )
            written += 1
        return written

    def _prune(self) -> int:
        before = self.conn.total_changes
        self.conn.execute(
            """DELETE FROM research_market_flow_reaction_mx
               WHERE rowid IN (
                   SELECT rowid FROM research_market_flow_reaction_mx
                   ORDER BY signal_feature_ts DESC,horizon_seconds ASC
                   LIMIT -1 OFFSET ?
               )""",
            (REACTION_RETENTION,),
        )
        return max(0, self.conn.total_changes - before)

    def compute_pending(self, *, now: float | None = None, limit: int = MAX_SIGNALS_PER_RUN) -> dict[str, Any]:
        stamp = float(now or time.time())
        signals = self._signal_rows(limit)
        processed = 0
        ready_written = 0
        waiting_written = 0
        alignment_skipped = 0
        for signal in signals:
            for horizon_label in HORIZONS:
                if processed >= MAX_REACTIONS_PER_RUN:
                    break
                if self._existing_ready(signal, horizon_label):
                    continue
                status, endpoint_ts, endpoint_price, source_tf, source_interval = self._reaction_price(
                    signal,horizon_label,now=stamp
                )
                if status == "unsupported_exact_alignment":
                    alignment_skipped += 1
                    continue
                row = self._derive(
                    signal,horizon_label,now=stamp,status=status,endpoint_candle_ts=endpoint_ts,
                    endpoint_price=endpoint_price,source_timeframe=source_tf,source_interval=source_interval,
                )
                self._upsert(row)
                processed += 1
                if row["data_ready"]:
                    ready_written += 1
                else:
                    waiting_written += 1
            if processed >= MAX_REACTIONS_PER_RUN:
                break

        pruned = self._prune()
        stats_written = self._refresh_stats(stamp)
        self.conn.commit()
        return {
            "ok": True,
            "status": "computed",
            "signals_scanned": len(signals),
            "reactions_processed": processed,
            "ready_written": ready_written,
            "waiting_written": waiting_written,
            "exact_alignment_skipped": alignment_skipped,
            "stats_written": stats_written,
            "rows_pruned": pruned,
            "horizons": list(HORIZONS),
            "reaction_sources": {label: REACTION_SOURCE[label][0] for label in HORIZONS},
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
        }

    def audit(self) -> dict[str, Any]:
        table_exists = bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_flow_reaction_mx'"
        ).fetchone())
        if not table_exists:
            return {
                "ok": True,"status": "waiting_for_table","table_exists": False,"row_count": 0,
                "ready_rows": 0,"waiting_rows": 0,"reaction_time_violations": 0,
                "paper_only": True,"score_wired": False,"can_place_orders": False,
            }
        row_count = int(self.conn.execute("SELECT COUNT(*) FROM research_market_flow_reaction_mx").fetchone()[0])
        ready_rows = int(self.conn.execute(
            "SELECT COUNT(*) FROM research_market_flow_reaction_mx WHERE data_ready=1"
        ).fetchone()[0])
        waiting_rows = row_count - ready_rows
        time_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_reaction_mx
               WHERE ABS(reaction_end_ts-(signal_feature_ts+horizon_seconds))>0.001"""
        ).fetchone()[0])
        source_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_reaction_mx
               WHERE (horizon_label IN ('15m','1h','4h') AND reaction_source_timeframe!='1m')
                  OR (horizon_label='1d' AND reaction_source_timeframe!='5m')"""
        ).fetchone()[0])
        direction_violations = int(self.conn.execute(
            """SELECT COUNT(*) FROM research_market_flow_reaction_mx
               WHERE (signal_evidence_label='passive_buy_absorption_candidate' AND hypothesis_direction!=1)
                  OR (signal_evidence_label='passive_sell_absorption_candidate' AND hypothesis_direction!=-1)
                  OR (signal_evidence_label NOT IN ('passive_buy_absorption_candidate','passive_sell_absorption_candidate') AND hypothesis_direction!=0)"""
        ).fetchone()[0])
        latest = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_reaction_mx
               WHERE data_ready=1 ORDER BY reaction_end_ts DESC,signal_feature_ts DESC LIMIT 12"""
        ).fetchall()]
        stats = [dict(row) for row in self.conn.execute(
            """SELECT * FROM research_market_flow_reaction_stats_mx
               ORDER BY hypothesis_sample_count DESC,sample_count DESC,updated_at DESC LIMIT 24"""
        ).fetchall()]
        return {
            "ok": time_violations == 0 and source_violations == 0 and direction_violations == 0,
            "status": "ready" if ready_rows else "waiting_for_forward_horizons",
            "table_exists": True,
            "row_count": row_count,
            "ready_rows": ready_rows,
            "waiting_rows": waiting_rows,
            "reaction_time_violations": time_violations,
            "reaction_source_violations": source_violations,
            "hypothesis_direction_violations": direction_violations,
            "latest_ready": latest,
            "stats": stats,
            "horizons": list(HORIZONS),
            "join_contract": "forward_only_exact_contiguous_closed_ohlcv_after_signal_window",
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "raw_cloud_projection": False,
            "feature_version": FEATURE_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
