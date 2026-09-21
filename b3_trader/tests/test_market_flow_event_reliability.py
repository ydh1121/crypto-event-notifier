from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.market_flow_event_cluster import (
    CLUSTER_POLICY,
    REPRESENTATIVE_POLICY,
    MarketFlowEventClusterStore,
)
from b3_trader.market_flow_event_reliability import MarketFlowEventReliabilityStore


def _prepare(path: Path) -> None:
    MarketFlowEventClusterStore(path).close()


def _insert_event(
    path: Path,
    *,
    index: int,
    event_return: float,
    cross: bool = True,
    bithumb_return: float | None = None,
    upbit_return: float | None = None,
    market: str = "KRW-BTC",
    regime: str = "distribution_candidate",
    horizon: str = "15m",
) -> None:
    anchor = 1_800_000_000.0 + index * 1_000.0
    event_id = f"{market}|{regime}|{horizon}|{anchor:.6f}"
    if cross:
        b = event_return if bithumb_return is None else bithumb_return
        u = event_return if upbit_return is None else upbit_return
        event_return = (b + u) / 2.0
        exchanges = [("bithumb", b), ("upbit", u)]
    else:
        exchanges = [("bithumb", event_return)]
    evidence = (
        "passive_buy_absorption_candidate"
        if regime == "accumulation_candidate"
        else "passive_sell_absorption_candidate"
    )
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO research_market_flow_event_cluster_mx(
                   event_id,market,regime_label,horizon_label,event_anchor_signal_ts,event_anchor_end_ts,
                   member_count,representative_count,exchange_count,cross_exchange_confirmed,
                   exchanges_json,signal_windows_json,mean_gross_hypothesis_return_pct,
                   mean_roundtrip_spread_cost_bps,mean_spread_adjusted_hypothesis_return_pct,
                   spread_adjusted_positive,max_reference_notional_share_pct,cluster_policy,
                   representative_policy,independence_claim,pseudo_replication_reduced,source,
                   received_at,feature_version,schema_version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?,?,?,0,1,
                        'market_flow_cost_edge',?,1,1)""",
            (
                event_id,market,regime,horizon,anchor,anchor + 900.0,len(exchanges),len(exchanges),
                len(exchanges),1 if cross else 0,
                '["bithumb", "upbit"]' if cross else '["bithumb"]','["1m"]',
                event_return + 0.01,1.0,event_return,1 if event_return > 0 else 0,0.1,
                CLUSTER_POLICY,REPRESENTATIVE_POLICY,anchor + 901.0,
            ),
        )
        for exchange, adjusted in exchanges:
            conn.execute(
                """INSERT INTO research_market_flow_event_cluster_member_mx(
                       event_id,market,regime_label,horizon_label,exchange,signal_window_label,
                       signal_feature_ts,signal_evidence_label,reaction_end_ts,gross_hypothesis_return_pct,
                       roundtrip_spread_cost_bps,spread_adjusted_hypothesis_return_pct,
                       max_reference_notional_share_pct,representative_for_exchange,
                       suppressed_overlap_member,cluster_policy,representative_policy,source,
                       received_at,feature_version,schema_version
                   ) VALUES(?,?,?,?,?,'1m',?,?,?,?,?,?,?,1,0,?,?,
                            'market_flow_cost_edge',?,1,1)""",
                (
                    event_id,market,regime,horizon,exchange,anchor,evidence,anchor + 900.0,
                    adjusted + 0.01,1.0,adjusted,0.1,CLUSTER_POLICY,REPRESENTATIVE_POLICY,
                    anchor + 901.0,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def test_observation_ready_but_mixed_when_hit_rate_is_below_chance(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    for index in range(30):
        value = 0.20 if index < 12 else -0.05
        _insert_event(path,index=index,event_return=value,cross=index < 20)

    store = MarketFlowEventReliabilityStore(path)
    try:
        result = store.compute(now=1_800_100_000.0)
        audit = store.audit()
    finally:
        store.close()

    assert result["observation_ready_rows"] == 1
    assert result["promotion_ready_rows"] == 0
    row = audit["rows"][0]
    assert row["event_count"] == 30
    assert row["cross_exchange_event_count"] == 20
    assert row["mean_event_spread_adjusted_return_pct"] > 0
    assert row["event_hit_rate_pct"] == 40.0
    assert row["direction_consistent"] == 0
    assert row["status"] == "mixed_event_edge"


def test_directional_watch_requires_positive_cross_exchange_agreement(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    for index in range(30):
        _insert_event(path,index=index,event_return=0.10,cross=True)

    store = MarketFlowEventReliabilityStore(path)
    try:
        result = store.compute(now=1_800_100_000.0)
        audit = store.audit()
    finally:
        store.close()

    row = audit["rows"][0]
    assert result["promotion_ready_rows"] == 0
    assert row["direction_consistent"] == 1
    assert row["cross_exchange_positive_agreement_rate_pct"] == 100.0
    assert row["status"] == "directional_watch"


def test_promotion_requires_large_event_and_cross_exchange_samples_plus_wilson(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    for index in range(60):
        _insert_event(path,index=index,event_return=0.10,cross=index < 40)

    store = MarketFlowEventReliabilityStore(path)
    try:
        result = store.compute(now=1_800_100_000.0)
        audit = store.audit()
    finally:
        store.close()

    row = audit["rows"][0]
    assert result["promotion_ready_rows"] == 1
    assert row["event_count"] == 60
    assert row["cross_exchange_event_count"] == 40
    assert row["event_wilson_lower_pct"] > 50.0
    assert row["cross_exchange_positive_wilson_lower_pct"] > 50.0
    assert row["status"] == "validated_candidate"
    assert audit["promotion_contract_violations"] == 0


def test_cross_exchange_disagreement_blocks_direction_consistency(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    for index in range(30):
        _insert_event(
            path,index=index,event_return=0.05,cross=True,
            bithumb_return=0.20,upbit_return=-0.10,
        )

    store = MarketFlowEventReliabilityStore(path)
    try:
        store.compute(now=1_800_100_000.0)
        audit = store.audit()
    finally:
        store.close()

    row = audit["rows"][0]
    assert row["observation_ready"] == 1
    assert row["event_hit_rate_pct"] == 100.0
    assert row["cross_exchange_positive_agreement_rate_pct"] == 0.0
    assert row["direction_consistent"] == 0
    assert row["promotion_ready"] == 0
    assert row["status"] == "mixed_event_edge"
    assert audit["direction_contract_violations"] == 0
