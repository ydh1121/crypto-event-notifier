from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

DEFAULT_SOURCE_DB = Path("b3_trader/data/auto_demo.sqlite3")
DEFAULT_ROOT = Path("b3_trader/data/research-warehouse")
STATE_FILE = "warehouse-state.json"
EXPORT_TABLES = (
    "research_market_memory",
    "research_fills",
    "research_feedback",
    "research_equity",
    "research_market_memory_mx",
    "research_fills_mx",
    "research_feedback_mx",
    "research_equity_mx",
)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def _sql_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _utc_date(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")


class ResearchWarehouse:
    """Incrementally exports append-heavy PAPER research tables to Parquet.

    SQLite stays authoritative for live PAPER operation. Parquet is a secondary,
    append-only analytical warehouse intended for DuckDB/local-AI research.
    """

    def __init__(self, source_db: Path = DEFAULT_SOURCE_DB, root: Path = DEFAULT_ROOT) -> None:
        self.source_db = Path(source_db)
        self.root = Path(root)
        self.state_path = self.root / STATE_FILE
        self.state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"version": 1, "tables": {}, "updated_at": 0.0}
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                value.setdefault("tables", {})
                return value
        except (OSError, json.JSONDecodeError):
            pass
        return {"version": 1, "tables": {}, "updated_at": 0.0}

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
        ).fetchone()
        return row is not None

    @staticmethod
    def _id_column(conn: sqlite3.Connection, table: str) -> str | None:
        columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if "id" in columns:
            return "id"
        return None

    @staticmethod
    def _timestamp_column(conn: sqlite3.Connection, table: str) -> str:
        columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        for candidate in ("ts", "signal_ts", "updated_ts"):
            if candidate in columns:
                return candidate
        return ""

    def _read_batch(
        self,
        conn: sqlite3.Connection,
        table: str,
        *,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        id_column = self._id_column(conn, table)
        checkpoint = int((self.state.get("tables") or {}).get(table, {}).get("last_id") or 0)
        if id_column:
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE {id_column} > ? ORDER BY {id_column} ASC LIMIT ?",
                (checkpoint, int(limit)),
            ).fetchall()
            values = [dict(row) for row in rows]
            new_checkpoint = int(values[-1][id_column]) if values else checkpoint
            return values, new_checkpoint

        # Tables without an integer id are snapshots/current state rather than append-heavy history.
        return [], checkpoint

    def _write_parquet_group(self, table: str, date_key: str, rows: list[dict[str, Any]]) -> Path:
        if not rows:
            raise ValueError("rows required")
        table_dir = self.root / "parquet" / f"table={table}" / f"date={date_key}"
        table_dir.mkdir(parents=True, exist_ok=True)
        first_id = int(rows[0].get("id") or 0)
        last_id = int(rows[-1].get("id") or first_id)
        output = table_dir / f"part-{int(time.time() * 1000)}-{first_id}-{last_id}.parquet"

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".ndjson", delete=False, dir=str(self.root)
        ) as handle:
            spool = Path(handle.name)
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str))
                handle.write("\n")
        try:
            con = duckdb.connect(database=":memory:")
            try:
                con.execute(
                    f"COPY (SELECT * FROM read_json_auto({_sql_literal(spool)}, format='newline_delimited')) "
                    f"TO {_sql_literal(output)} (FORMAT PARQUET, COMPRESSION ZSTD)"
                )
            finally:
                con.close()
        finally:
            spool.unlink(missing_ok=True)
        return output

    def export_once(self, *, batch_limit: int = 50_000) -> dict[str, Any]:
        started = time.time()
        if not self.source_db.exists():
            return {
                "status": "waiting_for_source_db",
                "source_db": str(self.source_db),
                "exported_rows": 0,
                "files": [],
                "elapsed_seconds": round(time.time() - started, 3),
            }

        self.root.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.source_db), timeout=30)
        conn.row_factory = sqlite3.Row
        exported_rows = 0
        files: list[str] = []
        table_results: dict[str, Any] = {}
        try:
            for table in EXPORT_TABLES:
                if not self._table_exists(conn, table):
                    table_results[table] = {"status": "not_created", "rows": 0}
                    continue
                rows, new_checkpoint = self._read_batch(conn, table, limit=batch_limit)
                if not rows:
                    table_results[table] = {
                        "status": "up_to_date",
                        "rows": 0,
                        "last_id": int((self.state.get("tables") or {}).get(table, {}).get("last_id") or 0),
                    }
                    continue

                ts_column = self._timestamp_column(conn, table)
                grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for row in rows:
                    ts = float(row.get(ts_column) or time.time()) if ts_column else time.time()
                    grouped[_utc_date(ts)].append(row)

                written: list[str] = []
                for date_key, group in grouped.items():
                    path = self._write_parquet_group(table, date_key, group)
                    written.append(str(path))
                    files.append(str(path))

                exported_rows += len(rows)
                table_state = {
                    "last_id": new_checkpoint,
                    "rows_exported_total": int(
                        (self.state.get("tables") or {}).get(table, {}).get("rows_exported_total") or 0
                    ) + len(rows),
                    "last_export_at": time.time(),
                    "last_files": written[-8:],
                }
                self.state.setdefault("tables", {})[table] = table_state
                table_results[table] = {"status": "exported", "rows": len(rows), **table_state}

            self.state["updated_at"] = time.time()
            self.state["source_db"] = str(self.source_db)
            self.state["root"] = str(self.root)
            _atomic_json(self.state_path, self.state)
        finally:
            conn.close()

        return {
            "status": "ok",
            "exported_rows": exported_rows,
            "files": files,
            "tables": table_results,
            "state_file": str(self.state_path),
            "elapsed_seconds": round(time.time() - started, 3),
        }


def main() -> None:
    result = ResearchWarehouse().export_once()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
