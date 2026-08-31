from __future__ import annotations

from pathlib import Path

from b3_trader.market_flow_stream import normalize_stream_trade
from b3_trader.market_flow_stream_store import MarketFlowStreamStore


def _trade(seq: int, ts: float, side: str, price: float = 100.0, volume: float = 1.0) -> dict:
    return {
        "exchange": "upbit",
        "market": "KRW-BTC",
        "sequential_id": str(seq),
        "trade_ts": ts,
        "trade_price": price,
        "trade_volume": volume,
        "quote_volume": price * volume,
        "aggressor_side": side,
        "side_source": "exchange",
        "received_at": ts,
    }


def test_normalize_stream_trade_requires_exchange_side_and_realtime() -> None:
    row = normalize_stream_trade(
        "upbit",
        {
            "type": "trade",
            "code": "KRW-BTC",
            "trade_price": 100.0,
            "trade_volume": 2.0,
            "ask_bid": "BID",
            "trade_timestamp": 1_788_000_000_000,
            "sequential_id": 123,
            "stream_type": "REALTIME",
        },
        1_788_000_001.0,
    )
    assert row is not None
    assert row["market"] == "KRW-BTC"
    assert row["aggressor_side"] == "BID"
    assert row["trade_ts"] == 1_788_000_000.0
    assert row["quote_volume"] == 200.0

    assert normalize_stream_trade(
        "upbit",
        {
            "type": "trade",
            "code": "KRW-BTC",
            "trade_price": 100.0,
            "trade_volume": 1.0,
            "ask_bid": "UNKNOWN",
            "trade_timestamp": 1_788_000_000_000,
            "sequential_id": 124,
        },
        1_788_000_001.0,
    ) is None
    assert normalize_stream_trade(
        "bithumb",
        {
            "type": "trade",
            "code": "KRW-BTC",
            "trade_price": 100.0,
            "trade_volume": 1.0,
            "ask_bid": "ASK",
            "trade_timestamp": 1_788_000_000_000,
            "sequential_id": 125,
            "stream_type": "SNAPSHOT",
        },
        1_788_000_001.0,
    ) is None


def test_stream_store_dedupes_and_builds_continuity_gated_windows(tmp_path: Path) -> None:
    path = tmp_path / "stream.sqlite3"
    store = MarketFlowStreamStore(path)
    now = 1_788_000_600.0
    connected_since = now - 10 * 60
    try:
        store.mark_connected(
            "upbit",
            ["KRW-BTC"],
            process_started_at=connected_since,
            connected_since=connected_since,
            reconnects=0,
        )
        rows = [
            _trade(1, now - 280, "BID", volume=2.0),
            _trade(2, now - 220, "ASK", volume=1.0),
            _trade(3, now - 50, "BID", volume=1.0),
        ]
        first = store.insert_trades(rows, received_at=now - 10)
        second = store.insert_trades(rows, received_at=now - 5)
        assert first["inserted"] == 3
        assert second["inserted"] == 0

        written = store.compute_window_features(now=now)
        assert written == 6
        audit = store.audit()
        assert audit["minute_rows"] >= 2
        assert audit["window_rows"] == 6
        latest = {row["window_label"]: row for row in audit["latest_windows"]}
        assert latest["1m"]["continuity_complete"] == 1
        assert latest["5m"]["continuity_complete"] == 1
        assert latest["15m"]["continuity_complete"] == 0
        assert latest["1h"]["continuity_complete"] == 0
        assert latest["5m"]["side_coverage_pct"] == 100.0
        assert latest["5m"]["session_cvd_quote"] == 200.0
    finally:
        store.close()


def test_reconnect_resets_cvd_anchor_and_window_continuity(tmp_path: Path) -> None:
    path = tmp_path / "stream.sqlite3"
    store = MarketFlowStreamStore(path)
    now = 1_788_001_200.0
    try:
        store.mark_connected(
            "upbit",
            ["KRW-BTC"],
            process_started_at=now - 1200,
            connected_since=now - 1200,
            reconnects=0,
        )
        store.insert_trades([_trade(1, now - 500, "BID")], received_at=now - 490)
        before = store.session("upbit", "KRW-BTC")
        assert before["session_cvd_quote"] == 100.0

        store.mark_disconnected("upbit", ["KRW-BTC"], disconnected_at=now - 30)
        store.mark_connected(
            "upbit",
            ["KRW-BTC"],
            process_started_at=now - 1200,
            connected_since=now - 20,
            reconnects=1,
        )
        after = store.session("upbit", "KRW-BTC")
        assert after["session_cvd_quote"] == 0.0
        assert after["connected_since"] == now - 20

        store.insert_trades([_trade(2, now - 10, "ASK")], received_at=now - 5)
        store.compute_window_features(now=now)
        audit = store.audit()
        latest = {row["window_label"]: row for row in audit["latest_windows"]}
        assert latest["1m"]["continuity_complete"] == 0
        assert latest["5m"]["continuity_complete"] == 0
        assert latest["1m"]["session_cvd_quote"] == -100.0
    finally:
        store.close()
