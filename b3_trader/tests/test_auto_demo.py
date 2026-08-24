from pathlib import Path

from b3_trader.auto_demo import AutoPaperDemo, DemoStore, START_KRW


def test_demo_store_persists_separate_market_account_and_fills(tmp_path: Path):
    store = DemoStore(tmp_path / "demo.sqlite3")
    store.ensure_market("KRW-AAA", "AAA", "Alpha")
    store.ensure_market("KRW-BBB", "BBB", "Beta")
    accounts = store.all_accounts()
    assert accounts["KRW-AAA"]["cash_krw"] == START_KRW
    assert accounts["KRW-BBB"]["cash_krw"] == START_KRW

    store.add_fill(
        market="KRW-AAA",
        symbol="AAA",
        side="buy",
        price=100.0,
        volume=10.0,
        krw=1000.0,
        realized_pnl=0.0,
        reason="test buy",
        weight_pct=5.0,
    )
    store.add_fill(
        market="KRW-AAA",
        symbol="AAA",
        side="sell",
        price=110.0,
        volume=10.0,
        krw=1100.0,
        realized_pnl=100.0,
        return_pct=10.0,
        reason="test sell",
    )
    rows = store.fills("KRW-AAA")
    store.close()

    assert START_KRW == 10_000_000.0
    assert [row["side"] for row in rows] == ["buy", "sell"]
    assert rows[-1]["realized_pnl"] == 100.0
    assert rows[-1]["return_pct"] == 10.0


def test_rank_universe_keeps_all_valid_krw_markets():
    demo = AutoPaperDemo.__new__(AutoPaperDemo)
    demo.prices = {}
    demo.names = {"KRW-AAA": "Alpha", "KRW-USDT": "Tether", "KRW-LOW": "Low"}
    rows = [
        {
            "market": "KRW-AAA",
            "trade_price": 100.0,
            "acc_trade_price_24h": 9_000_000_000.0,
            "signed_change_rate": 0.04,
        },
        {
            "market": "KRW-USDT",
            "trade_price": 1400.0,
            "acc_trade_price_24h": 20_000_000_000.0,
            "signed_change_rate": 0.001,
        },
        {
            "market": "KRW-LOW",
            "trade_price": 2.0,
            "acc_trade_price_24h": 10_000_000.0,
            "signed_change_rate": -0.01,
        },
        {
            "market": "BTC-AAA",
            "trade_price": 1.0,
            "acc_trade_price_24h": 999_000_000_000.0,
            "signed_change_rate": 0.5,
        },
    ]

    ranked, breadth = demo._rank_universe(rows)
    markets = [row["market"] for row in ranked]

    assert set(markets) == {"KRW-AAA", "KRW-USDT", "KRW-LOW"}
    assert "BTC-AAA" not in markets
    assert 0.0 <= breadth <= 100.0
    assert demo.prices["KRW-AAA"] == 100.0


def test_exploration_weight_is_smaller_than_normal_buy():
    profile = {"base_weight_pct": 8.0}
    normal = AutoPaperDemo._suggested_weight(profile, 66.0, "buy")
    explore = AutoPaperDemo._suggested_weight(profile, 66.0, "explore")

    assert 2.5 <= explore < normal <= 15.0
