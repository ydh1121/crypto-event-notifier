from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.market_flow_family_dedup import (
    AGGREGATION_METHOD,
    CORRELATION_POLICY,
    MarketFlowFamilyDedupStore,
)
from b3_trader.market_flow_regime_confidence import MarketFlowRegimeConfidenceStore


def _prepare(path: Path) -> None:
    MarketFlowRegimeConfidenceStore(path).close()


def _insert_confidence(
    path: Path,
    *,
    market: str = "KRW-ETH",
    window: str,
    evidence: str = "passive_sell_absorption_candidate",
    regime: str = "distribution_candidate",
    horizon: str = "15m",
    confidence: float,
    band: str,
    pooled: int,
    cross_consistent: int = 0,
    base_ready: int = 0,
    final_ready: int = 0,
) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO research_market_flow_regime_confidence_mx(
                   market,signal_window_label,signal_evidence_label,regime_label,horizon_label,
                   reliability_status,pooled_sample_count,cross_exchange_direction_consistent,
                   base_promotion_ready,final_candidate_ready,evidence_confidence_pct,
                   confidence_band,received_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                market,window,evidence,regime,horizon,band,pooled,cross_consistent,
                base_ready,final_ready,confidence,band,1_900_000_000.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _compute(path: Path) -> tuple[dict, dict]:
    store = MarketFlowFamilyDedupStore(path)
    try:
        result = store.compute(now=1_900_000_100.0)
        audit = store.audit()
        return result, audit
    finally:
        store.close()


def test_same_regime_and_horizon_fully_suppresses_correlated_siblings(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_confidence(path,window="1m",confidence=36.0,band="directional_watch",pooled=84,cross_consistent=1)
    _insert_confidence(path,window="5m",confidence=12.0,band="collecting",pooled=24)

    result, audit = _compute(path)

    assert result["families_written"] == 1
    assert result["members_written"] == 2
    assert result["suppressed_correlated_members"] == 1
    assert result["effective_confidence_sum_pct"] == 36.0
    assert result["raw_confidence_sum_pct"] == 48.0
    assert result["inflation_avoided_pct"] == 12.0
    row = audit["rows"][0]
    assert row["representative_signal_window_label"] == "1m"
    assert row["member_count"] == 2
    assert row["suppressed_member_count"] == 1
    assert row["effective_family_confidence_pct"] == 36.0
    members = audit["members"]
    assert sum(int(member["representative_member"]) for member in members) == 1
    assert sum(float(member["effective_weight"]) for member in members) == 1.0
    suppressed = [member for member in members if int(member["suppressed_correlated_member"]) == 1]
    assert len(suppressed) == 1
    assert suppressed[0]["effective_weight"] == 0.0


def test_higher_validation_stage_beats_higher_unvalidated_confidence(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_confidence(
        path,window="1m",confidence=79.0,band="base_validated_oos_collecting",pooled=160,
        cross_consistent=1,base_ready=1,final_ready=0,
    )
    _insert_confidence(
        path,window="5m",confidence=71.0,band="oos_validated_shadow",pooled=140,
        cross_consistent=1,base_ready=1,final_ready=1,
    )

    _, audit = _compute(path)
    row = audit["rows"][0]
    assert row["representative_signal_window_label"] == "5m"
    assert row["representative_final_candidate_ready"] == 1
    assert row["effective_family_confidence_pct"] == 71.0


def test_opposite_regimes_and_different_horizons_are_never_merged(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_confidence(path,window="1m",confidence=30.0,band="directional_watch",pooled=80,cross_consistent=1)
    _insert_confidence(
        path,window="5m",evidence="passive_buy_absorption_candidate",regime="accumulation_candidate",
        confidence=28.0,band="directional_watch",pooled=75,cross_consistent=1,
    )
    _insert_confidence(
        path,window="5m",horizon="1h",confidence=18.0,band="collecting",pooled=35,
    )

    result, audit = _compute(path)
    assert result["families_written"] == 3
    keys = {(row["regime_label"],row["horizon_label"]) for row in audit["rows"]}
    assert ("distribution_candidate","15m") in keys
    assert ("accumulation_candidate","15m") in keys
    assert ("distribution_candidate","1h") in keys


def test_audit_enforces_non_additive_shadow_contract(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_confidence(path,window="1m",confidence=20.0,band="collecting",pooled=40)
    _insert_confidence(path,window="5m",confidence=10.0,band="collecting",pooled=20)

    _, audit = _compute(path)
    assert audit["ok"] is True
    assert audit["representative_contract_violations"] == 0
    assert audit["effective_weight_contract_violations"] == 0
    assert audit["suppression_contract_violations"] == 0
    assert audit["summary_contract_violations"] == 0
    assert audit["member_count_mismatches"] == 0
    assert audit["wiring_columns"] == []
    assert audit["correlation_policy"] == CORRELATION_POLICY
    assert audit["aggregation_method"] == AGGREGATION_METHOD
    assert audit["empirical_correlation_estimated"] is False
    assert audit["probability_interpretation"] is False
    assert audit["score_wired"] is False
    assert audit["can_place_orders"] is False
