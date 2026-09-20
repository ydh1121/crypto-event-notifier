from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from b3_trader.holding_mutation_consumer import MutationRejected, apply_mutation


def _database(path: Path, *, exchange: str | None = None, market: str = "KRW-BTC") -> None:
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
                (market, 1.0, 100.0, exchange, 123.0),
            )
    finally:
        conn.close()


def _mutation(*, mutation_id: str, exchange: str, revision: float, market: str = "KRW-BTC") -> dict[str, object]:
    return {
        "id": mutation_id,
        "exchange": exchange,
        "market": market,
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


def test_zero_volume_closeout_sets_volume_and_avg_to_zero(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite3"
    _database(path, exchange="bithumb")

    mutation = _mutation(mutation_id="closeout-1", exchange="bithumb", revision=123.0)
    mutation["payload"] = {"volume": 0.0, "avg_price": 100.0}

    result = apply_mutation(str(path), mutation)

    assert result["final_volume"] == 0.0
    assert result["final_avg_price"] == 0.0

    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT volume,avg_price,exchange,updated_ts FROM manual_holdings WHERE market='KRW-BTC'"
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == 0.0
    assert row[1] == 0.0
    assert row[2] == "bithumb"
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


def test_bithumb_btc_market_has_zero_fee_and_supports_pair_key(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite3"
    market = "KRW-ETH/BTC"
    _database(path, market=market)
    result = apply_mutation(
        str(path),
        _mutation(mutation_id="btc-quote-1", exchange="bithumb", revision=123.0, market=market),
    )
    assert result["market"] == market
    assert result["quote_currency"] == "BTC"
    assert result["fee_rate"] == 0.0
    assert result["fee_policy"] == "bithumb_btc_free"
    assert result["exchange_backfilled"] is True


def test_btc_market_averaging_write_is_blocked_until_quote_aware(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite3"
    market = "KRW-ETH/BTC"
    _database(path, exchange="bithumb", market=market)
    mutation = _mutation(mutation_id="btc-avg-1", exchange="bithumb", revision=123.0, market=market)
    mutation["action"] = "apply_averaging"
    mutation["payload"] = {"rounds": [{"price": 0.03, "amount_krw": 0.001}]}
    with pytest.raises(MutationRejected) as excinfo:
        apply_mutation(str(path), mutation)
    assert excinfo.value.code == "QUOTE_AWARE_AVERAGING_REQUIRED"
