from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.market_flow_family_dedup import MarketFlowFamilyDedupStore
from b3_trader.market_flow_promotion_gate import MarketFlowPromotionGateStore
from b3_trader.market_flow_regime_confidence import MarketFlowRegimeConfidenceStore
from b3_trader.market_flow_regime_history import MarketFlowRegimeHistoryStore
from b3_trader.market_flow_reliability import MarketFlowReliabilityStore


def _prepare(path: Path) -> None:
    MarketFlowReliabilityStore(path).close()
    MarketFlowPromotionGateStore(path).close()
    MarketFlowRegimeConfidenceStore(path).close()
    MarketFlowFamilyDedupStore(path).close()
    MarketFlowRegimeHistoryStore(path).close()


def test_frozen_gate_survives_current_base_threshold_fallback(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO research_market_flow_reliability_mx(
                   market,signal_window_label,signal_evidence_label,horizon_label,
                   bithumb_sample_count,upbit_sample_count,pooled_sample_count,
                   bithumb_mean_hypothesis_return_pct,upbit_mean_hypothesis_return_pct,
                   pooled_mean_hypothesis_return_pct,bithumb_hit_rate_pct,upbit_hit_rate_pct,
                   pooled_hit_rate_pct,pooled_wilson_lower_pct,cross_exchange_direction_consistent,
                   observation_ready,promotion_ready,status,received_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "KRW-ETH","1m","passive_sell_absorption_candidate","15m",
                71,61,132,0.02,0.018,0.019,60.0,58.0,59.0,49.8,1,
                1,0,"directional_watch",1_900_000_000.0,
            ),
        )
        conn.execute(
            """INSERT INTO research_market_flow_promotion_gate_mx(
                   market,signal_window_label,signal_evidence_label,horizon_label,
                   gate_started_at,cutoff_signal_ts,
                   base_bithumb_sample_count,base_upbit_sample_count,base_pooled_sample_count,
                   oos_bithumb_sample_count,oos_upbit_sample_count,oos_pooled_sample_count,
                   oos_bithumb_mean_hypothesis_return_pct,oos_upbit_mean_hypothesis_return_pct,
                   oos_pooled_mean_hypothesis_return_pct,oos_bithumb_hit_rate_pct,oos_upbit_hit_rate_pct,
                   oos_pooled_hit_rate_pct,oos_pooled_wilson_lower_pct,oos_direction_consistent,
                   oos_sample_ready,final_candidate_ready,status,received_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "KRW-ETH","1m","passive_sell_absorption_candidate","15m",
                1_899_990_000.0,1_899_989_000.0,60,60,120,
                7,5,12,0.0,0.0,0.0,40.0,40.0,40.0,0.0,0,0,0,
                "collecting_oos",1_900_000_010.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    confidence = MarketFlowRegimeConfidenceStore(path)
    try:
        result = confidence.compute(now=1_900_000_020.0)
        assert result["ok"] is True
        audit = confidence.audit()
        assert audit["ok"] is True
        row = audit["rows"][0]
        assert row["base_gate_started"] == 1
        assert row["base_promotion_ready"] == 0
        assert row["promotion_gate_status"] == "collecting_oos"
        assert row["confidence_band"] == "base_validated_oos_collecting"
        assert audit["base_gate_semantics_violations"] == 0
    finally:
        confidence.close()

    family = MarketFlowFamilyDedupStore(path)
    try:
        family.compute(now=1_900_000_020.0)
        audit = family.audit()
        assert audit["ok"] is True
        row = audit["rows"][0]
        assert row["representative_base_gate_started"] == 1
        assert row["representative_base_promotion_ready"] == 0
        assert audit["base_gate_lifecycle_mismatches"] == 0
    finally:
        family.close()

    history = MarketFlowRegimeHistoryStore(path)
    try:
        history.capture(now=1_900_000_100.0)
        audit = history.audit()
        assert audit["ok"] is True
        confidence_row = audit["latest_confidence"][0]
        family_row = audit["latest_families"][0]
        assert confidence_row["base_gate_started"] == 1
        assert confidence_row["base_promotion_ready"] == 0
        assert family_row["representative_base_gate_started"] == 1
        assert family_row["representative_base_promotion_ready"] == 0
        assert audit["base_gate_semantics_violations"] == 0
    finally:
        history.close()
