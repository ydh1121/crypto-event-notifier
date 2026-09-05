from __future__ import annotations

import sqlite3
from pathlib import Path

import duckdb

from b3_trader.research_warehouse import ResearchWarehouse


def _seed(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        """CREATE TABLE research_market_memory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            market TEXT NOT NULL,
            price REAL NOT NULL,
            feature_json TEXT NOT NULL DEFAULT '{}'
        )"""
    )
    conn.execute(
        "INSERT INTO research_market_memory(ts,market,price,feature_json) VALUES(?,?,?,?)",
        (1_725_000_000.0, "KRW-BTC", 100.0, '{"x":1}'),
    )
    conn.execute(
        "INSERT INTO research_market_memory(ts,market,price,feature_json) VALUES(?,?,?,?)",
        (1_725_000_100.0, "KRW-XRP", 200.0, '{"x":2}'),
    )
    conn.commit()
    conn.close()


def test_incremental_market_memory_export(tmp_path: Path) -> None:
    db = tmp_path / "auto_demo.sqlite3"
    root = tmp_path / "warehouse"
    _seed(db)

    warehouse = ResearchWarehouse(source_db=db, root=root)
    first = warehouse.export_once()
    assert first["status"] == "ok"
    assert first["exported_rows"] == 2
    files = list((root / "parquet" / "table=research_market_memory").rglob("*.parquet"))
    assert files

    count = duckdb.connect(database=":memory:").execute(
        "SELECT COUNT(*) FROM read_parquet(?)", [str(files[0])]
    ).fetchone()[0]
    assert count >= 1

    second = ResearchWarehouse(source_db=db, root=root).export_once()
    assert second["exported_rows"] == 0

    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO research_market_memory(ts,market,price,feature_json) VALUES(?,?,?,?)",
        (1_725_000_200.0, "KRW-BTC", 101.0, '{"x":3}'),
    )
    conn.commit()
    conn.close()

    third = ResearchWarehouse(source_db=db, root=root).export_once()
    assert third["exported_rows"] == 1
