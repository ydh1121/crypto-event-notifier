from __future__ import annotations

from pathlib import Path

from b3_trader.exchange_public import PublicMarket
from b3_trader.market_ohlcv_collector import MarketOhlcvCollector, TimeframeSpec, normalize_candles
from b3_trader.market_ohlcv_research_cycle import MarketOhlcvResearchCycle
from b3_trader.market_ohlcv_store import MarketOhlcvStore


class FakeAdapter:
    def __init__(self, exchange: str, markets: int = 10) -> None:
        self.exchange = exchange
        self._markets = [
            PublicMarket(exchange=exchange, market=f"KRW-C{index:02d}", symbol=f"C{index:02d}", name=f"Coin {index}")
            for index in range(markets)
        ]
        self.minute_calls: list[tuple[str, int, int]] = []
        self.day_calls: list[tuple[str, int]] = []

    def krw_markets(self) -> list[PublicMarket]:
        return list(self._markets)

    def krw_tickers(self) -> list[dict]:
        return []

    @staticmethod
    def _row(ts_text: str, price: float = 100.0) -> dict:
        return {
            "candle_date_time_utc": ts_text,
            "opening_price": price,
            "high_price": price + 2,
            "low_price": price - 2,
            "trade_price": price + 1,
            "candle_acc_trade_volume": 10.0,
            "candle_acc_trade_price": 1010.0,
        }

    def candles_minutes(self, market: str, unit: int = 5, count: int = 120) -> list[dict]:
        self.minute_calls.append((market, unit, count))
        return [self._row("2026-08-31T05:00:00")]

    def candles_days(self, market: str, count: int = 120) -> list[dict]:
        self.day_calls.append((market, count))
        return [self._row("2026-08-31T00:00:00")]

    def orderbook(self, market: str) -> dict:
        return {}


def test_normalize_candle_uses_utc_open_time_and_closed_flag() -> None:
    spec = TimeframeSpec("5m", 300, 5)
    rows = normalize_candles(
        [FakeAdapter._row("2026-08-31T05:00:00")],
        exchange="bithumb",
        market="KRW-AAA",
        timeframe=spec,
        now=1788153000.0,
    )
    assert len(rows) == 1
    assert rows[0]["timeframe"] == "5m"
    assert rows[0]["candle_ts"] == 1788152400.0
    assert rows[0]["open"] == 100.0
    assert rows[0]["close"] == 101.0
    assert rows[0]["base_volume"] == 10.0
    assert rows[0]["quote_volume"] == 1010.0
    assert rows[0]["is_closed"] is True


def test_store_prunes_to_bounded_bar_count(tmp_path: Path) -> None:
    store = MarketOhlcvStore(tmp_path / "ohlcv.sqlite3", retention_bars=400)
    try:
        rows = [
            {
                "exchange": "bithumb",
                "market": "KRW-AAA",
                "timeframe": "1m",
                "candle_ts": float(1_000_000 + index * 60),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "base_volume": 1.0,
                "quote_volume": 100.5,
                "is_closed": True,
                "source": "public_rest",
                "received_at": 2_000_000.0,
            }
            for index in range(450)
        ]
        assert store.upsert_rows(rows) == 450
        assert store.prune("bithumb", "KRW-AAA", "1m") == 50
        kept = store.rows("bithumb", "KRW-AAA", "1m", limit=500)
        assert len(kept) == 400
        assert kept[0]["candle_ts"] > kept[-1]["candle_ts"]
    finally:
        store.close()


def test_fetch_count_bridges_only_missing_history() -> None:
    assert MarketOhlcvCollector.fetch_count(latest_ts=0.0, now=10_000.0, seconds=60) == 200
    assert MarketOhlcvCollector.fetch_count(latest_ts=9_700.0, now=10_000.0, seconds=60) == 7
    assert MarketOhlcvCollector.fetch_count(latest_ts=9_900.0, now=10_000.0, seconds=300) == 3
    assert MarketOhlcvCollector.fetch_count(latest_ts=1.0, now=100_000.0, seconds=60) == 200


def test_cycle_rotates_eight_markets_per_exchange_and_six_timeframes(tmp_path: Path) -> None:
    store = MarketOhlcvStore(tmp_path / "ohlcv.sqlite3")
    clock = iter(float(index) for index in range(1000))
    collector = MarketOhlcvCollector(
        store,
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: next(clock),
    )
    bithumb = FakeAdapter("bithumb", markets=10)
    upbit = FakeAdapter("upbit", markets=10)
    cycle = MarketOhlcvResearchCycle(
        tmp_path / "ohlcv.sqlite3",
        store=store,
        adapters={"bithumb": bithumb, "upbit": upbit},
        collector=collector,
        state_path=tmp_path / "state.json",
    )
    try:
        result = cycle.run_once()
        assert result["paper_only"] is True
        assert result["can_place_orders"] is False
        assert result["database_scope"] == "research_market_ohlcv_mx_only"
        assert result["markets_processed"] == 16
        assert result["requests"] == 96
        assert result["failures"] == 0
        assert result["timeframes"] == ["1m", "5m", "15m", "1h", "4h", "1d"]
        assert len(bithumb.minute_calls) == 8 * 5
        assert len(bithumb.day_calls) == 8
        assert len(upbit.minute_calls) == 8 * 5
        assert len(upbit.day_calls) == 8

        second = cycle.run_once()
        assert second["markets_processed"] == 16
        second_markets = [row["market"] for row in second["exchanges"]["bithumb"]["markets"]]
        assert second_markets[:2] == ["KRW-C08", "KRW-C09"]
    finally:
        store.close()
