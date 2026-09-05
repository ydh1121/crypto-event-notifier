from __future__ import annotations

from pathlib import Path

from b3_trader.scoped_paper_store import ScopedPaperStore


def _insert_memory(
    store: ScopedPaperStore,
    *,
    ts: float,
    price: float,
    feature: str = '{"large":"payload"}',
) -> None:
    store.conn.execute(
        """
        INSERT INTO research_market_memory_mx(
            ts,
            signal_ts,
            exchange,
            market,
            strategy,
            price,
            change_24h_pct,
            turnover_24h,
            liquidity_score,
            regime_score,
            entry_score,
            opportunity_score,
            suggested_weight_pct,
            trade_intent,
            feature_json
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            ts,
            ts,
            "upbit",
            "KRW-BTC",
            "adaptive",
            price,
            0.0,
            1.0,
            50.0,
            50.0,
            50.0,
            50.0,
            0.0,
            "wait",
            feature,
        ),
    )


def _insert_equity(
    store: ScopedPaperStore,
    *,
    ts: float,
    equity: float,
) -> None:
    store.conn.execute(
        """
        INSERT INTO research_equity_mx(
            ts,
            exchange,
            market,
            strategy,
            equity_krw,
            return_pct,
            cash_krw,
            position_value_krw
        )
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            ts,
            "upbit",
            "KRW-BTC",
            "adaptive",
            equity,
            0.0,
            equity,
            0.0,
        ),
    )


def test_runtime_history_has_true_seven_day_horizon_and_no_features(
    tmp_path: Path,
) -> None:
    db = tmp_path / "runtime.sqlite3"

    store = ScopedPaperStore(
        "upbit",
        "adaptive",
        path=db,
    )

    now = 3_600_000_000.0

    six_days = now - 6 * 86400 + 600
    five_days_a = now - 5 * 86400 + 600
    five_days_b = now - 5 * 86400 + 1200

    recent_a = now - 23 * 3600 + 60
    recent_b = now - 23 * 3600 + 120

    outside_horizon = now - 8 * 86400

    try:
        _insert_memory(store, ts=six_days, price=1.0)
        _insert_memory(store, ts=five_days_a, price=2.0)
        _insert_memory(store, ts=five_days_b, price=3.0)
        _insert_memory(store, ts=recent_a, price=4.0)
        _insert_memory(store, ts=recent_b, price=5.0)
        _insert_memory(store, ts=outside_horizon, price=999.0)

        _insert_equity(store, ts=six_days, equity=10_000_001.0)
        _insert_equity(store, ts=five_days_a, equity=10_000_002.0)
        _insert_equity(store, ts=five_days_b, equity=10_000_003.0)
        _insert_equity(store, ts=recent_a, equity=10_000_004.0)
        _insert_equity(store, ts=recent_b, equity=10_000_005.0)
        _insert_equity(store, ts=outside_horizon, equity=99_000_000.0)

        store.conn.commit()

        result = store.runtime_history(
            "KRW-BTC",
            now=now,
        )

    finally:
        store.conn.close()

    memory = result["market_memory"]
    equity = result["equity_history"]

    memory_ts = [float(row["ts"]) for row in memory]
    equity_ts = [float(row["ts"]) for row in equity]

    assert six_days in memory_ts
    assert six_days in equity_ts

    assert outside_horizon not in memory_ts
    assert outside_horizon not in equity_ts

    assert five_days_a not in memory_ts
    assert five_days_b in memory_ts

    assert five_days_a not in equity_ts
    assert five_days_b in equity_ts

    assert recent_a in memory_ts
    assert recent_b in memory_ts

    assert recent_a in equity_ts
    assert recent_b in equity_ts

    assert all("features" not in row for row in memory)
    assert all("feature_json" not in row for row in memory)

    assert memory_ts == sorted(memory_ts)
    assert equity_ts == sorted(equity_ts)


def test_standard_market_detail_query_still_requests_feature_json() -> None:
    source = Path(
        "b3_trader/scoped_paper_store.py"
    ).read_text(encoding="utf-8")

    start = source.index(
        "    def market_detail("
    )

    market_detail_source = source[start:]

    assert "feature_json" in market_detail_source
    assert 'item["features"]' in market_detail_source
