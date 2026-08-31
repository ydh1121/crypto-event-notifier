from __future__ import annotations

import json
from pathlib import Path

from b3_trader.market_flow_orderbook_stream_store import MarketFlowOrderbookStreamStore
from b3_trader.market_flow_stream import _subscription, normalize_stream_orderbook
from b3_trader.market_flow_stream_store import MarketFlowStreamStore


def _snapshot(ts: float, *, bid_depth: float, ask_depth: float) -> dict:
    return {
        "exchange": "upbit",
        "market": "KRW-BTC",
        "source_ts": ts,
        "best_bid_price": 100.0,
        "best_ask_price": 101.0,
        "bid_depth_top5_quote": bid_depth,
        "ask_depth_top5_quote": ask_depth,
        "spread_bps": (1.0 / 100.5) * 10_000.0,
        "imbalance_pct": ((bid_depth - ask_depth) / (bid_depth + ask_depth)) * 100.0,
        "received_at": ts,
    }


def test_subscription_requests_realtime_trade_and_orderbook() -> None:
    for exchange in ("upbit", "bithumb"):
        payload = json.loads(_subscription(exchange, ("KRW-BTC", "KRW-ETH")))
        type_rows = [row for row in payload if isinstance(row, dict) and row.get("type")]
        assert [row["type"] for row in type_rows] == ["trade", "orderbook"]
        assert all(row["codes"] == ["KRW-BTC", "KRW-ETH"] for row in type_rows)
        flag = "is_only_realtime" if exchange == "upbit" else "isOnlyRealtime"
        assert all(row[flag] is True for row in type_rows)


def test_normalize_stream_orderbook_uses_top5_quote_depth() -> None:
    payload = {
        "type": "orderbook",
        "code": "KRW-BTC",
        "timestamp": 1_788_000_000_000,
        "orderbook_units": [
            {
                "ask_price": 101.0 + index,
                "bid_price": 100.0 - index,
                "ask_size": 2.0,
                "bid_size": 3.0,
            }
            for index in range(6)
        ],
    }
    row = normalize_stream_orderbook("upbit", payload, 1_788_000_001.0)
    assert row is not None
    assert row["source_ts"] == 1_788_000_000.0
    assert row["best_bid_price"] == 100.0
    assert row["best_ask_price"] == 101.0
    assert row["bid_depth_top5_quote"] == sum((100.0 - index) * 3.0 for index in range(5))
    assert row["ask_depth_top5_quote"] == sum((101.0 + index) * 2.0 for index in range(5))
    assert row["spread_bps"] > 0

    crossed = dict(payload)
    crossed["orderbook_units"] = [
        {"ask_price": 100.0, "bid_price": 101.0, "ask_size": 1.0, "bid_size": 1.0}
    ]
    assert normalize_stream_orderbook("upbit", crossed, 1_788_000_001.0) is None


def test_orderbook_store_samples_and_builds_replenishment_windows(tmp_path: Path) -> None:
    path = tmp_path / "orderbook.sqlite3"
    flow_store = MarketFlowStreamStore(path)
    book_store = MarketFlowOrderbookStreamStore(path)
    feature_ts = 1_788_000_600.0
    try:
        flow_store.mark_connected(
            "upbit",
            ["KRW-BTC"],
            process_started_at=feature_ts - 600,
            connected_since=feature_ts - 600,
            reconnects=0,
        )
        bid_depths = [1000.0, 900.0, 850.0, 950.0, 1100.0, 1000.0, 1200.0, 1150.0]
        ask_depths = [1000.0, 950.0, 900.0, 1000.0, 1050.0, 950.0, 1100.0, 1000.0]
        for index, (bid_depth, ask_depth) in enumerate(zip(bid_depths, ask_depths)):
            ts = feature_ts - 50 + index
            result = book_store.insert_snapshot(
                _snapshot(ts, bid_depth=bid_depth, ask_depth=ask_depth),
                received_at=ts,
            )
            assert result["accepted"] is True

        too_fast = book_store.insert_snapshot(
            _snapshot(feature_ts - 42.5, bid_depth=1200.0, ask_depth=900.0),
            received_at=feature_ts - 42.5,
        )
        assert too_fast["accepted"] is False
        assert too_fast["reason"] == "sample_interval"

        written = book_store.compute_window_features(now=feature_ts + 1)
        assert written == 6
        audit = book_store.audit()
        assert audit["tables_ready"] is True
        assert audit["minute_rows"] >= 1
        latest = {row["window_label"]: row for row in audit["latest_windows"]}
        one_minute = latest["1m"]
        assert one_minute["continuity_complete"] == 1
        assert one_minute["snapshot_count"] == 8
        assert one_minute["bid_same_best_pairs"] == 7
        assert one_minute["ask_same_best_pairs"] == 7
        assert one_minute["bid_refill_quote"] > 0
        assert one_minute["bid_depletion_quote"] > 0
        assert one_minute["ask_refill_quote"] > 0
        assert one_minute["ask_depletion_quote"] > 0
        assert one_minute["bid_replenishment_ratio"] is not None
        assert one_minute["ask_replenishment_ratio"] is not None
        assert one_minute["bid_refill_quote_per_second"] > 0
        assert one_minute["ask_refill_quote_per_second"] > 0
    finally:
        book_store.close()
        flow_store.close()


def test_orderbook_store_does_not_bridge_stale_or_changed_best_price(tmp_path: Path) -> None:
    path = tmp_path / "orderbook.sqlite3"
    store = MarketFlowOrderbookStreamStore(path)
    base = 1_788_001_200.0
    try:
        first = _snapshot(base, bid_depth=1000.0, ask_depth=1000.0)
        assert store.insert_snapshot(first, received_at=base)["accepted"] is True

        stale = _snapshot(base + 10, bid_depth=2000.0, ask_depth=500.0)
        result = store.insert_snapshot(stale, received_at=base + 10)
        assert result["accepted"] is True
        assert result["bid_refill_quote"] == 0.0
        assert result["ask_depletion_quote"] == 0.0

        changed = _snapshot(base + 11, bid_depth=2500.0, ask_depth=400.0)
        changed["best_bid_price"] = 99.0
        changed["best_ask_price"] = 102.0
        changed["spread_bps"] = ((102.0 - 99.0) / 100.5) * 10_000.0
        result = store.insert_snapshot(changed, received_at=base + 11)
        assert result["accepted"] is True
        assert result["bid_same_best_pair"] is False
        assert result["ask_same_best_pair"] is False
        assert result["bid_refill_quote"] == 0.0
        assert result["ask_depletion_quote"] == 0.0
    finally:
        store.close()
