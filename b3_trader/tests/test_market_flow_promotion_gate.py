from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.market_flow_reaction import MarketFlowReactionStore
from b3_trader.market_flow_reliability import MarketFlowReliabilityStore
from b3_trader.market_flow_promotion_gate import (
    MarketFlowPromotionGateStore,
    OOS_MIN_PER_VENUE,
    OOS_MIN_POOLED,
)


def _prepare(path: Path) -> None:
    MarketFlowReactionStore(path).close()


def _insert_ready(
    path: Path,
    *,
    exchange: str,
    count: int,
    start_ts: float,
    positive_ratio: float,
    market: str = "KRW-ETH",
    window: str = "1m",
    evidence: str = "passive_sell_absorption_candidate",
    horizon: str = "15m",
    positive_return: float = 0.10,
    negative_return: float = -0.08,
) -> None:
    conn = sqlite3.connect(path)
    try:
        positive_count = int(round(count * positive_ratio))
        hypothesis_direction = -1 if evidence == "passive_sell_absorption_candidate" else 1
        for index in range(count):
            signal_ts = float(start_ts + index * 60.0)
            hypothesis_return = positive_return if index < positive_count else negative_return
            future_return = hypothesis_return * hypothesis_direction
            conn.execute(
                """INSERT INTO research_market_flow_reaction_mx(
                       exchange,market,signal_window_label,signal_feature_ts,signal_evidence_label,
                       signal_price,signal_delta_quote,flow_direction,hypothesis_direction,
                       horizon_label,horizon_seconds,reaction_start_ts,reaction_end_ts,
                       reaction_source_timeframe,reaction_source_interval_seconds,data_ready,status,
                       endpoint_candle_ts,endpoint_price,future_return_pct,flow_followthrough_return_pct,
                       hypothesis_directional_return_pct,source,received_at,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    exchange,market,window,signal_ts,evidence,
                    100.0,1_000_000.0,1,hypothesis_direction,
                    horizon,900.0,signal_ts,signal_ts + 900.0,"1m",60.0,1,"ready",
                    signal_ts + 840.0,100.0 + future_return,
                    future_return,future_return,hypothesis_return,
                    "price_flow_divergence+rest_ohlcv",signal_ts + 1000.0,1,1,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _compute_reliability(path: Path, now: float) -> dict:
    store = MarketFlowReliabilityStore(path)
    try:
        return store.compute(now=now)
    finally:
        store.close()


def _gate_audit(path: Path) -> dict:
    store = MarketFlowPromotionGateStore(path)
    try:
        return store.audit()
    finally:
        store.close()


def _seed_base_candidate(path: Path) -> float:
    _prepare(path)
    base_start = 1_800_000_000.0
    for exchange in ("bithumb", "upbit"):
        _insert_ready(
            path,
            exchange=exchange,
            count=60,
            start_ts=base_start,
            positive_ratio=0.75,
        )
    result = _compute_reliability(path, 1_900_000_000.0)
    assert result["promotion_ready_rows"] == 1
    assert result["promotion_gate"]["gates_started"] == 1
    audit = _gate_audit(path)
    assert audit["row_count"] == 1
    return float(audit["rows"][0]["cutoff_signal_ts"])


def test_base_promotion_freezes_forward_only_cutoff(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    cutoff = _seed_base_candidate(path)
    audit = _gate_audit(path)
    row = audit["rows"][0]
    assert cutoff == 1_800_000_000.0 + 59 * 60.0
    assert row["status"] == "collecting_oos"
    assert row["oos_pooled_sample_count"] == 0
    assert row["final_candidate_ready"] == 0
    assert audit["transition_count"] == 1
    assert audit["transitions"][0]["previous_status"] == "not_started"
    assert audit["transitions"][0]["new_status"] == "collecting_oos"


def test_pre_cutoff_rows_never_enter_oos_cohort(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _seed_base_candidate(path)
    for exchange in ("bithumb", "upbit"):
        _insert_ready(
            path,
            exchange=exchange,
            count=10,
            start_ts=1_700_000_000.0,
            positive_ratio=1.0,
        )
    _compute_reliability(path, 1_900_000_100.0)
    audit = _gate_audit(path)
    row = audit["rows"][0]
    assert row["oos_bithumb_sample_count"] == 0
    assert row["oos_upbit_sample_count"] == 0
    assert audit["forward_cutoff_count_mismatches"] == 0


def test_strictly_forward_oos_can_validate_final_candidate(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    cutoff = _seed_base_candidate(path)
    per_venue = max(OOS_MIN_PER_VENUE, OOS_MIN_POOLED // 2)
    for exchange in ("bithumb", "upbit"):
        _insert_ready(
            path,
            exchange=exchange,
            count=per_venue,
            start_ts=cutoff + 60.0,
            positive_ratio=0.80,
        )
    result = _compute_reliability(path, 1_900_001_000.0)
    assert result["promotion_gate"]["final_candidate_ready_rows"] == 1
    audit = _gate_audit(path)
    row = audit["rows"][0]
    assert row["oos_sample_ready"] == 1
    assert row["oos_direction_consistent"] == 1
    assert row["oos_pooled_sample_count"] >= OOS_MIN_POOLED
    assert float(row["oos_pooled_wilson_lower_pct"]) > 50.0
    assert row["final_candidate_ready"] == 1
    assert row["status"] == "oos_validated"
    assert audit["oos_contract_violations"] == 0
    assert audit["forward_cutoff_count_mismatches"] == 0
    assert audit["transition_count"] == 2


def test_cross_exchange_oos_disagreement_does_not_validate(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    cutoff = _seed_base_candidate(path)
    per_venue = max(OOS_MIN_PER_VENUE, OOS_MIN_POOLED // 2)
    _insert_ready(
        path,
        exchange="bithumb",
        count=per_venue,
        start_ts=cutoff + 60.0,
        positive_ratio=0.80,
    )
    _insert_ready(
        path,
        exchange="upbit",
        count=per_venue,
        start_ts=cutoff + 60.0,
        positive_ratio=0.30,
    )
    _compute_reliability(path, 1_900_001_000.0)
    audit = _gate_audit(path)
    row = audit["rows"][0]
    assert row["oos_sample_ready"] == 1
    assert row["oos_direction_consistent"] == 0
    assert row["final_candidate_ready"] == 0
    assert row["status"] == "oos_mixed"


def test_repeated_compute_does_not_duplicate_unchanged_transition(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _seed_base_candidate(path)
    _compute_reliability(path, 1_900_000_100.0)
    _compute_reliability(path, 1_900_000_200.0)
    audit = _gate_audit(path)
    assert audit["transition_count"] == 1
