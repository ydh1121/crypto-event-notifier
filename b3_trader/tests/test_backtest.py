from b3_trader.backtest import align_histories


def _row(ts, price):
    return {"candle_date_time_utc": ts, "trade_price": price}


def test_align_histories_uses_intersection_in_time_order():
    btc = [_row("2026-01-01T00:00:00", 1), _row("2026-01-01T00:05:00", 2)]
    eth = [_row("2026-01-01T00:05:00", 3), _row("2026-01-01T00:10:00", 4)]
    b3 = [_row("2026-01-01T00:05:00", 5)]

    aligned = align_histories(btc, eth, b3)
    assert len(aligned) == 1
    assert aligned[0][2]["trade_price"] == 5
