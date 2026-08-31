from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.market_flow_reaction import MarketFlowReactionStore
from b3_trader.market_flow_reliability import (
    MarketFlowReliabilityStore,
    OBSERVATION_MIN_PER_VENUE,
    PROMOTION_MIN_PER_VENUE,
    PROMOTION_MIN_POOLED,
)


def _prepare(path: Path) -> None:
    MarketFlowReactionStore(path).close()


def _insert_ready(
    path: Path,
    *,
    exchange: str,
    count: int,
    evidence: str = "passive_sell_absorption_candidate",
    market: str = "KRW-ETH",
    window: str = "1m",
    horizon: str = "15m",
    positive_ratio: float = 0.65,
    positive_return: float = 0.10,
    negative_return: float = -0.08,
) -> None:
    conn = sqlite3.connect(path)
    try:
        positive_count = int(round(count * positive_ratio))
        for index in range(count):
            hypothesis_return = positive_return if index < positive_count else negative_return
            hypothesis_direction = -1 if evidence == "passive_sell_absorption_candidate" else 1
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
                    exchange,market,window,1_800_000_000.0 + index * 60.0,evidence,
                    100.0,1_000_000.0,1,hypothesis_direction,
                    horizon,900.0,1_800_000_000.0 + index * 60.0,
                    1_800_000_900.0 + index * 60.0,"1m",60.0,1,"ready",
                    1_800_000_840.0 + index * 60.0,100.0 + future_return,
                    future_return,future_return,hypothesis_return,
                    "price_flow_divergence+rest_ohlcv",1_800_001_000.0 + index,
                    1,1,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _row(path: Path) -> dict:
    store = MarketFlowReliabilityStore(path)
    try:
        store.compute(now=1_900_000_000.0)
        rows = store.audit()["rows"]
        assert rows
        return rows[0]
    finally:
        store.close()


def test_directional_watch_requires_cross_exchange_observation(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_ready(path,exchange="bithumb",count=OBSERVATION_MIN_PER_VENUE,positive_ratio=0.65)
    _insert_ready(path,exchange="upbit",count=OBSERVATION_MIN_PER_VENUE,positive_ratio=0.60)
    row = _row(path)
    assert row["observation_ready"] == 1
    assert row["cross_exchange_direction_consistent"] == 1
    assert row["promotion_ready"] == 0
    assert row["status"] == "directional_watch"


def test_mixed_cross_exchange_does_not_promote(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_ready(path,exchange="bithumb",count=OBSERVATION_MIN_PER_VENUE,positive_ratio=0.70)
    _insert_ready(path,exchange="upbit",count=OBSERVATION_MIN_PER_VENUE,positive_ratio=0.35)
    row = _row(path)
    assert row["observation_ready"] == 1
    assert row["cross_exchange_direction_consistent"] == 0
    assert row["promotion_ready"] == 0
    assert row["status"] == "mixed_cross_exchange"


def test_promotion_requires_large_cross_exchange_sample_and_wilson_support(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    per_venue = max(PROMOTION_MIN_PER_VENUE, PROMOTION_MIN_POOLED // 2)
    _insert_ready(path,exchange="bithumb",count=per_venue,positive_ratio=0.75)
    _insert_ready(path,exchange="upbit",count=per_venue,positive_ratio=0.75)
    row = _row(path)
    assert row["pooled_sample_count"] >= PROMOTION_MIN_POOLED
    assert float(row["pooled_wilson_lower_pct"]) > 50.0
    assert row["promotion_ready"] == 1
    assert row["status"] == "validated_candidate"


def test_small_single_exchange_sample_stays_collecting(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    _prepare(path)
    _insert_ready(path,exchange="bithumb",count=10,positive_ratio=0.90)
    row = _row(path)
    assert row["observation_ready"] == 0
    assert row["promotion_ready"] == 0
    assert row["status"] == "collecting"
