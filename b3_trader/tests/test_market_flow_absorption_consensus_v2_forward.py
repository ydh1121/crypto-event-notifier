from __future__ import annotations

from pathlib import Path

from b3_trader.market_fee_schedule import MarketFeeScheduleStore
from b3_trader.market_flow_absorption_consensus_v2 import MarketFlowAbsorptionConsensusV2Store
from b3_trader.market_flow_absorption_consensus_v2_forward import (
    REFERENCE_NOTIONAL_KRW,
    MarketFlowAbsorptionConsensusV2ForwardStore,
)
from b3_trader.market_ohlcv_store import MarketOhlcvStore
from b3_trader.market_orderbook_ladder import MarketOrderbookLadderStore


def _insert_consensus(
    path: Path,
    *,
    feature_ts: float,
    consensus_received_at: float,
    activation_ts: float = 800.0,
) -> None:
    store = MarketFlowAbsorptionConsensusV2Store(path)
    try:
        store.conn.execute(
            """INSERT INTO research_market_flow_absorption_consensus_v2_mx(
                   market,feature_ts,window_label,evidence_label,hypothesis_direction,
                   bithumb_delta_pct,upbit_delta_pct,
                   bithumb_price_return_bps,upbit_price_return_bps,
                   bithumb_replenishment_ratio,upbit_replenishment_ratio,
                   bithumb_same_best_pairs,upbit_same_best_pairs,
                   bithumb_received_at,upbit_received_at,
                   identity_verified,identity_basis,identity_received_at,
                   activation_ts,source,received_at,feature_version,schema_version
               ) VALUES(
                   'KRW-BTC',?,'5m','passive_buy_absorption_candidate',1,
                   -30,-32,2,3,1.4,1.5,8,9,?,?,1,
                   'symbol+official_name_exact',?,?,
                   'exact_5m_bithumb+upbit_v1_absorption_consensus',?,2,1
               )""",
            (
                feature_ts,
                consensus_received_at - 1.0,
                consensus_received_at - 0.5,
                consensus_received_at - 2.0,
                activation_ts,
                consensus_received_at,
            ),
        )
        store.conn.commit()
    finally:
        store.close()


def _seed_15m_ohlcv(path: Path, *, entry_ts: float) -> None:
    store = MarketOhlcvStore(path)
    try:
        rows = []
        for exchange in ("bithumb", "upbit"):
            for offset in range(15):
                ts = entry_ts + offset * 60.0
                rows.append(
                    {
                        "exchange": exchange,
                        "market": "KRW-BTC",
                        "timeframe": "1m",
                        "candle_ts": ts,
                        "open": 100.0,
                        "high": 101.5,
                        "low": 99.5,
                        "close": 101.0 if offset == 14 else 100.0,
                        "is_closed": True,
                        "received_at": entry_ts + 1000.0,
                    }
                )
        store.upsert_rows(rows)
    finally:
        store.close()


def _seed_fees_and_ladders(path: Path, *, entry_ts: float, exit_ts: float) -> None:
    fees = MarketFeeScheduleStore(path)
    try:
        fees.ensure_current_catalog(now=900.0)
        fees.set_active_profile(
            "bithumb",
            "KRW",
            "coupon_0_04",
            source="test_confirmed_account_profile",
            now=1000.0,
        )
    finally:
        fees.close()

    ladder = MarketOrderbookLadderStore(path)
    try:
        levels_bid = [
            {"price": 99.9, "size": 20_000.0},
            {"price": 99.8, "size": 20_000.0},
        ]
        levels_ask = [
            {"price": 100.1, "size": 20_000.0},
            {"price": 100.2, "size": 20_000.0},
        ]
        for exchange in ("bithumb", "upbit"):
            for boundary in (entry_ts, exit_ts):
                result = ladder.insert_snapshot(
                    {
                        "exchange": exchange,
                        "market": "KRW-BTC",
                        "source_ts": boundary - 2.0,
                        "bid_levels": levels_bid,
                        "ask_levels": levels_ask,
                    },
                    received_at=boundary - 1.0,
                )
                assert result["accepted"] is True
    finally:
        ladder.close()


