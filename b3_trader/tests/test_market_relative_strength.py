from __future__ import annotations

from pathlib import Path

from b3_trader.market_ohlcv_store import MarketOhlcvStore
from b3_trader.market_relative_strength import MarketRelativeStrengthEngine


def _daily_rows(exchange: str, market: str, *, start_ts: float, days: int, daily_step: float) -> list[dict]:
    rows: list[dict] = []
    for day in range(days + 1):
        price = 100.0 + daily_step * day
        rows.append(
            {
                "exchange": exchange,
                "market": market,
                "timeframe": "1d",
                "candle_ts": start_ts + day * 86400.0,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "base_volume": 1.0,
                "quote_volume": price,
                "is_closed": day < days,
                "source": "public_rest",
                "received_at": start_ts + days * 86400.0,
            }
        )
    return rows


def test_relative_strength_compares_asset_to_btc_eth_and_ready_breadth(tmp_path: Path) -> None:
    store = MarketOhlcvStore(tmp_path / "relative.sqlite3")
    engine = MarketRelativeStrengthEngine(store.conn)
    start = 1_780_000_000.0
    try:
        store.upsert_rows(_daily_rows("bithumb", "KRW-BTC", start_ts=start, days=31, daily_step=1.0))
        store.upsert_rows(_daily_rows("bithumb", "KRW-ETH", start_ts=start, days=31, daily_step=1.5))
        store.upsert_rows(_daily_rows("bithumb", "KRW-AAA", start_ts=start, days=31, daily_step=3.0))
        for index in range(37):
            store.upsert_rows(
                _daily_rows(
                    "bithumb",
                    f"KRW-C{index:02d}",
                    start_ts=start,
                    days=31,
                    daily_step=0.5 + index * 0.02,
                )
            )

        result = engine.compute_exchange("bithumb", universe_count=50)
        assert result["status"] == "computed"
        assert result["features_written"] == 40 * 4
        assert result["breadth_ready_horizons"] == 4
        assert result["breadth"]["30"]["sample_count"] == 40
        assert result["breadth"]["30"]["coverage_pct"] == 80.0
        assert result["breadth"]["30"]["positive_pct"] == 100.0

        feature = engine.read_market("bithumb", "KRW-AAA")["horizons"]["30"]
        assert feature["breadth_ready"] == 1
        assert feature["asset_return_pct"] > feature["btc_return_pct"]
        assert feature["asset_return_pct"] > feature["eth_return_pct"]
        assert feature["vs_btc_pp"] > 0
        assert feature["vs_eth_pp"] > 0
        assert feature["breadth_median_return_pct"] is not None
        assert feature["vs_breadth_median_pp"] > 0
        assert feature["source_timeframe"] == "1d"
        assert feature["source_table"] == "research_market_ohlcv_mx"
    finally:
        store.close()


def test_breadth_remains_null_until_universe_coverage_gate_is_met(tmp_path: Path) -> None:
    store = MarketOhlcvStore(tmp_path / "relative.sqlite3")
    engine = MarketRelativeStrengthEngine(store.conn)
    start = 1_780_000_000.0
    try:
        store.upsert_rows(_daily_rows("upbit", "KRW-BTC", start_ts=start, days=31, daily_step=1.0))
        store.upsert_rows(_daily_rows("upbit", "KRW-ETH", start_ts=start, days=31, daily_step=1.5))
        for index in range(8):
            store.upsert_rows(
                _daily_rows("upbit", f"KRW-X{index:02d}", start_ts=start, days=31, daily_step=2.0)
            )

        result = engine.compute_exchange("upbit", universe_count=100)
        assert result["status"] == "computed"
        assert result["breadth_ready_horizons"] == 0
        assert result["breadth"]["30"]["sample_count"] == 10
        assert result["breadth"]["30"]["coverage_pct"] == 10.0
        assert result["breadth"]["30"]["positive_pct"] is None
        feature = engine.read_market("upbit", "KRW-X00")["horizons"]["30"]
        assert feature["breadth_ready"] == 0
        assert feature["breadth_positive_pct"] is None
        assert feature["breadth_median_return_pct"] is None
        assert feature["vs_breadth_median_pp"] is None
        assert feature["vs_btc_pp"] is not None
        assert feature["vs_eth_pp"] is not None
    finally:
        store.close()
