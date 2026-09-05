from b3_trader.risk import (
    ExecutionGuard,
    OrderRateLimiter,
    adaptive_order_krw,
    estimate_buy,
    recent_move_pct,
    spread_bps,
)


def book():
    return {
        "orderbook_units": [
            {"bid_price": 0.699, "bid_size": 100000, "ask_price": 0.701, "ask_size": 100000},
            {"bid_price": 0.698, "bid_size": 100000, "ask_price": 0.702, "ask_size": 100000},
        ]
    }


def candles(values):
    # Bithumb REST is newest first.
    return [{"trade_price": value} for value in reversed(values)]


def test_spread_and_market_buy_estimate():
    ob = book()
    assert 20 < spread_bps(ob) < 40
    fill, slip = estimate_buy(ob, 50_000)
    assert fill >= 0.701
    assert slip >= 0


def test_flash_crash_blocks_new_buy():
    limiter = OrderRateLimiter(2, 8)
    guard = ExecutionGuard(
        max_spread_bps=50,
        max_slippage_bps=50,
        btc_flash_crash_pct=-3,
        btc_flash_window_candles=3,
        rate_limiter=limiter,
    )
    risk = guard.evaluate_buy(
        orderbook=book(),
        btc_candles=candles([100, 99, 98, 96]),
        order_krw=10_000,
        now=1000,
    )
    assert not risk.allowed
    assert risk.btc_flash_move_pct <= -3


def test_rate_limit_blocks_burst():
    limiter = OrderRateLimiter(1, 8)
    limiter.record(1000)
    allowed, _ = limiter.allowed(1020)
    assert not allowed


def test_adaptive_size_is_bounded():
    weak = adaptive_order_krw(
        50_000,
        regime_score=60,
        entry_score=60,
        min_multiplier=0.6,
        max_multiplier=1.25,
    )
    strong = adaptive_order_krw(
        50_000,
        regime_score=90,
        entry_score=90,
        min_multiplier=0.6,
        max_multiplier=1.25,
    )
    assert 30_000 <= weak <= 62_500
    assert 30_000 <= strong <= 62_500
    assert strong > weak


def test_recent_move_pct_uses_requested_window():
    move = recent_move_pct(candles([100, 101, 102, 98]), 2)
    assert round(move, 3) == round((98 / 101 - 1) * 100, 3)