def test_v2_forward_has_independent_activation_and_strict_causal_entry(tmp_path: Path) -> None:
    path = tmp_path / "v2-forward.sqlite3"
    _insert_consensus(path, feature_ts=900.0, consensus_received_at=950.0)

    store = MarketFlowAbsorptionConsensusV2ForwardStore(path)
    try:
        first = store.compute(now=1000.0)
        assert first["activation_ts"] == 1000.0
        assert first["reaction_rows_registered"] == 0

        _insert_consensus(path, feature_ts=1200.0, consensus_received_at=1210.0)
        second = store.compute(now=1300.0)
        audit = store.audit()

        assert second["reaction_rows_registered"] == 8
        assert audit["consensus_source_rows_before_forward_activation"] == 1
        assert audit["consensus_source_rows_after_forward_activation"] == 1
        assert audit["pre_forward_activation_reaction_rows"] == 0
        assert audit["causal_entry_boundary_violations"] == 0
        assert audit["reference_notional_krw"] == REFERENCE_NOTIONAL_KRW

        rows = store.conn.execute(
            """SELECT DISTINCT consensus_feature_ts,consensus_received_at,entry_ts
               FROM research_market_flow_absorption_consensus_v2_reaction_mx"""
        ).fetchall()
        assert len(rows) == 1
        assert float(rows[0]["consensus_feature_ts"]) == 1200.0
        assert float(rows[0]["consensus_received_at"]) == 1210.0
        assert float(rows[0]["entry_ts"]) == 1500.0
        assert float(rows[0]["entry_ts"]) > float(rows[0]["consensus_received_at"])
    finally:
        store.close()


def test_v2_forward_exact_15m_to_750k_full_cost_event_is_separate(tmp_path: Path) -> None:
    path = tmp_path / "v2-forward-full-cost.sqlite3"
    _insert_consensus(path, feature_ts=900.0, consensus_received_at=950.0)

    store = MarketFlowAbsorptionConsensusV2ForwardStore(path)
    try:
        store.compute(now=1000.0)
        _insert_consensus(path, feature_ts=1200.0, consensus_received_at=1210.0)
        registered = store.compute(now=1300.0)
        assert registered["reaction_rows_registered"] == 8

        entry_ts = 1500.0
        exit_ts = 2400.0
        _seed_15m_ohlcv(path, entry_ts=entry_ts)
        _seed_fees_and_ladders(path, entry_ts=entry_ts, exit_ts=exit_ts)

        result = store.compute(now=2500.0)
        audit = store.audit()

        assert result["reaction_ready_written"] == 2
        assert result["full_cost_ready_rows"] == 2
        assert result["ready_nonoverlap_events"] == 1
        assert audit["prior_only_ladder_violations"] == 0
        assert audit["full_cost_formula_violations"] == 0
        assert audit["promotion_ready_rows"] == 0

        reactions = store.conn.execute(
            """SELECT exchange,gross_hypothesis_return_pct
               FROM research_market_flow_absorption_consensus_v2_reaction_mx
               WHERE horizon_label='15m' AND data_ready=1
               ORDER BY exchange"""
        ).fetchall()
        assert len(reactions) == 2
        assert all(abs(float(row["gross_hypothesis_return_pct"]) - 1.0) < 1e-9 for row in reactions)

        costs = store.conn.execute(
            """SELECT exchange,reference_notional_krw,fee_profile,
                      full_cost_ready,total_transaction_cost_bps,
                      full_cost_adjusted_return_pct
               FROM research_market_flow_absorption_consensus_v2_full_cost_mx
               ORDER BY exchange"""
        ).fetchall()
        assert len(costs) == 2
        assert all(float(row["reference_notional_krw"]) == 750000.0 for row in costs)
        assert all(int(row["full_cost_ready"]) == 1 for row in costs)
        assert str(costs[0]["exchange"]) == "bithumb"
        assert str(costs[0]["fee_profile"]) == "coupon_0_04"
        assert str(costs[1]["exchange"]) == "upbit"
        assert str(costs[1]["fee_profile"]) == "standard"
        assert all(float(row["full_cost_adjusted_return_pct"]) < 1.0 for row in costs)

        event = store.conn.execute(
            """SELECT * FROM research_market_flow_absorption_consensus_v2_event_mx
               WHERE horizon_label='15m'"""
        ).fetchone()
        assert event is not None
        assert int(event["cross_exchange_full_cost_ready"]) == 1
        assert int(event["suppressed_overlap"]) == 0
        assert float(event["mean_full_cost_adjusted_return_pct"]) > 0.0

        reliability = store.conn.execute(
            """SELECT * FROM research_market_flow_absorption_consensus_v2_reliability_mx
               WHERE market='KRW-BTC'
                 AND regime_label='accumulation_candidate'
                 AND horizon_label='15m'"""
        ).fetchone()
        assert reliability is not None
        assert int(reliability["event_count"]) == 1
        assert int(reliability["observation_ready"]) == 0
        assert int(reliability["promotion_ready"]) == 0
        assert str(reliability["status"]) == "collecting_v2_full_cost"
    finally:
        store.close()
