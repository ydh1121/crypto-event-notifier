from __future__ import annotations

from pathlib import Path

from b3_trader.multi_exchange_store import MultiExchangeStore
from b3_trader.strategy_lab import StrategyLabStore
from b3_trader.strategy_lab_custom import (
    ConfiguredStrategyLabRunner,
    create_custom_experiment,
    custom_experiments,
    set_custom_experiment_status,
)
from b3_trader.strategy_lab_market import read_strategy_lab_market


def _memory(store: MultiExchangeStore, *, idx: int, price: float) -> int:
    ts = 1_900_000_000.0 + idx
    cursor = store.conn.execute(
        """INSERT INTO research_market_memory_mx(
            ts,signal_ts,exchange,market,strategy,price,change_24h_pct,turnover_24h,liquidity_score,
            regime_score,entry_score,opportunity_score,suggested_weight_pct,trade_intent,
            asset_return_pct,pullback_pct,volatility_pct,orderbook_imbalance,fib_retrace,
            btc_return_pct,eth_return_pct,asset_vs_majors_pct,price_delta_pct,opportunity_delta,
            regime_delta,entry_delta,feature_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ts, ts, "bithumb", "KRW-BTC", "adaptive", price, 1.0, 5_000_000_000.0, 90.0,
            82.0, 84.0, 88.0, 8.0, "wait", 2.0, 8.0, 2.0, 0.12, 0.5,
            0.5, 0.8, 1.5, 0.0, 0.0, 0.0, 0.0, "{}",
        ),
    )
    store.conn.commit()
    return int(cursor.lastrowid)


def test_custom_experiment_is_exchange_scoped_and_starts_after_creation(tmp_path: Path) -> None:
    db = tmp_path / "paper.sqlite3"
    mx = MultiExchangeStore(db)
    first_id = _memory(mx, idx=1, price=100.0)
    second_id = _memory(mx, idx=2, price=101.0)
    mx.close()

    # Leave the shared Strategy Lab cursor deliberately behind the latest memory.
    lab = StrategyLabStore(db)
    first_pass = lab.process_exchange("bithumb", limit=1)
    assert first_pass["cursor_after"] == first_id
    lab.close()

    created = create_custom_experiment(
        exchange="bithumb",
        label="공격 + 분할 60/40",
        primary_style="aggressive",
        secondary_style="dca",
        mix_ratio=0.6,
        path=db,
    )
    assert created["seeded_markets"] == 1
    exp_id = created["experiment_id"]

    mx = MultiExchangeStore(db)
    third_id = _memory(mx, idx=3, price=102.0)
    mx.close()

    result = ConfiguredStrategyLabRunner(db).run_once()
    assert result["custom_experiment_count"] == 1

    conn = MultiExchangeStore(db)
    try:
        rows = conn.conn.execute(
            "SELECT exchange,style FROM strategy_lab_experiments WHERE style LIKE 'custom_%' ORDER BY exchange"
        ).fetchall()
        assert [(row["exchange"], row["style"]) for row in rows] == [("bithumb", created["style"])]
        trade_rows = conn.conn.execute(
            "SELECT source_memory_id,side FROM strategy_lab_trades WHERE experiment_id=? ORDER BY id",
            (exp_id,),
        ).fetchall()
        assert trade_rows
        # Row 2 existed before experiment creation and must never be replayed.
        assert all(int(row["source_memory_id"]) > second_id for row in trade_rows)
        assert int(trade_rows[0]["source_memory_id"]) == third_id
    finally:
        conn.close()

    market = read_strategy_lab_market("bithumb", "KRW-BTC", db)
    custom = [row for row in market["experiments"] if row["experiment_id"] == exp_id]
    assert len(custom) == 1
    assert custom[0]["custom"] is True
    assert custom[0]["primary_style"] == "aggressive"
    assert custom[0]["secondary_style"] == "dca"


def test_custom_experiment_pause_removes_it_from_processing(tmp_path: Path) -> None:
    db = tmp_path / "paper.sqlite3"
    mx = MultiExchangeStore(db)
    _memory(mx, idx=1, price=100.0)
    mx.close()

    created = create_custom_experiment(
        exchange="bithumb",
        label="보수 + 스윙",
        primary_style="conservative",
        secondary_style="swing",
        mix_ratio=0.5,
        path=db,
    )
    paused = set_custom_experiment_status(created["experiment_id"], "paused", db)
    assert paused["status"] == "paused"
    result = ConfiguredStrategyLabRunner(db).run_once()
    assert result["custom_experiment_count"] == 0
    custom = custom_experiments(db)
    assert len(custom) == 1
    assert custom[0]["status"] == "paused"
