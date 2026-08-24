from b3_trader.portfolio import MultiPaperPortfolio


def test_multi_asset_portfolio_buy_sell():
    portfolio = MultiPaperPortfolio(
        start_krw=1_000_000,
        max_total_exposure_krw=500_000,
        max_daily_loss_pct=5,
    )
    prices = {"KRW-B3": 1.0, "KRW-SEI": 500.0}
    fill = portfolio.buy(
        market="KRW-B3",
        price=1.0,
        order_krw=100_000,
        reason="test",
        max_position_krw=200_000,
        prices=prices,
    )
    assert fill.volume == 100_000
    assert portfolio.position("KRW-B3").volume == 100_000
    assert portfolio.equity(prices) == 1_000_000
    sell = portfolio.sell_all("KRW-B3", 1.1, "test exit")
    assert sell is not None
    assert portfolio.cash_krw == 1_010_000


def test_restore_from_persisted_fills():
    portfolio = MultiPaperPortfolio(
        start_krw=1_000_000,
        max_total_exposure_krw=500_000,
        max_daily_loss_pct=5,
    )
    portfolio.restore_from_fills(
        [
            {
                "market": "KRW-B3",
                "side": "buy",
                "price": 1.0,
                "volume": 100_000.0,
                "krw": 100_000.0,
                "reason": "entry 1",
            },
            {
                "market": "KRW-B3",
                "side": "buy",
                "price": 2.0,
                "volume": 50_000.0,
                "krw": 100_000.0,
                "reason": "entry 2",
            },
        ]
    )
    position = portfolio.position("KRW-B3")
    assert portfolio.cash_krw == 800_000
    assert position.volume == 150_000
    assert round(position.avg_price, 6) == round(200_000 / 150_000, 6)


def test_restore_completed_round_trip_keeps_realized_cash():
    portfolio = MultiPaperPortfolio(
        start_krw=1_000_000,
        max_total_exposure_krw=500_000,
        max_daily_loss_pct=5,
    )
    portfolio.restore_from_fills(
        [
            {"market": "KRW-B3", "side": "buy", "price": 1.0, "volume": 100.0, "krw": 100.0, "reason": "entry"},
            {"market": "KRW-B3", "side": "sell", "price": 1.2, "volume": 100.0, "krw": 120.0, "reason": "exit"},
        ]
    )
    assert portfolio.cash_krw == 1_000_020
    assert portfolio.position("KRW-B3").volume == 0
