from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.market_flow_regime_history import HISTORY_BUCKET_SECONDS, MarketFlowRegimeHistoryStore
from b3_trader.market_flow_regime_stability import MarketFlowRegimeStabilityStore

BASE = 1_900_000_000.0


def _prepare(path: Path) -> None:
    MarketFlowRegimeHistoryStore(path).close()


def _insert_family_row(
    path: Path,
    *,
    snapshot_ts: float,
    confidence: float = 40.0,
    band: str = "directional_watch",
    representative_window: str = "1m",
    base_gate_started: int = 0,
    base_ready: int = 0,
    final_ready: int = 0,
) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO research_market_flow_family_history_mx(
                   snapshot_ts,market,regime_label,horizon_label,family_key,
                   representative_signal_window_label,representative_signal_evidence_label,
                   representative_confidence_pct,representative_confidence_band,
                   representative_base_gate_started,representative_base_promotion_ready,
                   representative_final_candidate_ready,source_received_at,recorded_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                snapshot_ts,"KRW-ETH","distribution_candidate","15m",
                "KRW-ETH|distribution_candidate|15m",representative_window,
                "passive_sell_absorption_candidate",confidence,band,base_gate_started,
                base_ready,final_ready,snapshot_ts + 10.0,snapshot_ts + 10.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _row(path: Path) -> dict:
    store = MarketFlowRegimeStabilityStore(path)
    try:
        store.compute(now=BASE + 100_000.0)
        value = store.conn.execute("SELECT * FROM research_market_flow_regime_stability_mx").fetchone()
        assert value is not None
        return dict(value)
    finally:
        store.close()


def test_less_than_four_contiguous_buckets_is_insufficient_history(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    for index in range(3):
        _insert_family_row(path,snapshot_ts=BASE + index * HISTORY_BUCKET_SECONDS)
    row = _row(path)
    assert row["contiguous_bucket_count"] == 3
    assert row["history_ready"] == 0
    assert row["stability_window_ready"] == 0
    assert row["stability_state"] == "insufficient_history"


def test_twelve_flat_buckets_are_stable(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    for index in range(12):
        _insert_family_row(path,snapshot_ts=BASE + index * HISTORY_BUCKET_SECONDS,confidence=40.0)
    row = _row(path)
    assert row["contiguous_bucket_count"] == 12
    assert row["history_ready"] == 1
    assert row["stability_window_ready"] == 1
    assert row["stability_state"] == "stable"
    assert row["degradation_level"] == "none"


def test_current_confidence_can_be_improving_only_after_full_stability_window(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    values = [30.0] * 8 + [34.0,35.0,36.0,40.0]
    for index, value in enumerate(values):
        _insert_family_row(path,snapshot_ts=BASE + index * HISTORY_BUCKET_SECONDS,confidence=value)
    row = _row(path)
    assert row["stability_window_ready"] == 1
    assert row["confidence_delta_vs_stability_median_pct"] >= 5.0
    assert row["short_confidence_range_pct"] < 10.0
    assert row["stability_state"] == "improving"


def test_oos_mixed_is_hard_degradation_even_with_high_confidence(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_family_row(
        path,snapshot_ts=BASE,confidence=79.0,band="oos_mixed",
        base_gate_started=1,base_ready=0,
    )
    row = _row(path)
    assert row["stability_state"] == "hard_degradation"
    assert row["degradation_level"] == "hard"
    assert row["degradation_reason"] == "forward_oos_mixed"


def test_started_oos_gate_with_current_base_loss_is_soft_degradation(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_family_row(
        path,snapshot_ts=BASE,confidence=55.0,band="base_validated_oos_collecting",
        base_gate_started=1,base_ready=0,
    )
    row = _row(path)
    assert row["stability_state"] == "soft_degradation"
    assert row["degradation_level"] == "soft"
    assert row["degradation_reason"] == "base_threshold_lost_after_oos_gate_started"


def test_history_gap_breaks_contiguous_count(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    for offset in (0,1,4,5):
        _insert_family_row(path,snapshot_ts=BASE + offset * HISTORY_BUCKET_SECONDS)
    row = _row(path)
    assert row["contiguous_bucket_count"] == 2
    assert row["history_ready"] == 0
    assert row["stability_state"] == "insufficient_history"


def test_stability_audit_is_shadow_only_and_contract_clean(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    for index in range(12):
        _insert_family_row(path,snapshot_ts=BASE + index * HISTORY_BUCKET_SECONDS,confidence=40.0)
    store = MarketFlowRegimeStabilityStore(path)
    try:
        store.compute(now=BASE + 100_000.0)
        audit = store.audit()
        assert audit["ok"] is True
        assert audit["row_count"] == 1
        assert audit["hard_degradation_contract_violations"] == 0
        assert audit["soft_degradation_contract_violations"] == 0
        assert audit["readiness_contract_violations"] == 0
        assert audit["safety_contract_violations"] == 0
        assert audit["suspicious_wiring_columns"] == []
        assert audit["paper_only"] is True
        assert audit["shadow_only"] is True
        assert audit["probability_interpretation"] is False
        assert audit["score_wired"] is False
        assert audit["can_place_orders"] is False
        assert audit["can_modify_strategy"] is False
        assert audit["raw_cloud_projection"] is False
    finally:
        store.close()
