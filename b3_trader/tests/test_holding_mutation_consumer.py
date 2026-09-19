from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from b3_trader.holding_mutation_consumer import MutationRejected, apply_mutation


def _database(path: Path, *, exchange: str | None = None) -> None:
    conn = sqlite3.connect(path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE manual_holdings (
                    market TEXT PRIMARY KEY,
                    volume REAL NOT NULL,
                    avg_price REAL NOT NULL,
                    exchange TEXT,
                    updated_ts REAL NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO manual_holdings(market,volume,avg_price,exchange,updated_ts) VALUES(?,?,?,?,?)",
                ("KRW-BTC", 1.0, 100.0, exchange, 123.0),
            )
    finally:
        conn.close()


def _mutation(*, mutation_id: str, exchange: str, revision: float) -> dict[str, object]:
    return {
        "id": mutation_id,
        "exchange": exchange,
        "market": "KRW-BTC",
        "action": "set_holding",
        "expected_revision": revision,
        "payload": {"volume": 2.0, "avg_price": 110.0},
    }


def test_legacy_blank_exchange_is_backfilled_once(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite3"
    _database(path)

    result = apply_mutation(
        str(path),
        _mutation(mutation_id="legacy-1", exchange="upbit", revision=123.0),
    )

    assert result["exchange"] == "upbit"
    assert result["exchange_backfilled"] is True

    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT volume,avg_price,exchange,updated_ts FROM manual_holdings WHERE market='KRW-BTC'"
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == pytest.approx(2.0)
    assert row[1] == pytest.approx(110.0)
    assert row[2] == "upbit"
    assert row[3] == pytest.approx(float(result["updated_ts"]))


def test_saved_exchange_cannot_be_changed_by_mutation(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite3"
    _database(path, exchange="upbit")

    with pytest.raises(MutationRejected) as excinfo:
        apply_mutation(
            str(path),
            _mutation(mutation_id="conflict-1", exchange="bithumb", revision=123.0),
        )

    assert excinfo.value.code == "EXCHANGE_CONFLICT"

    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT volume,avg_price,exchange,updated_ts FROM manual_holdings WHERE market='KRW-BTC'"
        ).fetchone()
    finally:
        conn.close()

    assert row == (1.0, 100.0, "upbit", 123.0)
