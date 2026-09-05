import unittest

from b3_trader.strategy import B3Strategy, ExternalFactors


def candles(prices):
    # strategy expects Bithumb newest-first candle payloads
    return [{"trade_price": p} for p in reversed(prices)]


def orderbook(bid=120.0, ask=80.0):
    return {
        "orderbook_units": [
            {"bid_size": bid / 5.0, "ask_size": ask / 5.0}
            for _ in range(5)
        ]
    }


class StrategyTests(unittest.TestCase):
    def test_constructive_alt_regime_scores_higher(self):
        strategy = B3Strategy()
        bullish = strategy.score(
            candles([100, 101, 102, 103]),
            candles([100, 102, 104, 106]),
            candles([0.60, 0.65, 0.70, 0.68]),
            orderbook(130, 70),
            ExternalFactors(70, 75, 78, 65, 2),
        )
        bearish = strategy.score(
            candles([100, 98, 96, 95]),
            candles([100, 97, 94, 92]),
            candles([0.70, 0.67, 0.63, 0.60]),
            orderbook(70, 130),
            ExternalFactors(30, 30, 35, 25, -5),
        )
        self.assertGreater(bullish.regime_score, bearish.regime_score)

    def test_signal_is_bounded(self):
        signal = B3Strategy().score(
            candles([100, 101, 102]),
            candles([100, 101, 103]),
            candles([0.60, 0.70, 0.66]),
            orderbook(),
            ExternalFactors(),
        )
        self.assertGreaterEqual(signal.regime_score, 0)
        self.assertLessEqual(signal.regime_score, 100)
        self.assertGreaterEqual(signal.entry_score, 0)
        self.assertLessEqual(signal.entry_score, 100)


if __name__ == "__main__":
    unittest.main()
