from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .market_flow_reaction import (
    REACTION_SOURCE,
    SOURCE_RETENTION_BARS,
    TERMINAL_WAIT_STATUSES,
    MarketFlowReactionStore,
)

MAX_DUE_REACTIONS_PER_RUN = 480


class MarketFlowReactionDueStore:
    """Drain matured forward-reaction rows that aged out of the latest-signal scan.

    ``MarketFlowReactionStore.compute_pending`` intentionally scans only a bounded
    set of the newest divergence signals. Under sustained one-minute signal flow,
    longer-horizon rows can mature after their source signal has fallen outside
    that newest-signal window. This local-only drain revisits those already
    registered waiting rows by their exact reaction horizon without creating any
    synthetic history or relaxing the exact contiguous OHLCV contract.

    Recoverable rows are processed before rows whose bounded OHLCV source window
    has already expired. The latter are still drained afterward so the existing
    reaction store can terminally mark them rather than carrying stale waiting
    rows forever. No score, PAPER decision, strategy mutation or order path reads
    this queue.
    """

    def __init__(self, path: Path | str = DB_PATH) -> None:
        self.path = Path(path)
        self.reactions = MarketFlowReactionStore(self.path)

    def close(self) -> None:
        self.reactions.close()

    def _due_rows(self, stamp: float, limit: int) -> tuple[list[dict[str, Any]], int, int]:
        rows = self.reactions.conn.execute(
            """SELECT exchange,market,
                      signal_window_label AS window_label,
                      signal_feature_ts AS feature_ts,
                      signal_evidence_label AS evidence_label,
                      signal_price AS price_close,
                      signal_delta_quote AS delta_quote,
                      signal_delta_pct AS delta_pct,
                      signal_price_efficiency_bps_per_100m_quote AS price_efficiency_bps_per_100m_quote,
                      horizon_label,reaction_end_ts,status,received_at
               FROM research_market_flow_reaction_mx
               WHERE data_ready=0 AND reaction_end_ts<=?
               ORDER BY reaction_end_ts ASC,signal_feature_ts ASC""",
            (float(stamp),),
        ).fetchall()

        candidates: list[dict[str, Any]] = []
        recoverable_count = 0
        for source_row in rows:
            row = dict(source_row)
            if str(row.get("status") or "") in TERMINAL_WAIT_STATUSES:
                continue
            horizon_label = str(row.get("horizon_label") or "")
            source = REACTION_SOURCE.get(horizon_label)
            if source is None:
                continue
            interval = int(source[1])
            retention_span = float(SOURCE_RETENTION_BARS * interval)
            recoverable = float(stamp) - float(row["feature_ts"]) <= retention_span
            row["_recoverable"] = recoverable
            recoverable_count += 1 if recoverable else 0
            candidates.append(row)

        candidates.sort(
            key=lambda row: (
                0 if bool(row.get("_recoverable")) else 1,
                float(row.get("reaction_end_ts") or 0.0),
                float(row.get("feature_ts") or 0.0),
                str(row.get("horizon_label") or ""),
            )
        )
        bounded = candidates[:max(1, min(MAX_DUE_REACTIONS_PER_RUN, int(limit)))]
        return bounded, len(candidates), recoverable_count

    def compute(
        self,
        *,
        now: float | None = None,
        limit: int = MAX_DUE_REACTIONS_PER_RUN,
    ) -> dict[str, Any]:
        stamp = float(time.time() if now is None else now)
        due_rows, total_due, recoverable_due = self._due_rows(stamp, limit)
        processed = 0
        ready_written = 0
        waiting_written = 0
        terminal_expired = 0
        exact_alignment_skipped = 0
        selected_recoverable = 0

        for due in due_rows:
            horizon_label = str(due["horizon_label"])
            selected_recoverable += 1 if bool(due.get("_recoverable")) else 0
            signal = {
                "exchange": str(due["exchange"]),
                "market": str(due["market"]),
                "window_label": str(due["window_label"]),
                "feature_ts": float(due["feature_ts"]),
                "evidence_label": str(due["evidence_label"]),
                "price_close": float(due["price_close"]),
                "delta_quote": float(due.get("delta_quote") or 0.0),
                "delta_pct": due.get("delta_pct"),
                "price_efficiency_bps_per_100m_quote": due.get("price_efficiency_bps_per_100m_quote"),
                "received_at": float(due.get("received_at") or stamp),
            }
            status, endpoint_ts, endpoint_price, source_tf, source_interval = self.reactions._reaction_price(
                signal,
                horizon_label,
                now=stamp,
            )
            if status == "unsupported_exact_alignment":
                exact_alignment_skipped += 1
                continue
            row = self.reactions._derive(
                signal,
                horizon_label,
                now=stamp,
                status=status,
                endpoint_candle_ts=endpoint_ts,
                endpoint_price=endpoint_price,
                source_timeframe=source_tf,
                source_interval=source_interval,
            )
            self.reactions._upsert(row)
            processed += 1
            if int(row["data_ready"]) == 1:
                ready_written += 1
            else:
                waiting_written += 1
                if status == "expired_missing_exact_reaction_path":
                    terminal_expired += 1

        stats_written = self.reactions._refresh_stats(stamp) if processed else 0
        self.reactions.conn.commit()
        return {
            "ok": True,
            "status": "computed" if due_rows else "no_due_reactions",
            "due_rows_available": total_due,
            "recoverable_due_rows": recoverable_due,
            "selected_rows": len(due_rows),
            "selected_recoverable_rows": selected_recoverable,
            "reactions_processed": processed,
            "ready_written": ready_written,
            "waiting_written": waiting_written,
            "terminal_expired_missing_path": terminal_expired,
            "exact_alignment_skipped": exact_alignment_skipped,
            "stats_written": stats_written,
            "max_due_reactions_per_run": MAX_DUE_REACTIONS_PER_RUN,
            "priority": "recoverable_before_expired",
            "network_fetches": False,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
            "can_modify_strategy": False,
        }
