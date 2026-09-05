from __future__ import annotations

from pathlib import Path

from b3_trader.multi_exchange_store import MultiExchangeStore
from b3_trader.strategy_lab import STYLE_SPECS, StrategyLabStore


def _memory(
    store: MultiExchangeStore,
    *,
    idx: int,
    price: float,
    regime: float = 76.0,
    entry: float = 76.0,
    opportunity: float = 82.0,
    pullback: float = 8.0,
    asset_return: float = 1.0,
) -> None:
    ts = 1_800_000_000.0 + idx
    store.conn.execute(
        """INSERT INTO research_market_memory_mx(
            ts,signal_ts,exchange,market,strategy,price,change_24h_pct,turnover_24h,liquidity_score,
            regime_score,entry_score,opportunity_score,suggested_weight_pct,trade_intent,
            asset_return_pct,pullback_pct,volatility_pct,orderbook_imbalance,fib_retrace,
            btc_return_pct,eth_return_pct,asset_vs_majors_pct,price_delta_pct,opportunity_delta,
            regime_delta,entry_delta,feature_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ts, ts, "bithumb", "KRW-BTC", "adaptive", price, 1.0, 5_000_000_000.0, 90.0,
            regime, entry, opportunity, 8.0, "wait", asset_return, pullback, 2.0, 0.12, 0.5,
            0.5, 0.8, 1.5, 0.0, 0.0, 0.0, 0.0, "{}",
        ),
    )
    store.conn.commit()


def test_strategy_lab_runs_six_isolated_styles_without_touching_active_accounts(tmp_path: Path) -> None:
    db = tmp_path / "paper.sqlite3"
    mx = MultiExchangeStore(db)
    mx.ensure_market("bithumb", "KRW-BTC", "adaptive", "BTC", "비트코인")
    active_before = mx.account("bithumb", "KRW-BTC", "adaptive")
    _memory(mx, idx=1, price=100.0)
    _memory(mx, idx=2, price=95.0)
    _memory(mx, idx=3, price=125.0)
    mx.close()

    lab = StrategyLabStore(db)
    result = lab.process_exchange("bithumb", limit=100)
    assert result["experiments"] == len(STYLE_SPECS)
    assert result["source_rows"] == 3

    experiments = lab.conn.execute(
        "SELECT experiment_id,style FROM strategy_lab_experiments WHERE exchange='bithumb' ORDER BY style"
    ).fetchall()
    assert len(experiments) == 6
    assert {row["style"] for row in experiments} == set(STYLE_SPECS)

    accounts = lab.conn.execute(
        "SELECT experiment_id,market,cash_krw,volume,closed_trades FROM strategy_lab_accounts WHERE exchange='bithumb'"
    ).fetchall()
    assert len(accounts) == 6
    assert {row["market"] for row in accounts} == {"KRW-BTC"}

    trades = lab.conn.execute(
        "SELECT experiment_id,side FROM strategy_lab_trades WHERE exchange='bithumb'"
    ).fetchall()
    assert any(row["side"] == "buy" for row in trades)
    assert any(row["side"] == "sell" for row in trades)

    metrics = lab.snapshot()["experiments"]
    bithumb_metrics = [row for row in metrics if row["exchange"] == "bithumb"]
    assert len(bithumb_metrics) == 6
    assert all(row["markets"] == 1 for row in bithumb_metrics)
    lab.close()

    mx = MultiExchangeStore(db)
    active_after = mx.account("bithumb", "KRW-BTC", "adaptive")
    assert active_after["cash_krw"] == active_before["cash_krw"]
    assert active_after["volume"] == active_before["volume"]
    mx.close()


def test_strategy_lab_cursor_prevents_duplicate_replay(tmp_path: Path) -> None:
    db = tmp_path / "paper.sqlite3"
    mx = MultiExchangeStore(db)
    _memory(mx, idx=1, price=100.0)
    _memory(mx, idx=2, price=120.0)
    mx.close()

    lab = StrategyLabStore(db)
    first = lab.process_exchange("bithumb", limit=100)
    first_trade_count = int(lab.conn.execute("SELECT COUNT(*) FROM strategy_lab_trades").fetchone()[0])
    second = lab.process_exchange("bithumb", limit=100)
    second_trade_count = int(lab.conn.execute("SELECT COUNT(*) FROM strategy_lab_trades").fetchone()[0])

    assert first["source_rows"] == 2
    assert second["source_rows"] == 0
    assert second_trade_count == first_trade_count
    lab.close()
