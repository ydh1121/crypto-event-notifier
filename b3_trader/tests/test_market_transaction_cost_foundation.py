from __future__ import annotations

from pathlib import Path

from b3_trader.auto_demo_v2 import MIN_ORDER_KRW
from b3_trader.market_fee_schedule import MarketFeeScheduleStore
from b3_trader.market_flow_cost_edge import MarketFlowCostEdgeStore
from b3_trader.market_flow_full_cost_edge import MarketFlowFullCostEdgeStore
from b3_trader.market_flow_stream import normalize_stream_orderbook
from b3_trader.market_orderbook_ladder import MarketOrderbookLadderStore


def _ladder_snapshot(exchange: str, market: str, ts: float) -> dict:
    return {
        "exchange": exchange,
        "market": market,
        "source_ts": ts,
        "bid_levels": [
            {"price": 100.0 - index, "size": 100.0}
            for index in range(5)
        ],
        "ask_levels": [
            {"price": 101.0 + index, "size": 100.0}
            for index in range(5)
        ],
        "received_at": ts,
    }


def test_normalize_orderbook_preserves_sorted_top5_ladder() -> None:
    payload = {
        "type": "orderbook",
        "code": "KRW-BTC",
        "timestamp": 1_788_000_000_000,
        "orderbook_units": [
            {
                "ask_price": 105.0 - index,
                "bid_price": 96.0 + index,
                "ask_size": 2.0 + index,
                "bid_size": 3.0 + index,
            }
            for index in range(6)
        ],
    }
    row = normalize_stream_orderbook("upbit", payload, 1_788_000_001.0)
    assert row is not None
    assert len(row["ask_levels"]) == 5
    assert len(row["bid_levels"]) == 5
    assert [level["price"] for level in row["ask_levels"]] == sorted(
        level["price"] for level in row["ask_levels"]
    )
    assert [level["price"] for level in row["bid_levels"]] == sorted(
        (level["price"] for level in row["bid_levels"]), reverse=True
    )
    assert row["best_ask_price"] == row["ask_levels"][0]["price"]
    assert row["best_bid_price"] == row["bid_levels"][0]["price"]


def test_ladder_store_keeps_latest_minute_snapshot_and_prior_only_boundary(tmp_path: Path) -> None:
    path = tmp_path / "ladder.sqlite3"
    store = MarketOrderbookLadderStore(path)
    boundary = 1_788_000_600.0
    try:
        first = _ladder_snapshot("upbit", "KRW-BTC", boundary - 4.0)
        second = _ladder_snapshot("upbit", "KRW-BTC", boundary - 1.0)
        assert store.insert_snapshot(first, received_at=boundary - 4.0)["accepted"] is True
        assert store.insert_snapshot(second, received_at=boundary - 1.0)["updated"] is True

        prior = store.prior_snapshot("upbit", "KRW-BTC", boundary)
        assert prior is not None
        assert prior["source_ts"] == boundary - 1.0
        assert prior["age_seconds"] == 1.0

        assert store.prior_snapshot("upbit", "KRW-BTC", boundary + 30.0) is None
        stale_boundary = boundary + 60.0
        assert store.prior_snapshot("upbit", "KRW-BTC", stale_boundary) is None
        audit = store.audit()
        assert audit["ok"] is True
        assert audit["historical_backfill"] is False
        assert audit["prior_only_minute_boundary"] is True
    finally:
        store.close()


def test_fee_catalog_is_forward_only_and_bithumb_profile_fails_closed(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "fees.sqlite3"
    store = MarketFeeScheduleStore(path)
    verified_at = 1_788_000_000.0
    monkeypatch.delenv("B3_BITHUMB_FEE_PROFILE", raising=False)
    try:
        assert store.ensure_current_catalog(now=verified_at) == 3
        assert store.resolve_taker_fee("upbit", "KRW-BTC", verified_at - 1.0) is None
        upbit = store.resolve_taker_fee("upbit", "KRW-BTC", verified_at + 1.0)
        assert upbit is not None
        assert upbit["profile"] == "standard"
        assert upbit["taker_fee_bps"] == 5.0
        assert store.resolve_taker_fee("bithumb", "KRW-BTC", verified_at + 1.0) is None

        store.set_active_profile("bithumb", "KRW", "coupon_0_04", now=verified_at + 2.0)
        bithumb = store.resolve_taker_fee("bithumb", "KRW-BTC", verified_at + 3.0)
        assert bithumb is not None
        assert bithumb["taker_fee_bps"] == 4.0
        assert bithumb["profile"] == "coupon_0_04"
    finally:
        store.close()


def test_full_cost_edge_requires_prior_ladders_and_versioned_fee(tmp_path: Path) -> None:
    path = tmp_path / "full-cost.sqlite3"
    signal_ts = 1_788_000_600.0
    end_ts = signal_ts + 15 * 60

    fee_store = MarketFeeScheduleStore(path)
    ladder_store = MarketOrderbookLadderStore(path)
    source_store = MarketFlowCostEdgeStore(path)
    try:
        fee_store.ensure_current_catalog(now=signal_ts - 120.0)
        ladder_store.insert_snapshot(
            _ladder_snapshot("upbit", "KRW-BTC", signal_ts - 1.0),
            received_at=signal_ts - 1.0,
        )
        ladder_store.insert_snapshot(
            _ladder_snapshot("upbit", "KRW-BTC", end_ts - 1.0),
            received_at=end_ts - 1.0,
        )
        source_store.conn.execute(
            """INSERT INTO research_market_flow_cost_edge_mx(
                   exchange,market,signal_window_label,signal_feature_ts,signal_evidence_label,
                   horizon_label,reaction_end_ts,hypothesis_direction,gross_hypothesis_return_pct,
                   reference_notional_krw,orderbook_friction_ready,fee_model_ready,
                   slippage_model_ready,full_cost_edge_ready,cost_status,source,received_at,
                   feature_version,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,1,0,0,0,?, 'test',?,1,1)""",
            (
                "upbit","KRW-BTC","1m",signal_ts,"passive_buy_absorption_candidate",
                "15m",end_ts,1,1.0,float(MIN_ORDER_KRW),
                "spread_only_fee_and_historical_ladder_missing",end_ts,
            ),
        )
        source_store.conn.commit()
    finally:
        source_store.close()
        ladder_store.close()
        fee_store.close()

    full_store = MarketFlowFullCostEdgeStore(path)
    try:
        result = full_store.compute(now=end_ts + 60.0)
        audit = full_store.audit()
        assert result["full_cost_ready_rows"] == 1
        assert result["status_counts"]["full_cost_ready"] == 1
        assert audit["ok"] is True
        assert audit["full_cost_ready_rows"] == 1
        row = audit["sample_ready_rows"][0]
        assert row["entry_ladder_source_ts"] < row["signal_feature_ts"]
        assert row["exit_ladder_source_ts"] < row["reaction_end_ts"]
        assert row["entry_ladder_age_seconds"] <= 5.0
        assert row["exit_ladder_age_seconds"] <= 5.0
        assert row["entry_fee_bps"] == 5.0
        assert row["exit_fee_bps"] == 5.0
        expected_cost = (
            row["roundtrip_spread_cost_bps"]
            + row["entry_slippage_bps"]
            + row["exit_slippage_bps"]
            + row["entry_fee_bps"]
            + row["exit_fee_bps"]
        )
        assert abs(row["total_transaction_cost_bps"] - expected_cost) < 1e-9
        assert abs(
            row["full_cost_adjusted_return_pct"]
            - (row["gross_hypothesis_return_pct"] - expected_cost / 100.0)
        ) < 1e-9
    finally:
        full_store.close()
