from __future__ import annotations

import sqlite3

from b3_trader.market_feature_store import MarketFeatureStore
from b3_trader.market_return_windows import DAY_SECONDS, cumulative_returns, market_return_windows, prior_daily_returns


def test_prior_daily_returns_uses_completed_windows_before_live_24h() -> None:
    anchor = 10 * DAY_SECONDS
    rows = [
        {"ts": anchor - 6 * DAY_SECONDS, "price": 50.0},
        {"ts": anchor - 5 * DAY_SECONDS, "price": 60.0},
        {"ts": anchor - 4 * DAY_SECONDS, "price": 66.0},
        {"ts": anchor - 3 * DAY_SECONDS, "price": 60.0},
        {"ts": anchor - 2 * DAY_SECONDS, "price": 80.0},
        {"ts": anchor - 1 * DAY_SECONDS, "price": 100.0},
        {"ts": anchor, "price": 130.0},
    ]

    result = prior_daily_returns(rows, as_of_ts=anchor)

    assert result["d1_pct"] == 25.0
    assert round(result["d2_pct"], 6) == round((80.0 / 60.0 - 1.0) * 100.0, 6)
    assert round(result["d3_pct"], 6) == round((60.0 / 66.0 - 1.0) * 100.0, 6)
    assert result["d4_pct"] == 10.0
    assert result["d5_pct"] == 20.0
    assert result["coverage"] == 5


def test_prior_daily_returns_leaves_missing_window_null() -> None:
    anchor = 10 * DAY_SECONDS
    rows = [
        {"ts": anchor - 2 * DAY_SECONDS, "price": 80.0},
        {"ts": anchor - 1 * DAY_SECONDS, "price": 100.0},
    ]

    result = prior_daily_returns(rows, as_of_ts=anchor, max_sample_gap_seconds=3600.0)

    assert result["d1_pct"] == 25.0
    assert result["d2_pct"] is None
    assert result["coverage"] == 1


def test_cumulative_returns_are_separate_from_completed_daily_buckets() -> None:
    anchor = 40 * DAY_SECONDS
    rows = [
        {"ts": anchor - 30 * DAY_SECONDS, "price": 20.0},
        {"ts": anchor - 7 * DAY_SECONDS, "price": 50.0},
        {"ts": anchor - 6 * DAY_SECONDS, "price": 55.0},
        {"ts": anchor - 5 * DAY_SECONDS, "price": 60.0},
        {"ts": anchor - 4 * DAY_SECONDS, "price": 66.0},
        {"ts": anchor - 3 * DAY_SECONDS, "price": 60.0},
        {"ts": anchor - 2 * DAY_SECONDS, "price": 80.0},
        {"ts": anchor - 1 * DAY_SECONDS, "price": 100.0},
        {"ts": anchor, "price": 130.0},
    ]

    cumulative = cumulative_returns(rows, as_of_ts=anchor)
    combined = market_return_windows(rows, as_of_ts=anchor)

    assert cumulative["cum_1d_pct"] == 30.0
    assert round(cumulative["cum_3d_pct"], 6) == round((130.0 / 60.0 - 1.0) * 100.0, 6)
    assert round(cumulative["cum_5d_pct"], 6) == round((130.0 / 60.0 - 1.0) * 100.0, 6)
    assert cumulative["cum_7d_pct"] == 160.0
    assert cumulative["cum_30d_pct"] == 550.0
    assert cumulative["cumulative_coverage"] == 5
    assert combined["d1_pct"] == 25.0
    assert combined["cum_1d_pct"] == 30.0


def test_cumulative_returns_fail_closed_when_history_is_missing() -> None:
    anchor = 40 * DAY_SECONDS
    rows = [
        {"ts": anchor - 7 * DAY_SECONDS, "price": 50.0},
        {"ts": anchor - 1 * DAY_SECONDS, "price": 100.0},
        {"ts": anchor, "price": 130.0},
    ]

    result = cumulative_returns(rows, as_of_ts=anchor, max_sample_gap_seconds=3600.0)

    assert result["cum_1d_pct"] == 30.0
    assert result["cum_3d_pct"] is None
    assert result["cum_5d_pct"] is None
    assert result["cum_7d_pct"] == 160.0
    assert result["cum_30d_pct"] is None
    assert result["cumulative_coverage"] == 2


def test_market_feature_store_reuses_existing_market_memory_table() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE research_market_memory_mx(
            exchange TEXT,market TEXT,strategy TEXT,signal_ts REAL,price REAL
        )"""
    )
    anchor = 40 * DAY_SECONDS
    prices = {
        30: 20.0,
        7: 50.0,
        6: 55.0,
        5: 60.0,
        4: 66.0,
        3: 60.0,
        2: 80.0,
        1: 100.0,
        0: 130.0,
    }
    for day, price in prices.items():
        conn.execute(
            "INSERT INTO research_market_memory_mx(exchange,market,strategy,signal_ts,price) VALUES(?,?,?,?,?)",
            ("bithumb", "KRW-AAA", "adaptive", anchor - day * DAY_SECONDS, price),
        )
    conn.commit()

    store = MarketFeatureStore(conn)
    prior = store.prior_day_returns(
        exchange="bithumb",
        market="KRW-AAA",
        strategy="adaptive",
        as_of_ts=anchor,
    )
    combined = store.return_windows(
        exchange="bithumb",
        market="KRW-AAA",
        strategy="adaptive",
        as_of_ts=anchor,
    )

    assert prior["coverage"] == 5
    assert prior["d1_pct"] == 25.0
    assert combined["cumulative_coverage"] == 5
    assert combined["cum_1d_pct"] == 30.0
    assert combined["cum_30d_pct"] == 550.0
