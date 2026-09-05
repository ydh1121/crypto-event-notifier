from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .research_warehouse import DEFAULT_ROOT, STATE_FILE

HOT_MEMORY_DAYS = 7
HOT_EQUITY_DAYS = 7
RETENTION_MAINTENANCE_SECONDS = 15 * 60
DEFAULT_DELETE_BATCH_ROWS = 25_000
DEFAULT_MAX_BATCHES = 4
RUNTIME_RECENT_SECONDS = 24 * 3600
RUNTIME_BUCKET_SECONDS = 3600
RUNTIME_HORIZON_SECONDS = 7 * 86400

_ARCHIVE_TABLES = {
    "research_market_memory_mx",
    "research_equity_mx",
}
_PART_RE = re.compile(r"part-\d+-(\d+)-(\d+)\.parquet$")


def _load_state(root: Path) -> dict[str, Any]:
    path = root / STATE_FILE
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _parquet_max_id(root: Path, table: str) -> int:
    directory = root / "parquet" / f"table={table}"
    if not directory.exists():
        return 0
    maximum = 0
    for path in directory.rglob("*.parquet"):
        match = _PART_RE.match(path.name)
        if match:
            maximum = max(maximum, int(match.group(2)))
    return maximum


def compact_runtime_history(
    rows: list[dict[str, Any]],
    *,
    ts_key: str = "ts",
    now: float | None = None,
    recent_seconds: float = RUNTIME_RECENT_SECONDS,
    horizon_seconds: float = RUNTIME_HORIZON_SECONDS,
    bucket_seconds: float = RUNTIME_BUCKET_SECONDS,
) -> list[dict[str, Any]]:
    """Keep recent points at full resolution and downsample older runtime-only history.

    The database and Parquet warehouse remain untouched. Input may be newest-first
    or oldest-first; output is chronological. For each older bucket the newest
    point is retained so charts preserve the end-state of that interval.
    """
    current = float(now or time.time())
    horizon = current - max(float(recent_seconds), float(horizon_seconds))
    recent_cutoff = current - max(0.0, float(recent_seconds))
    bucket = max(60.0, float(bucket_seconds))

    normalized: list[dict[str, Any]] = []
    for source in rows:
        if not isinstance(source, dict):
            continue
        try:
            ts = float(source.get(ts_key) or 0.0)
        except (TypeError, ValueError):
            continue
        if ts <= 0 or ts < horizon:
            continue
        item = dict(source)
        item.pop("features", None)
        normalized.append(item)

    normalized.sort(key=lambda row: float(row.get(ts_key) or 0.0))
    recent: list[dict[str, Any]] = []
    older_by_bucket: dict[int, dict[str, Any]] = {}
    for item in normalized:
        ts = float(item.get(ts_key) or 0.0)
        if ts >= recent_cutoff:
            recent.append(item)
        else:
            older_by_bucket[int(ts // bucket)] = item
    return [*older_by_bucket.values(), *recent]


class ResearchRetentionManager:
    """Prune hot SQLite history only after the incremental Parquet archive is ahead.

    This deliberately refuses to delete if warehouse state is absent, stale, or
    its filename coverage does not reach the candidate rows. It only owns the two
    append-heavy MX tables that are already exported by ResearchWarehouse.
    """

    def __init__(self, conn: Any, *, warehouse_root: Path | str = DEFAULT_ROOT) -> None:
        self.conn = conn
        self.warehouse_root = Path(warehouse_root)

    def _archive_gate(
        self,
        table: str,
        *,
        exchange: str,
        strategy: str,
        cutoff_ts: float,
    ) -> dict[str, Any]:
        if table not in _ARCHIVE_TABLES:
            raise ValueError(f"unsupported retention table: {table}")
        row = self.conn.execute(
            f"SELECT COUNT(*) AS rows,COALESCE(MAX(id),0) AS max_id FROM {table} "
            "WHERE exchange=? AND strategy=? AND ts < ?",
            (exchange, strategy, float(cutoff_ts)),
        ).fetchone()
        candidate_rows = int(row[0] or 0) if row else 0
        candidate_max_id = int(row[1] or 0) if row else 0
        state = _load_state(self.warehouse_root)
        tables = state.get("tables") if isinstance(state.get("tables"), dict) else {}
        info = tables.get(table) if isinstance(tables.get(table), dict) else {}
        checkpoint = int(info.get("last_id") or 0)
        parquet_max_id = _parquet_max_id(self.warehouse_root, table)
        safe = candidate_max_id == 0 or (
            checkpoint >= candidate_max_id and parquet_max_id >= candidate_max_id
        )
        return {
            "table": table,
            "candidate_rows": candidate_rows,
            "candidate_max_id": candidate_max_id,
            "warehouse_last_id": checkpoint,
            "parquet_max_id": parquet_max_id,
            "safe": safe,
        }

    def prune_table(
        self,
        table: str,
        *,
        exchange: str,
        strategy: str,
        cutoff_ts: float,
        batch_rows: int = DEFAULT_DELETE_BATCH_ROWS,
        max_batches: int = DEFAULT_MAX_BATCHES,
    ) -> dict[str, Any]:
        gate = self._archive_gate(
            table,
            exchange=exchange,
            strategy=strategy,
            cutoff_ts=cutoff_ts,
        )
        if not gate["safe"]:
            return {**gate, "status": "archive_not_ready", "deleted_rows": 0}
        if gate["candidate_rows"] <= 0:
            return {**gate, "status": "up_to_date", "deleted_rows": 0}

        delete_ceiling = int(gate["candidate_max_id"])
        limit = max(1, int(batch_rows))
        batches = max(1, int(max_batches))
        deleted = 0
        for _ in range(batches):
            before = self.conn.total_changes
            self.conn.execute(
                f"DELETE FROM {table} WHERE id IN ("
                f"SELECT id FROM {table} WHERE exchange=? AND strategy=? "
                "AND ts < ? AND id <= ? ORDER BY id ASC LIMIT ?)",
                (exchange, strategy, float(cutoff_ts), delete_ceiling, limit),
            )
            self.conn.commit()
            changed = max(0, self.conn.total_changes - before)
            deleted += changed
            if changed < limit:
                break
        remaining = max(0, int(gate["candidate_rows"]) - deleted)
        return {
            **gate,
            "status": "pruned" if deleted else "up_to_date",
            "deleted_rows": deleted,
            "remaining_candidate_rows": remaining,
        }

    def prune_scope(
        self,
        *,
        exchange: str,
        strategy: str,
        now: float | None = None,
        memory_days: int = HOT_MEMORY_DAYS,
        equity_days: int = HOT_EQUITY_DAYS,
        batch_rows: int = DEFAULT_DELETE_BATCH_ROWS,
        max_batches: int = DEFAULT_MAX_BATCHES,
    ) -> dict[str, Any]:
        current = float(now or time.time())
        memory = self.prune_table(
            "research_market_memory_mx",
            exchange=exchange,
            strategy=strategy,
            cutoff_ts=current - max(1, int(memory_days)) * 86400.0,
            batch_rows=batch_rows,
            max_batches=max_batches,
        )
        equity = self.prune_table(
            "research_equity_mx",
            exchange=exchange,
            strategy=strategy,
            cutoff_ts=current - max(1, int(equity_days)) * 86400.0,
            batch_rows=batch_rows,
            max_batches=max_batches,
        )
        return {
            "status": "ok",
            "exchange": exchange,
            "strategy": strategy,
            "memory_days": int(memory_days),
            "equity_days": int(equity_days),
            "memory": memory,
            "equity": equity,
            "updated_at": current,
        }
