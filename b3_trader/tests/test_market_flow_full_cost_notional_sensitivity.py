from __future__ import annotations

from pathlib import Path

from b3_trader.auto_demo_v2 import MIN_ORDER_KRW
from b3_trader.market_fee_schedule import MarketFeeScheduleStore
from b3_trader.market_flow_full_cost_notional_sensitivity import (
    REFERENCE_NOTIONALS_KRW,
    MarketFlowFullCostNotionalSensitivityStore,
)
from b3_trader.market_orderbook_ladder import MarketOrderbookLadderStore


def _snapshot(ts: float, *, size: float = 10_000.0) -> dict:
    return {
        "exchange": "upbit",
        "market": "KRW-BTC",
        "source_ts": ts,
        "bid_levels": [
            {"price": 100.0 - index * 0.1, "size": size}
            for index in range(5)
        ],
        "ask_levels": [
            {"price": 100.2 + index * 0.1, "size": size}
            for index in range(5)
        ],
        "received_at": ts,
    }


def _seed_canonical(path: Path, *, size: float) -> tuple[float, float]:
    signal_ts = 1_788_000_600.0
    end_ts = signal_ts + 15 * 60
    fee = MarketFeeScheduleStore(path)
    ladder = MarketOrderbookLadderStore(path)
    try:
        fee.ensure_current_catalog(now=signal_ts - 120.0)
        ladder.insert_snapshot(_snapshot(signal_ts - 1.0, size=size), received_at=signal_ts - 1.0)
        ladder.insert_snapshot(_snapshot(end_ts - 1.0, size=size), received_at=end_ts - 1.0)
        entry = ladder.prior_snapshot("upbit", "KRW-BTC", signal_ts)
        exit_ = ladder.prior_snapshot("upbit", "KRW-BTC", end_ts)
        assert entry is not None and exit_ is not None
        entry_fill = ladder.estimate_buy(entry["ask_levels"], float(MIN_ORDER_KRW))
        exit_fill = ladder.estimate_sell(exit_["bid_levels"], float(MIN_ORDER_KRW))
        assert entry_fill is not None and exit_fill is not None
        spread = (float(ladder.spread_bps(entry)) + float(ladder.spread_bps(exit_))) / 2.0
        total_cost = spread + entry_fill["slippage_bps"] + exit_fill["slippage_bps"] + 10.0
        gross = 0.5
        adjusted = gross - total_cost / 100.0
    finally:
        ladder.close()
        fee.close()

    conn = __import__("sqlite3").connect(str(path))
    try:
        conn.execute(
            """CREATE TABLE research_market_flow_full_cost_edge_mx(
                   exchange TEXT,market TEXT,signal_window_label TEXT,signal_feature_ts REAL,
                   signal_evidence_label TEXT,horizon_label TEXT,reaction_end_ts REAL,
                   hypothesis_direction INTEGER,gross_hypothesis_return_pct REAL,
                   total_transaction_cost_bps REAL,full_cost_adjusted_return_pct REAL,
                   fee_model_ready INTEGER,ladder_slippage_ready INTEGER,full_cost_edge_ready INTEGER
               )"""
        )
        conn.execute(
            """INSERT INTO research_market_flow_full_cost_edge_mx VALUES(
                   'upbit','KRW-BTC','1m',?,'passive_buy_absorption_candidate','15m',?,1,?, ?,?,1,1,1
               )""",
            (signal_ts,end_ts,gross,total_cost,adjusted),
        )
        conn.commit()
    finally:
        conn.close()
    return total_cost, adjusted


def test_notional_sensitivity_matches_50k_and_cost_is_monotonic(tmp_path: Path) -> None:
    path = tmp_path / "sensitivity.sqlite3"
    expected_cost, expected_adjusted = _seed_canonical(path, size=10_000.0)
    store = MarketFlowFullCostNotionalSensitivityStore(path)
    try:
        result = store.compute(now=1_788_002_000.0)
        audit = store.audit()
        assert result["ok"] is True
        assert audit["ok"] is True
        assert audit["reference_notionals_krw"] == list(REFERENCE_NOTIONALS_KRW)
        assert audit["baseline_50k_mismatch_count"] == 0
        assert audit["cost_monotonicity_violations"] == 0
        assert audit["depth_monotonicity_violations"] == 0
        rows = store.conn.execute(
            """SELECT reference_notional_krw,total_transaction_cost_bps,
                      full_cost_adjusted_return_pct,full_cost_ready
               FROM research_market_flow_full_cost_notional_sensitivity_mx
               ORDER BY reference_notional_krw"""
        ).fetchall()
        assert len(rows) == len(REFERENCE_NOTIONALS_KRW)
        assert abs(float(rows[0][1]) - expected_cost) < 1e-6
        assert abs(float(rows[0][2]) - expected_adjusted) < 1e-6
        ready_costs = [float(row[1]) for row in rows if int(row[3]) == 1]
        assert ready_costs == sorted(ready_costs)
    finally:
        store.close()


def test_notional_sensitivity_fails_closed_when_top5_depth_is_insufficient(tmp_path: Path) -> None:
    path = tmp_path / "sensitivity-depth.sqlite3"
    _seed_canonical(path, size=1_100.0)
    store = MarketFlowFullCostNotionalSensitivityStore(path)
    try:
        result = store.compute(now=1_788_002_000.0)
        audit = store.audit()
        assert result["ok"] is True
        assert audit["ok"] is True
        baseline = store.conn.execute(
            """SELECT full_cost_ready FROM research_market_flow_full_cost_notional_sensitivity_mx
               WHERE reference_notional_krw=?""",
            (float(MIN_ORDER_KRW),),
        ).fetchone()
        large = store.conn.execute(
            """SELECT full_cost_ready,status FROM research_market_flow_full_cost_notional_sensitivity_mx
               WHERE reference_notional_krw=4500000"""
        ).fetchone()
        assert baseline is not None and int(baseline[0]) == 1
        assert large is not None and int(large[0]) == 0
        assert str(large[1]) == "insufficient_top5_depth"
    finally:
        store.close()
