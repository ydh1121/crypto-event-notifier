from __future__ import annotations

from pathlib import Path

from b3_trader.market_flow_collector import MarketFlowCollector
from b3_trader.market_flow_store import MarketFlowStore


class FakeAdapter:
    exchange = "upbit"

    def __init__(self, trades: list[dict], orderbook: dict) -> None:
        self.trades = trades
        self.book = orderbook
        self.trade_calls = 0

    def recent_trades(self, market: str, count: int = 200, cursor: str | None = None) -> list[dict]:
        self.trade_calls += 1
        return list(self.trades)

    def orderbook(self, market: str) -> dict:
        return dict(self.book)


def _trade(seq: int, ts: float, price: float, volume: float, side: str) -> dict:
    return {
        "market": "KRW-AAA",
        "timestamp": int(ts * 1000),
        "trade_price": price,
        "trade_volume": volume,
        "ask_bid": side,
        "sequential_id": seq,
    }


def _book(ts: float) -> dict:
    return {
        "market": "KRW-AAA",
        "timestamp": int(ts * 1000),
        "orderbook_units": [
            {"bid_price": 99.0, "ask_price": 101.0, "bid_size": 5.0, "ask_size": 2.0},
            {"bid_price": 98.0, "ask_price": 102.0, "bid_size": 4.0, "ask_size": 3.0},
        ],
    }


def test_flow_uses_exchange_aggressor_side_and_dedupes(tmp_path: Path) -> None:
    path = tmp_path / "flow.sqlite3"
    store = MarketFlowStore(path)
    adapter = FakeAdapter(
        [
            _trade(3, 1000.0, 100.0, 2.0, "BID"),
            _trade(2, 990.0, 100.0, 1.0, "ASK"),
            _trade(1, 980.0, 100.0, 1.0, "BID"),
        ],
        _book(1001.0),
    )
    collector = MarketFlowCollector(store)
    try:
        first = collector.collect_market(adapter, "KRW-AAA", now=1002.0)
        second = collector.collect_market(adapter, "KRW-AAA", now=1003.0)
        audit = store.audit()
        assert first["rows_inserted"] == 3
        assert second["rows_inserted"] == 0
        assert audit["trade_rows"] == 3
        assert first["side_source"] == "exchange"
        assert first["side_coverage_pct"] == 100.0
        assert first["delta_quote"] == 200.0
        assert first["observed_cvd_quote"] == 200.0
        assert first["orderbook"]["spread_bps"] is not None
        assert first["orderbook"]["imbalance_5"] is not None
        assert first["paper_only"] is True
        assert first["score_wired"] is False
        assert first["can_place_orders"] is False
    finally:
        store.close()


def test_flow_does_not_advance_continuity_across_unbridged_gap(tmp_path: Path) -> None:
    path = tmp_path / "flow.sqlite3"
    store = MarketFlowStore(path)
    collector = MarketFlowCollector(store)
    try:
        first = FakeAdapter(
            [_trade(2, 1000.0, 100.0, 1.0, "BID"), _trade(1, 900.0, 100.0, 1.0, "ASK")],
            _book(1001.0),
        )
        initial = collector.collect_market(first, "KRW-AAA", now=1002.0)
        assert initial["cycle_continuity_complete"] is True
        assert initial["covered_through_ts"] == 1000.0

        gap = FakeAdapter(
            [_trade(4, 2000.0, 100.0, 1.0, "BID"), _trade(3, 1900.0, 100.0, 1.0, "ASK")],
            _book(2001.0),
        )
        later = collector.collect_market(gap, "KRW-AAA", now=2002.0)
        cursor = store.cursor("upbit", "KRW-AAA")
        assert later["cycle_continuity_complete"] is False
        assert later["recent_5m_continuity_complete"] is False
        assert later["covered_through_ts"] == 1000.0
        assert float(cursor["covered_through_ts"]) == 1000.0
    finally:
        store.close()


def test_flow_rejects_unknown_side_instead_of_guessing(tmp_path: Path) -> None:
    path = tmp_path / "flow.sqlite3"
    store = MarketFlowStore(path)
    adapter = FakeAdapter(
        [
            _trade(2, 1000.0, 100.0, 1.0, "UNKNOWN"),
            _trade(1, 990.0, 100.0, 1.0, "BID"),
        ],
        _book(1001.0),
    )
    collector = MarketFlowCollector(store)
    try:
        result = collector.collect_market(adapter, "KRW-AAA", now=1002.0)
        assert result["rows_observed"] == 1
        assert result["rows_inserted"] == 1
        assert result["side_source"] == "exchange"
        assert result["trade_count"] == 1
    finally:
        store.close()
