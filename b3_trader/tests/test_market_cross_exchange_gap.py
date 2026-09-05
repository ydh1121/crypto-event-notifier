from __future__ import annotations

from pathlib import Path

from b3_trader.market_cross_exchange_gap import MarketCrossExchangeGapEngine
from b3_trader.market_ohlcv_store import MarketOhlcvStore


def _row(exchange: str, market: str, ts: float, price: float) -> dict:
    return {
        "exchange": exchange,
        "market": market,
        "timeframe": "1m",
        "candle_ts": ts,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "base_volume": 1.0,
        "quote_volume": price,
        "is_closed": True,
        "source": "public_rest",
        "received_at": ts + 30.0,
    }


def test_gap_requires_exact_official_name_and_fresh_close(tmp_path: Path) -> None:
    store = MarketOhlcvStore(tmp_path / "gap.sqlite3")
    engine = MarketCrossExchangeGapEngine(store.conn)
    now = 2_000_000.0
    try:
        store.upsert_rows(
            [
                _row("bithumb", "KRW-AAA", now - 60, 100.0),
                _row("upbit", "KRW-AAA", now - 120, 102.0),
            ]
        )
        result = engine.compute(
            bithumb_names={"KRW-AAA": "Alpha Coin"},
            upbit_names={"KRW-AAA": "Alpha Coin"},
            now=now,
        )
        feature = engine.read_market("KRW-AAA")
        assert result["gap_ready_rows"] == 1
        assert feature["identity_verified"] == 1
        assert feature["identity_basis"] == "symbol+official_name_exact"
        assert feature["gap_ready"] == 1
        assert round(float(feature["upbit_vs_bithumb_pct"]), 8) == 2.0
        assert round(float(feature["absolute_gap_pct"]), 8) == 2.0
        assert float(feature["source_skew_seconds"]) == 60.0
    finally:
        store.close()


def test_gap_fails_closed_on_name_mismatch(tmp_path: Path) -> None:
    store = MarketOhlcvStore(tmp_path / "gap.sqlite3")
    engine = MarketCrossExchangeGapEngine(store.conn)
    now = 2_000_000.0
    try:
        store.upsert_rows(
            [
                _row("bithumb", "KRW-AAA", now - 60, 100.0),
                _row("upbit", "KRW-AAA", now - 60, 102.0),
            ]
        )
        result = engine.compute(
            bithumb_names={"KRW-AAA": "Alpha Coin"},
            upbit_names={"KRW-AAA": "Another Asset"},
            now=now,
        )
        feature = engine.read_market("KRW-AAA")
        assert result["identity_rejected_rows"] == 1
        assert feature["identity_verified"] == 0
        assert feature["gap_ready"] == 0
        assert feature["upbit_vs_bithumb_pct"] is None
        assert feature["bithumb_price"] is None
        assert feature["upbit_price"] is None
    finally:
        store.close()


def test_gap_fails_closed_on_stale_or_skewed_prices(tmp_path: Path) -> None:
    store = MarketOhlcvStore(tmp_path / "gap.sqlite3")
    engine = MarketCrossExchangeGapEngine(store.conn)
    now = 2_000_000.0
    try:
        store.upsert_rows(
            [
                _row("bithumb", "KRW-AAA", now - 60, 100.0),
                _row("upbit", "KRW-AAA", now - 500, 102.0),
                _row("bithumb", "KRW-BBB", now - 1_000, 50.0),
                _row("upbit", "KRW-BBB", now - 1_020, 51.0),
            ]
        )
        result = engine.compute(
            bithumb_names={"KRW-AAA": "Alpha Coin", "KRW-BBB": "Beta Coin"},
            upbit_names={"KRW-AAA": "Alpha Coin", "KRW-BBB": "Beta Coin"},
            now=now,
        )
        assert result["gap_ready_rows"] == 0
        assert result["stale_or_skewed_rows"] == 2
        assert engine.read_market("KRW-AAA")["gap_ready"] == 0
        assert engine.read_market("KRW-BBB")["gap_ready"] == 0
    finally:
        store.close()


def test_gap_audit_is_latest_only_and_score_unwired(tmp_path: Path) -> None:
    store = MarketOhlcvStore(tmp_path / "gap.sqlite3")
    engine = MarketCrossExchangeGapEngine(store.conn)
    now = 2_000_000.0
    try:
        store.upsert_rows(
            [
                _row("bithumb", "KRW-AAA", now - 60, 100.0),
                _row("upbit", "KRW-AAA", now - 60, 101.0),
            ]
        )
        names = {"KRW-AAA": "Alpha Coin"}
        engine.compute(bithumb_names=names, upbit_names=names, now=now)
        engine.compute(bithumb_names=names, upbit_names=names, now=now + 30)
        audit = engine.audit()
        assert audit["row_count"] == 1
        assert audit["identity_verified_rows"] == 1
        assert audit["gap_ready_rows"] == 1
        assert audit["paper_only"] is True
        assert audit["score_wired"] is False
        assert audit["can_place_orders"] is False
    finally:
        store.close()
