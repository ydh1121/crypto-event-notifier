from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from b3_trader.market_flow_cost_edge import MarketFlowCostEdgeStore
from b3_trader.market_flow_event_cluster import MarketFlowEventClusterStore


def _prepare(path: Path) -> None:
    MarketFlowCostEdgeStore(path).close()


def _insert_cost(
    path: Path,
    *,
    exchange: str = "bithumb",
    market: str = "KRW-ETH",
    window: str = "1m",
    signal_ts: float,
    end_ts: float,
    direction: int = 1,
    adjusted: float = 0.10,
    gross: float | None = None,
    spread_bps: float = 2.0,
    horizon: str = "15m",
) -> None:
    evidence = "passive_buy_absorption_candidate" if direction > 0 else "passive_sell_absorption_candidate"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO research_market_flow_cost_edge_mx(
                   exchange,market,signal_window_label,signal_feature_ts,signal_evidence_label,
                   horizon_label,reaction_end_ts,hypothesis_direction,gross_hypothesis_return_pct,
                   entry_spread_bps,exit_spread_bps,roundtrip_spread_cost_bps,
                   spread_adjusted_hypothesis_return_pct,entry_relevant_top5_depth_quote,
                   exit_relevant_top5_depth_quote,reference_notional_krw,
                   max_reference_notional_share_pct,orderbook_friction_ready,
                   fee_model_ready,slippage_model_ready,full_cost_edge_ready,
                   full_cost_adjusted_return_pct,cost_status,source,received_at,
                   feature_version,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,0,0,0,NULL,
                        'spread_only_fee_and_historical_ladder_missing',
                        'flow_reaction+ws_orderbook_window',?,1,1)""",
            (
                exchange,market,window,signal_ts,evidence,horizon,end_ts,direction,
                adjusted if gross is None else gross,spread_bps,spread_bps,spread_bps,
                adjusted,5_000_000.0,5_000_000.0,50_000.0,1.0,end_ts + 1.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_overlapping_rows_collapse_to_fixed_anchor_event_and_keep_cross_exchange(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    t0 = 1_800_000_000.0
    end = t0 + 900.0
    _insert_cost(path,exchange="bithumb",window="1m",signal_ts=t0,end_ts=end,adjusted=0.10)
    _insert_cost(path,exchange="bithumb",window="5m",signal_ts=t0,end_ts=end,adjusted=9.99)
    _insert_cost(path,exchange="upbit",window="1m",signal_ts=t0 + 60,end_ts=t0 + 960,adjusted=0.20)
    _insert_cost(path,exchange="bithumb",window="1m",signal_ts=t0 + 840,end_ts=t0 + 1740,adjusted=8.88)
    _insert_cost(path,exchange="bithumb",window="1m",signal_ts=end,end_ts=end + 900,adjusted=-0.10)

    store = MarketFlowEventClusterStore(path)
    try:
        result = store.compute(now=end + 1000.0)
        audit = store.audit()
    finally:
        store.close()

    assert result["source_spread_ready_members"] == 5
    assert result["events_written"] == 2
    assert result["suppressed_overlap_members"] == 2
    assert result["cross_exchange_events"] == 1
    assert audit["ok"] is True
    first = audit["sample_events"][-1]
    assert first["event_anchor_signal_ts"] == pytest.approx(t0)
    assert first["event_anchor_end_ts"] == pytest.approx(end)
    assert first["member_count"] == 4
    assert first["representative_count"] == 2
    assert first["cross_exchange_confirmed"] == 1
    assert first["mean_spread_adjusted_hypothesis_return_pct"] == pytest.approx(0.15)


def test_fixed_anchor_does_not_transitively_chain_events(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    t0 = 1_800_000_000.0
    _insert_cost(path,signal_ts=t0,end_ts=t0 + 900,adjusted=0.10)
    _insert_cost(path,signal_ts=t0 + 840,end_ts=t0 + 1740,adjusted=0.20)
    _insert_cost(path,signal_ts=t0 + 1680,end_ts=t0 + 2580,adjusted=0.30)

    store = MarketFlowEventClusterStore(path)
    try:
        result = store.compute(now=t0 + 3000)
        audit = store.audit()
    finally:
        store.close()

    assert result["events_written"] == 2
    anchors = sorted(float(row["event_anchor_signal_ts"]) for row in audit["sample_events"])
    assert anchors == [t0, t0 + 1680]
    assert audit["fixed_anchor_overlap_violations"] == 0


def test_opposite_regimes_and_different_horizons_never_merge(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    t0 = 1_800_000_000.0
    _insert_cost(path,signal_ts=t0,end_ts=t0 + 900,direction=1,horizon="15m",adjusted=0.10)
    _insert_cost(path,signal_ts=t0,end_ts=t0 + 900,direction=-1,horizon="15m",adjusted=0.20)
    _insert_cost(path,signal_ts=t0,end_ts=t0 + 3600,direction=1,horizon="1h",adjusted=0.30)

    store = MarketFlowEventClusterStore(path)
    try:
        result = store.compute(now=t0 + 4000)
        audit = store.audit()
    finally:
        store.close()

    assert result["events_written"] == 3
    groups = {(row["regime_label"],row["horizon_label"]) for row in audit["sample_events"]}
    assert groups == {
        ("accumulation_candidate","15m"),
        ("distribution_candidate","15m"),
        ("accumulation_candidate","1h"),
    }


def test_representative_selection_ignores_later_better_performance(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    t0 = 1_800_000_000.0
    _insert_cost(path,exchange="bithumb",window="5m",signal_ts=t0,end_ts=t0 + 900,adjusted=-0.20)
    _insert_cost(path,exchange="bithumb",window="1m",signal_ts=t0,end_ts=t0 + 900,adjusted=-0.10)
    _insert_cost(path,exchange="bithumb",window="1m",signal_ts=t0 + 60,end_ts=t0 + 960,adjusted=5.00)

    store = MarketFlowEventClusterStore(path)
    try:
        store.compute(now=t0 + 1000)
        event = store.conn.execute(
            "SELECT * FROM research_market_flow_event_cluster_mx"
        ).fetchone()
        rep = store.conn.execute(
            """SELECT * FROM research_market_flow_event_cluster_member_mx
               WHERE representative_for_exchange=1"""
        ).fetchone()
        audit = store.audit()
    finally:
        store.close()

    assert rep is not None
    assert rep["signal_feature_ts"] == pytest.approx(t0)
    assert rep["signal_window_label"] == "1m"
    assert rep["spread_adjusted_hypothesis_return_pct"] == pytest.approx(-0.10)
    assert event["mean_spread_adjusted_hypothesis_return_pct"] == pytest.approx(-0.10)
    assert audit["representative_selection_violations"] == 0
