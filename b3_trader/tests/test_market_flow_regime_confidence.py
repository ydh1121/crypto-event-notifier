from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

from b3_trader.market_flow_promotion_gate import MarketFlowPromotionGateStore
from b3_trader.market_flow_regime_confidence import MarketFlowRegimeConfidenceStore
from b3_trader.market_flow_reliability import MarketFlowReliabilityStore


def _prepare(path: Path) -> None:
    MarketFlowReliabilityStore(path).close()
    MarketFlowPromotionGateStore(path).close()
    MarketFlowRegimeConfidenceStore(path).close()


def _insert_reliability(
    path: Path,
    *,
    market: str = "KRW-ETH",
    window: str = "1m",
    evidence: str = "passive_sell_absorption_candidate",
    horizon: str = "15m",
    bithumb: int = 38,
    upbit: int = 32,
    pooled: int = 70,
    wilson: float = 55.5,
    consistent: int = 1,
    observation_ready: int = 1,
    promotion_ready: int = 0,
    status: str = "directional_watch",
) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO research_market_flow_reliability_mx(
                   market,signal_window_label,signal_evidence_label,horizon_label,
                   bithumb_sample_count,upbit_sample_count,pooled_sample_count,
                   bithumb_mean_hypothesis_return_pct,upbit_mean_hypothesis_return_pct,
                   pooled_mean_hypothesis_return_pct,bithumb_hit_rate_pct,upbit_hit_rate_pct,
                   pooled_hit_rate_pct,pooled_wilson_lower_pct,cross_exchange_direction_consistent,
                   observation_ready,promotion_ready,status,received_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                market,window,evidence,horizon,bithumb,upbit,pooled,
                0.05 if consistent else -0.01,0.06,0.055,
                65.0 if consistent else 45.0,66.0,65.5,wilson,consistent,
                observation_ready,promotion_ready,status,1_900_000_000.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_gate(
    path: Path,
    *,
    market: str = "KRW-ETH",
    window: str = "1m",
    evidence: str = "passive_sell_absorption_candidate",
    horizon: str = "15m",
    oos_bithumb: int = 5,
    oos_upbit: int = 5,
    oos_pooled: int = 10,
    oos_wilson: float = 0.0,
    oos_consistent: int = 0,
    final_ready: int = 0,
    status: str = "collecting_oos",
) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO research_market_flow_promotion_gate_mx(
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
                market,window,evidence,horizon,1_900_000_000.0,1_899_999_000.0,
                60,60,120,oos_bithumb,oos_upbit,oos_pooled,
                0.08 if oos_consistent else -0.01,0.07,0.075,
                70.0 if oos_consistent else 45.0,68.0,69.0,oos_wilson,oos_consistent,
                1 if oos_bithumb >= 20 and oos_upbit >= 20 and oos_pooled >= 50 else 0,
                final_ready,status,1_900_000_100.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _compute_rows(path: Path) -> list[dict]:
    store = MarketFlowRegimeConfidenceStore(path)
    try:
        result = store.compute(now=1_900_000_200.0)
        assert result["ok"] is True
        audit = store.audit()
        assert audit["ok"] is True
        return audit["rows"]
    finally:
        store.close()


def test_regime_mapping_and_multitimeframe_aggregation_stays_blocked(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_reliability(path,evidence="passive_buy_absorption_candidate",window="1m")
    _insert_reliability(path,evidence="passive_sell_absorption_candidate",window="5m")
    rows = _compute_rows(path)
    assert len(rows) == 2
    by_evidence = {row["signal_evidence_label"]: row for row in rows}
    assert by_evidence["passive_buy_absorption_candidate"]["regime_label"] == "accumulation_candidate"
    assert by_evidence["passive_sell_absorption_candidate"]["regime_label"] == "distribution_candidate"
    assert all(row["family_aggregation_blocked"] == 1 for row in rows)
    assert all(row["probability_interpretation"] == 0 for row in rows)


def test_directional_watch_is_capped_before_base_promotion(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_reliability(path,status="directional_watch",consistent=1,promotion_ready=0,wilson=55.5)
    row = _compute_rows(path)[0]
    assert row["confidence_band"] == "directional_watch"
    assert 0.0 < float(row["evidence_confidence_pct"]) <= 59.9
    assert float(row["directional_support_pct"]) == 55.5


def test_mixed_cross_exchange_cannot_borrow_wilson_support(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_reliability(path,status="mixed_cross_exchange",consistent=0,promotion_ready=0,wilson=75.0)
    row = _compute_rows(path)[0]
    assert row["confidence_band"] == "mixed_cross_exchange"
    assert float(row["directional_support_pct"]) == 0.0
    assert float(row["evidence_confidence_pct"]) <= 39.9


def test_base_validated_candidate_remains_below_final_oos_band(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_reliability(
        path,bithumb=60,upbit=60,pooled=120,wilson=60.0,
        consistent=1,promotion_ready=1,status="validated_candidate",
    )
    _insert_gate(path,oos_bithumb=5,oos_upbit=5,oos_pooled=10,status="collecting_oos")
    row = _compute_rows(path)[0]
    assert row["confidence_band"] == "base_validated_oos_collecting"
    assert row["base_promotion_ready"] == 1
    assert row["final_candidate_ready"] == 0
    assert float(row["evidence_confidence_pct"]) <= 79.9


def test_oos_validated_shadow_can_enter_high_confidence_band(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_reliability(
        path,bithumb=70,upbit=70,pooled=140,wilson=65.0,
        consistent=1,promotion_ready=1,status="validated_candidate",
    )
    _insert_gate(
        path,oos_bithumb=25,oos_upbit=25,oos_pooled=50,oos_wilson=65.0,
        oos_consistent=1,final_ready=1,status="oos_validated",
    )
    row = _compute_rows(path)[0]
    assert row["confidence_band"] == "oos_validated_shadow"
    assert row["final_candidate_ready"] == 1
    assert float(row["evidence_confidence_pct"]) >= 80.0


def test_reliability_compute_integrates_regime_confidence_after_promotion_gate() -> None:
    source = inspect.getsource(MarketFlowReliabilityStore.compute)
    promotion_call = source.index("promotion_gate.compute")
    confidence_call = source.index("regime_confidence.compute")
    assert promotion_call < confidence_call
    assert '"regime_confidence": regime_confidence_result' in source
