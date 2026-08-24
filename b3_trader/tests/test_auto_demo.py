from pathlib import Path

from b3_trader.asset_strategy import AssetSignal
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


def test_dynamic_trade_plan_exposes_entry_rounds_target_stop_and_trailing(tmp_path: Path):
    store = DemoStore(tmp_path / "demo.sqlite3")
    store.ensure_market("KRW-AAA", "AAA", "Alpha")
    account = store.all_accounts()["KRW-AAA"]
    account["cash_krw"] = 8_000_000.0
    account["volume"] = 20_000.0
    account["avg_price"] = 100.0
    account["peak_price"] = 107.0
    account["last_buy_at"] = 0.0
    store.save_account(account)
    store.add_fill(
        market="KRW-AAA",
        symbol="AAA",
        side="buy",
        price=100.0,
        volume=20_000.0,
        krw=2_000_000.0,
        realized_pnl=0.0,
        reason="seed",
        weight_pct=20.0,
    )
    profile = store.all_profiles()["KRW-AAA"]
    profile["market"] = "KRW-AAA"
    signal = AssetSignal(
        regime_score=65.0,
        entry_score=63.0,
        btc_return_pct=1.0,
        eth_return_pct=1.2,
        asset_return_pct=2.0,
        eth_vs_btc_pct=0.2,
        asset_vs_majors_pct=0.9,
        orderbook_imbalance=0.08,
        pullback_pct=4.0,
        volatility_pct=2.0,
        fib_retrace=0.5,
        action="WATCH",
        reason="test",
    )
    demo = AutoPaperDemo.__new__(AutoPaperDemo)
    demo.store = store

    plan = demo._build_trade_plan(account, profile, signal, 66.0, 106.0, "hold")
    store.close()

    assert plan["current_price"] == 106.0
    assert plan["position_avg_price"] == 100.0
    assert 3 <= plan["expected_total_entries"] <= 8
    assert plan["completed_entries"] == 1
    assert plan["next_add_price"] < 100.0
    assert plan["target_price"] > 100.0
    assert plan["hard_stop_price"] < 100.0
    assert plan["trailing_stop_price"] > 0.0
    assert plan["target_is_dynamic"] is True


def test_leaderboard_can_return_more_than_old_top_60_limit(tmp_path: Path):
    store = DemoStore(tmp_path / "demo.sqlite3")
    for index in range(75):
        store.ensure_market(f"KRW-C{index}", f"C{index}", f"Coin {index}")
    rows = store.leaderboard(5000)
    store.close()

    assert len(rows) == 75


def test_market_memory_accumulates_scan_features_for_ai_analysis(tmp_path: Path):
    store = DemoStore(tmp_path / "demo.sqlite3")
    store.ensure_market("KRW-AAA", "AAA", "Alpha")

    def save(ts: float, price: float, opportunity: float) -> None:
        store.save_signal(
            {
                "market": "KRW-AAA",
                "symbol": "AAA",
                "ts": ts,
                "price": price,
                "turnover_24h": 1_000_000_000.0,
                "change_24h_pct": 3.2,
                "liquidity_score": 70.0,
                "regime_score": 62.0,
                "entry_score": 58.0,
                "opportunity_score": opportunity,
                "strategy_action": "WATCH",
                "trade_intent": "wait",
                "suggested_weight_pct": 7.5,
                "reason": "test",
                "signal": {
                    "asset_return_pct": 2.5,
                    "pullback_pct": 4.2,
                    "volatility_pct": 1.8,
                    "orderbook_imbalance": 0.12,
                    "fib_retrace": 0.5,
                    "btc_return_pct": 0.8,
                    "eth_return_pct": 1.0,
                    "asset_vs_majors_pct": 1.6,
                    "trade_plan": {"target_price": 120.0},
                },
            }
        )

    save(1000.0, 100.0, 60.0)
    save(1010.0, 102.0, 64.0)
    detail = store.market_detail("KRW-AAA")
    store.close()

    assert detail["market_memory_count"] == 2
    assert len(detail["market_memory"]) == 2
    assert detail["market_memory"][-1]["price"] == 102.0
    assert detail["market_memory"][-1]["price_delta_pct"] > 1.9
    assert detail["market_memory"][-1]["opportunity_delta"] == 4.0
    assert detail["market_memory"][-1]["features"]["trade_plan"]["target_price"] == 120.0


def test_completed_trade_without_position_is_classified_as_waiting(tmp_path: Path):
    store = DemoStore(tmp_path / "demo.sqlite3")
    store.ensure_market("KRW-AAA", "AAA", "Alpha")
    store.conn.execute("UPDATE research_profiles SET closed_trades=2,wins=1 WHERE market='KRW-AAA'")
    store.conn.commit()
    row = store.leaderboard(10)[0]
    store.close()

    assert row["has_position"] is False
    assert row["state_class"] == "completed_waiting"
    assert row["state_label"] == "매매 완료 · 대기"
