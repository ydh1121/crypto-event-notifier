from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.cloudflare_snapshot_publisher import (
    _manual_holdings,
    _manual_holdings_history,
    _record_manual_holdings_snapshot,
)


def _seed_holding(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE manual_holdings (
                    market TEXT PRIMARY KEY,
                    volume REAL NOT NULL,
                    avg_price REAL NOT NULL,
                    updated_ts REAL NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO manual_holdings(market,volume,avg_price,updated_ts) VALUES (?,?,?,?)",
                ("KRW-BTC", 0.1, 100_000_000.0, 1_000.0),
            )
    finally:
        conn.close()


def test_manual_holdings_history_is_bounded_and_interval_limited(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite3"
    _seed_holding(path)

    summary = _manual_holdings(str(path), {"KRW-BTC": 110_000_000.0})
    assert summary["holding_count"] == 1
    assert summary["priced_holding_count"] == 1
    assert summary["valuation_complete"] is True
    assert summary["invested_krw"] == 10_000_000.0
    assert summary["value_krw"] == 11_000_000.0
    assert summary["pnl_krw"] == 1_000_000.0

    assert _record_manual_holdings_snapshot(str(path), summary, now=10_000.0) is True
    assert _record_manual_holdings_snapshot(str(path), summary, now=10_299.0) is False

    later = {**summary, "value_krw": 12_000_000.0, "pnl_krw": 2_000_000.0}
    assert _record_manual_holdings_snapshot(str(path), later, now=10_301.0) is True

    history = _manual_holdings_history(str(path))
    assert history["interval_seconds"] == 300
    assert history["retention_days"] == 90
    assert history["points"] == [
        [10_000.0, 10_000_000.0, 11_000_000.0, 1_000_000.0, 1],
        [10_301.0, 10_000_000.0, 12_000_000.0, 2_000_000.0, 1],
    ]


def test_incomplete_manual_holdings_valuation_is_not_recorded(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite3"
    _seed_holding(path)

    summary = _manual_holdings(str(path), {})
    assert summary["holding_count"] == 1
    assert summary["priced_holding_count"] == 0
    assert summary["valuation_complete"] is False
    assert _record_manual_holdings_snapshot(str(path), summary, now=20_000.0) is False
    assert _manual_holdings_history(str(path))["points"] == []
