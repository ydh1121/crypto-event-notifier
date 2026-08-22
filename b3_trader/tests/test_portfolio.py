from b3_trader.portfolio import MultiPaperPortfolio


def test_multi_asset_portfolio_buy_sell():
    portfolio = MultiPaperPortfolio(start_krw=1_000_000, max_total_exposure_krw=500_000, max_daily_loss_pct=5)
    prices = {"KRW-B3": 1.0, "KRW-SEI": 500.0}
    fill = portfolio.buy(market="KRW-B3", price=1.0, order_krw=100_000, reason="test", max_position_krw=200_000, prices=prices)
    assert fill.volume == 100_000
    assert portfolio.position("KRW-B3").volume == 100_000
    assert portfolio.equity(prices) == 1_000_000
    sell = portfolio.sell_all("KRW-B3", 1.1, "test exit")
    assert sell is not None
    assert portfolio.cash_krw == 1_010_000
