import sqlite3

import pytest

from b3_trader.user_tools import UserToolsStore, calculate_averaging


def test_calculate_averaging_updates_average():
    result = calculate_averaging(
        volume=100.0,
        avg_price=10.0,
        rows=[{"price": 5.0, "amount_krw": 500.0}],
    )
    assert result["final_volume"] == 200.0
    assert result["final_cost_krw"] == 1500.0
    assert result["final_avg_price"] == 7.5


def test_user_tools_store_holding_and_plan(tmp_path):
    store = UserToolsStore(str(tmp_path / "journal.sqlite3"))
    holding = store.set_holding("KRW-B3", volume=1234.5, avg_price=0.777, exchange="UPBIT")
    assert holding["volume"] == 1234.5
    assert holding["avg_price"] == 0.777
    assert holding["exchange"] == "upbit"

    preserved = store.set_holding("KRW-B3", volume=1500.0, avg_price=0.7)
    assert preserved["exchange"] == "upbit"

    cleared = store.set_holding("KRW-B3", volume=1500.0, avg_price=0.7, exchange="")
    assert cleared["exchange"] is None

    with pytest.raises(ValueError, match="exchange must be one of"):
        store.set_holding("KRW-B3", volume=1.0, avg_price=1.0, exchange="okx")

    plan = store.set_plan(
        "KRW-B3",
        [
            {"price": 0.65, "amount_krw": 50_000},
            {"price": 0.55, "amount_krw": 70_000},
        ],
    )
    assert len(plan["rows"]) == 2
    assert store.get_plan("KRW-B3")["rows"][1]["amount_krw"] == 70_000
    store.close()


def test_user_tools_store_migrates_legacy_manual_holdings_schema(tmp_path):
    path = tmp_path / "legacy.sqlite3"
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
                ("KRW-BTC", 0.1, 100_000_000.0, 1234.0),
            )
    finally:
        conn.close()

    store = UserToolsStore(str(path))
    legacy = store.get_holding("KRW-BTC")
    assert legacy["volume"] == 0.1
    assert legacy["avg_price"] == 100_000_000.0
    assert legacy["exchange"] is None

    saved = store.set_holding(
        "KRW-BTC",
        volume=0.1,
        avg_price=100_000_000.0,
        exchange="bithumb",
    )
    assert saved["exchange"] == "bithumb"
    store.close()
