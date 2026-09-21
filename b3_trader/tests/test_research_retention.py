from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from b3_trader.research_retention import ResearchRetentionManager, compact_runtime_history


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE research_market_memory_mx(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            exchange TEXT NOT NULL,
            strategy TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE research_equity_mx(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            exchange TEXT NOT NULL,
            strategy TEXT NOT NULL
        )"""
    )
    return conn


def _archive(root: Path, table: str, *, checkpoint: int, parquet_max: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    state_path = root / "warehouse-state.json"
    state = {"tables": {table: {"last_id": checkpoint}}}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    part = root / "parquet" / f"table={table}" / "date=2026-09-01"
    part.mkdir(parents=True, exist_ok=True)
    (part / f"part-1000-1-{parquet_max}.parquet").write_bytes(b"test")


def test_retention_refuses_delete_when_archive_is_behind(tmp_path: Path) -> None:
    conn = _db()
    conn.execute(
        "INSERT INTO research_market_memory_mx(ts,exchange,strategy) VALUES(?,?,?)",
        (100.0, "bithumb", "adaptive"),
    )
    conn.commit()
    _archive(tmp_path, "research_market_memory_mx", checkpoint=0, parquet_max=0)

    result = ResearchRetentionManager(conn, warehouse_root=tmp_path).prune_table(
        "research_market_memory_mx",
        exchange="bithumb",
        strategy="adaptive",
        cutoff_ts=200.0,
    )

    assert result["status"] == "archive_not_ready"
    assert result["deleted_rows"] == 0
    assert conn.execute("SELECT COUNT(*) FROM research_market_memory_mx").fetchone()[0] == 1


def test_retention_deletes_only_archive_safe_scope_and_is_bounded(tmp_path: Path) -> None:
    conn = _db()
    rows = [
        (100.0, "bithumb", "adaptive"),
        (110.0, "bithumb", "adaptive"),
        (300.0, "bithumb", "adaptive"),
        (100.0, "upbit", "adaptive"),
    ]
    conn.executemany(
        "INSERT INTO research_market_memory_mx(ts,exchange,strategy) VALUES(?,?,?)",
        rows,
    )
    conn.commit()
    _archive(tmp_path, "research_market_memory_mx", checkpoint=10, parquet_max=10)

    manager = ResearchRetentionManager(conn, warehouse_root=tmp_path)
    first = manager.prune_table(
        "research_market_memory_mx",
        exchange="bithumb",
        strategy="adaptive",
        cutoff_ts=200.0,
        batch_rows=1,
        max_batches=1,
    )
    assert first["status"] == "pruned"
    assert first["deleted_rows"] == 1
    assert first["remaining_candidate_rows"] == 1

    second = manager.prune_table(
        "research_market_memory_mx",
        exchange="bithumb",
        strategy="adaptive",
        cutoff_ts=200.0,
        batch_rows=10,
        max_batches=1,
    )
    assert second["deleted_rows"] == 1

    remaining = conn.execute(
        "SELECT ts,exchange FROM research_market_memory_mx ORDER BY id"
    ).fetchall()
    assert remaining == [(300.0, "bithumb"), (100.0, "upbit")]


def test_compact_runtime_history_strips_features_and_keeps_recent_resolution() -> None:
    now = 1_000_000.0
    rows = [
        {"ts": now - 90_000, "price": 1, "features": {"trade_plan": {"huge": True}}},
        {"ts": now - 89_900, "price": 2, "features": {"trade_plan": {"huge": True}}},
        {"ts": now - 89_800, "price": 3, "features": {"trade_plan": {"huge": True}}},
        {"ts": now - 3_600, "price": 4, "features": {"trade_plan": {"huge": True}}},
        {"ts": now - 1_800, "price": 5, "features": {"trade_plan": {"huge": True}}},
        {"ts": now - 60, "price": 6, "features": {"trade_plan": {"huge": True}}},
    ]

    compact = compact_runtime_history(rows, now=now)

    assert [row["price"] for row in compact[-3:]] == [4, 5, 6]
    assert len([row for row in compact if row["ts"] < now - 86_400]) <= 2
    assert all("features" not in row for row in compact)
    assert [row["ts"] for row in compact] == sorted(row["ts"] for row in compact)
