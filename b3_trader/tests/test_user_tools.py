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
    holding = store.set_holding("KRW-B3", volume=1234.5, avg_price=0.777)
    assert holding["volume"] == 1234.5
    assert holding["avg_price"] == 0.777

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
