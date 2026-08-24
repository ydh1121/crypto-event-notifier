from pathlib import Path

from b3_trader.auto_demo import AutoPaperDemo, DemoStore, MIN_TURNOVER_24H, START_KRW


def test_demo_store_persists_separate_fills(tmp_path: Path):
    store = DemoStore(tmp_path / "demo.sqlite3")
    store.add_fill(
        market="KRW-AAA",
        symbol="AAA",
        side="buy",
        price=100.0,
        volume=10.0,
        krw=1000.0,
        realized_pnl=0.0,
        reason="test buy",
    )
    store.add_fill(
        market="KRW-AAA",
        symbol="AAA",
        side="sell",
        price=110.0,
        volume=10.0,
        krw=1100.0,
        realized_pnl=100.0,
        reason="test sell",
    )
    rows = store.fills()
    store.close()

    assert START_KRW == 10_000_000.0
    assert [row["side"] for row in rows] == ["buy", "sell"]
    assert rows[-1]["realized_pnl"] == 100.0


def test_rank_universe_filters_stables_and_low_liquidity():
    demo = AutoPaperDemo.__new__(AutoPaperDemo)
    demo.prices = {}
    rows = [
        {
            "market": "KRW-AAA",
            "trade_price": 100.0,
            "acc_trade_price_24h": MIN_TURNOVER_24H * 3,
            "signed_change_rate": 0.04,
        },
        {
            "market": "KRW-BBB",
            "trade_price": 50.0,
            "acc_trade_price_24h": MIN_TURNOVER_24H / 2,
            "signed_change_rate": 0.02,
        },
        {
            "market": "KRW-USDT",
            "trade_price": 1400.0,
            "acc_trade_price_24h": MIN_TURNOVER_24H * 20,
            "signed_change_rate": 0.001,
        },
        {
            "market": "KRW-CCC",
            "trade_price": 200.0,
            "acc_trade_price_24h": MIN_TURNOVER_24H * 4,
            "signed_change_rate": -0.01,
        },
    ]

    ranked, breadth = demo._rank_universe(rows)

    assert [row["market"] for row in ranked] == ["KRW-AAA", "KRW-CCC"]
    assert "KRW-USDT" not in [row["market"] for row in ranked]
    assert 0.0 <= breadth <= 100.0
    assert demo.prices["KRW-AAA"] == 100.0
