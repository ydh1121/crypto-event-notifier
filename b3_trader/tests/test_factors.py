from b3_trader.factors import (
    OkxDerivativesProvider,
    eth_btc_relative_change_pct,
    score_basket,
)


def test_score_basket_rewards_relative_strength_and_breadth():
    result = score_basket(
        [4.0, 6.0, 2.0, -1.0],
        ["A", "B", "C", "D"],
        relative_to_pct=1.0,
    )
    assert result.score > 50
    assert result.positive_ratio == 0.75


def test_empty_basket_is_neutral():
    result = score_basket([], [])
    assert result.score == 50.0
    assert result.markets == ()


def test_extreme_positive_funding_is_penalized():
    assert OkxDerivativesProvider._funding_score(0.002) < 30
    assert OkxDerivativesProvider._funding_score(0.0001) > 50


def test_eth_btc_relative_change_is_derived_from_major_returns():
    # ETH +10%, BTC +5% means ETH/BTC rose by about 4.7619%.
    assert eth_btc_relative_change_pct(10.0, 5.0) == 4.7619
    assert eth_btc_relative_change_pct(-5.0, -5.0) == 0.0
