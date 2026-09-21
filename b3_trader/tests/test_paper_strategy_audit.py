from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from b3_trader.paper_strategy_audit import audit_paper_strategy


def _db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE research_fills_mx (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            exchange TEXT NOT NULL,
            market TEXT NOT NULL,
            strategy TEXT NOT NULL,
            side TEXT NOT NULL,
            krw REAL NOT NULL,
            reason TEXT NOT NULL
        );
        CREATE TABLE research_signals_mx (
            exchange TEXT NOT NULL,
            market TEXT NOT NULL,
            strategy TEXT NOT NULL,
            trade_intent TEXT NOT NULL,
            reason TEXT NOT NULL
        );
        CREATE TABLE research_market_memory_mx (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange TEXT NOT NULL,
            market TEXT NOT NULL,
            strategy TEXT NOT NULL,
            trade_intent TEXT NOT NULL,
            feature_json TEXT NOT NULL
        );
        """
    )
    return conn


def test_audit_reports_real_add_cycles_and_small_ticket_distribution(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite3"
    conn = _db(path)
    rows = [
        (1.0, "bithumb", "KRW-A", "adaptive", "buy", 400_000.0, "entry"),
        (2.0, "bithumb", "KRW-A", "adaptive", "buy", 300_000.0, "staged_add"),
        (3.0, "bithumb", "KRW-A", "adaptive", "sell", 720_000.0, "exit"),
        (4.0, "bithumb", "KRW-B", "adaptive", "buy", 600_000.0, "entry"),
    ]
    conn.executemany(
        "INSERT INTO research_fills_mx(ts,exchange,market,strategy,side,krw,reason) VALUES(?,?,?,?,?,?,?)",
        rows,
    )
    conn.execute(
        "INSERT INTO research_signals_mx(exchange,market,strategy,trade_intent,reason) VALUES(?,?,?,?,?)",
        ("bithumb", "KRW-A", "adaptive", "hold", "position hold"),
    )
    conn.execute(
        "INSERT INTO research_market_memory_mx(exchange,market,strategy,trade_intent,feature_json) VALUES(?,?,?,?,?)",
        (
            "bithumb",
            "KRW-A",
            "adaptive",
            "add",
            json.dumps({"execution_note": "blocked: spread=90.0bps"}),
        ),
    )
    conn.commit()
    conn.close()

    result = audit_paper_strategy(path)

    assert result["paper_only"] is True
    assert result["read_only"] is True
    assert result["can_place_orders"] is False
    assert result["fills"]["buys"] == 3
    assert result["fills"]["buy_ticket_krw"]["median"] == 400_000.0
    assert result["fills"]["buy_ticket_krw"]["lte_500k_pct"] == 66.67
    assert result["averaging"]["cycles"] == 2
    assert result["averaging"]["cycles_with_adds"] == 1
    assert result["averaging"]["add_fill_count"] == 1
    assert result["averaging"]["first_buy_mean_krw"] == 500_000.0
    assert result["averaging"]["add_buy_mean_krw"] == 300_000.0
    assert result["averaging"]["add_vs_first_size_ratio"] == 0.6
    assert result["historical_execution_blockers"]["blocked: spread=90.0bps"] == 1


def test_audit_is_empty_safe(tmp_path: Path) -> None:
    path = tmp_path / "empty.sqlite3"
    sqlite3.connect(path).close()

    result = audit_paper_strategy(path)

    assert result["fills"]["total"] == 0
    assert result["averaging"]["cycles"] == 0
    assert result["averaging"]["add_fill_count"] == 0
    assert result["historical_execution_blockers"] == {}
