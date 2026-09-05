from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.market_flow_absorption_consensus_v2 import (
    CONSENSUS_WINDOW_LABEL,
    IDENTITY_BASIS,
    MarketFlowAbsorptionConsensusV2Store,
)


def _prepare_sources(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE research_market_price_flow_divergence_mx(
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                window_label TEXT NOT NULL,
                feature_ts REAL NOT NULL,
                data_ready INTEGER NOT NULL,
                evidence_label TEXT NOT NULL,
                delta_pct REAL,
                price_return_bps REAL,
                bid_replenishment_ratio REAL,
                ask_replenishment_ratio REAL,
                bid_same_best_pairs INTEGER,
                ask_same_best_pairs INTEGER,
                received_at REAL NOT NULL,
                PRIMARY KEY(exchange,market,window_label,feature_ts)
            );
            CREATE TABLE research_market_cross_exchange_gap_mx(
                market TEXT PRIMARY KEY,
                bithumb_market TEXT NOT NULL,
                upbit_market TEXT NOT NULL,
                identity_verified INTEGER NOT NULL,
                identity_basis TEXT NOT NULL,
                received_at REAL NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _identity(path: Path, *, verified: bool = True, market: str = "KRW-BTC") -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO research_market_cross_exchange_gap_mx(
                   market,bithumb_market,upbit_market,identity_verified,identity_basis,received_at
               ) VALUES(?,?,?,?,?,?)""",
            (
                market,
                market,
                market,
                1 if verified else 0,
                IDENTITY_BASIS if verified else "identity_mismatch",
                900.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _v1(
    path: Path,
    *,
    exchange: str,
    feature_ts: float,
    received_at: float,
    label: str = "passive_buy_absorption_candidate",
    window_label: str = CONSENSUS_WINDOW_LABEL,
    market: str = "KRW-BTC",
) -> None:
    buy = label == "passive_buy_absorption_candidate"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO research_market_price_flow_divergence_mx(
                   exchange,market,window_label,feature_ts,data_ready,evidence_label,
                   delta_pct,price_return_bps,bid_replenishment_ratio,ask_replenishment_ratio,
                   bid_same_best_pairs,ask_same_best_pairs,received_at
               ) VALUES(?,?,?,?,1,?,?,?,?,?,?,?,?)""",
            (
                exchange,
                market,
                window_label,
                feature_ts,
                label,
                -35.0 if buy else 35.0,
                2.0 if buy else -2.0,
                1.4 if buy else 0.5,
                0.5 if buy else 1.4,
                8 if buy else 2,
                2 if buy else 8,
                received_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_consensus_v2_is_forward_only_and_append_only(tmp_path: Path) -> None:
    path = tmp_path / "consensus-v2.sqlite3"
    _prepare_sources(path)
    _identity(path)
    _v1(path, exchange="bithumb", feature_ts=900.0, received_at=950.0)
    _v1(path, exchange="upbit", feature_ts=900.0, received_at=950.0)

    store = MarketFlowAbsorptionConsensusV2Store(path)
    try:
        first = store.compute(now=1000.0)
        assert first["activation_ts"] == 1000.0
        assert first["rows_written"] == 0
        assert first["consensus_rows"] == 0

        _v1(path, exchange="bithumb", feature_ts=1200.0, received_at=1210.0)
        _v1(path, exchange="upbit", feature_ts=1200.0, received_at=1211.0)
        second = store.compute(now=1300.0)
        third = store.compute(now=1400.0)
        audit = store.audit()

        assert second["rows_written"] == 1
        assert second["consensus_rows"] == 1
        assert third["rows_written"] == 0
        assert third["consensus_rows"] == 1
        assert audit["ok"] is True
        assert audit["activation_ts"] == 1000.0
        assert audit["pre_activation_rows"] == 0
        assert audit["non_5m_rows"] == 0
        assert audit["identity_violation_rows"] == 0
        row = store.conn.execute(
            "SELECT * FROM research_market_flow_absorption_consensus_v2_mx"
        ).fetchone()
        assert row is not None
        assert row["feature_ts"] == 1200.0
        assert row["hypothesis_direction"] == 1
        assert row["evidence_label"] == "passive_buy_absorption_candidate"
    finally:
        store.close()


def test_consensus_v2_requires_exact_exchange_direction_time_and_identity(tmp_path: Path) -> None:
    path = tmp_path / "consensus-v2-gates.sqlite3"
    _prepare_sources(path)
    _identity(path, verified=False)
    store = MarketFlowAbsorptionConsensusV2Store(path)
    try:
        store.compute(now=1000.0)

        _v1(path, exchange="bithumb", feature_ts=1200.0, received_at=1210.0)
        _v1(
            path,
            exchange="upbit",
            feature_ts=1200.0,
            received_at=1210.0,
            label="passive_sell_absorption_candidate",
        )
        assert store.compute(now=1300.0)["consensus_rows"] == 0

        _identity(path, verified=True)
        _v1(
            path,
            exchange="bithumb",
            feature_ts=1500.0,
            received_at=1510.0,
            window_label="1m",
        )
        _v1(
            path,
            exchange="upbit",
            feature_ts=1500.0,
            received_at=1510.0,
            window_label="1m",
        )
        assert store.compute(now=1600.0)["consensus_rows"] == 0

        _v1(path, exchange="bithumb", feature_ts=1800.0, received_at=1810.0)
        _v1(path, exchange="upbit", feature_ts=1860.0, received_at=1870.0)
        assert store.compute(now=1900.0)["consensus_rows"] == 0
        assert store.audit()["ok"] is True
    finally:
        store.close()
