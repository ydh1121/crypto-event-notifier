from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from b3_trader.dex_alternate_launch_probe import DexAlternateLaunchProbeRunner
from b3_trader.dex_launch_sources import DexCandle


class FakeStore:
    def __init__(self) -> None:
        self.candle_writes: list[tuple[str, str, str, int]] = []
        self.feature_writes: list[tuple[str, str, dict]] = []

    def upsert_candles(self, *, asset_key, pool_address, series_kind, candles):
        rows = list(candles)
        self.candle_writes.append((asset_key, pool_address, series_kind, len(rows)))
        return len(rows)

    def upsert_features(self, *, asset_key, pool_address, feature_version, features):
        self.feature_writes.append((asset_key, pool_address, dict(features)))


class FakeCycle:
    def __init__(self) -> None:
        self.store = FakeStore()
        self.min_liquidity_usd = 25_000.0
        self.min_volume_h24_usd = 10_000.0
        self.fetches: list[tuple[str, str, str, float]] = []

    def _launch_candles(self, *, network_id, pool_address, token_address, pool_created_at, now):
        self.fetches.append((network_id, pool_address, token_address, pool_created_at))
        return [
            DexCandle(
                ts=float(pool_created_at) + 1800.0,
                open=1.0,
                high=1.1,
                low=0.9,
                close=1.0,
                volume_usd=1000.0,
                interval_seconds=3600,
            )
        ], []


def _db(path: Path, *, created: float) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            CREATE TABLE listing_history_cases(
              case_key TEXT PRIMARY KEY,
              domestic_open_at REAL NOT NULL
            );
            CREATE TABLE dex_launch_pools(
              asset_key TEXT NOT NULL,
              pool_address TEXT NOT NULL,
              gate_status TEXT NOT NULL,
              selected_primary INTEGER NOT NULL,
              reserve_usd REAL NOT NULL,
              volume_h24_usd REAL NOT NULL,
              pool_created_at REAL NOT NULL,
              PRIMARY KEY(asset_key,pool_address)
            );
            CREATE TABLE dex_launch_features(
              asset_key TEXT NOT NULL,
              pool_address TEXT NOT NULL,
              feature_json TEXT NOT NULL DEFAULT '{}',
              PRIMARY KEY(asset_key,pool_address)
            );
            """
        )
        for case_key, asset_key in (("bithumb|KRW-FOLD|1", "fold-b"), ("upbit|KRW-FOLD|2", "fold-u")):
            conn.execute(
                "INSERT INTO listing_history_cases(case_key,domestic_open_at) VALUES(?,?)",
                (case_key, created + 10 * 86400),
            )
            conn.execute(
                """
                INSERT INTO dex_launch_pools(
                  asset_key,pool_address,gate_status,selected_primary,reserve_usd,volume_h24_usd,pool_created_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (asset_key, "0xfold-alt", "accepted", 0, 900000.0, 1700000.0, created),
            )
        conn.execute(
            "INSERT INTO listing_history_cases(case_key,domestic_open_at) VALUES(?,?)",
            ("upbit|KRW-USDG|3", created + 10 * 86400),
        )
        conn.execute(
            """
            INSERT INTO dex_launch_pools(
              asset_key,pool_address,gate_status,selected_primary,reserve_usd,volume_h24_usd,pool_created_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            ("usdg-u", "0xusdg-alt", "accepted", 0, 50000.0, 13000.0, created + 3 * 86400),
        )
        conn.commit()
    finally:
        conn.close()


def _audit(created: float):
    def audit(_path, *, now=None):
        return {
            "ok": True,
            "summary": {
                "usable_event_cases": 36,
                "launch_feature_cases": 8,
                "required_launch_feature_cases": 11,
                "additional_launch_cases_needed": 3,
            },
            "alternate_pool_opportunities": [
                {
                    "case_key": "bithumb|KRW-FOLD|1",
                    "asset_key": "fold-b",
                    "network_id": "eth",
                    "token_address": "0xfold-token",
                    "pool_address": "0xfold-alt",
                    "dex_id": "uniswap-v4-ethereum",
                    "pool_created_at": created,
                    "pool_age_days": 11.0,
                    "reserve_usd": 900000.0,
                    "volume_h24_usd": 1700000.0,
                },
                {
                    "case_key": "upbit|KRW-FOLD|2",
                    "asset_key": "fold-u",
                    "network_id": "eth",
                    "token_address": "0xfold-token",
                    "pool_address": "0xfold-alt",
                    "dex_id": "uniswap-v4-ethereum",
                    "pool_created_at": created,
                    "pool_age_days": 11.0,
                    "reserve_usd": 900000.0,
                    "volume_h24_usd": 1700000.0,
                },
                {
                    "case_key": "upbit|KRW-USDG|3",
                    "asset_key": "usdg-u",
                    "network_id": "ink",
                    "token_address": "0xusdg-token",
                    "pool_address": "0xusdg-alt",
                    "dex_id": "reservoir-v3-ink",
                    "pool_created_at": created + 3 * 86400,
                    "pool_age_days": 8.0,
                    "reserve_usd": 50000.0,
                    "volume_h24_usd": 13000.0,
                },
            ],
        }

    return audit


def test_build61_prefers_shared_case_gain_and_fetches_source_once(tmp_path: Path) -> None:
    now = time.time()
    created = now - 11 * 86400
    db_path = tmp_path / "sample.sqlite3"
    _db(db_path, created=created)
    cycle = FakeCycle()
    runner = DexAlternateLaunchProbeRunner(
        db_path,
        cycle=cycle,
        audit_fn=_audit(created),
        status_path=tmp_path / "status.json",
        state_path=tmp_path / "state.json",
    )
    try:
        plan = runner.plan(now=now)
        first = plan["alternate_probe"]["preview"][0]
        assert first["pool_address"] == "0xfold-alt"
        assert first["potential_case_gain"] == 2

        result = runner.run_once(max_sources=1, now=now)
        assert result["processed_sources"] == 1
        assert result["distinct_source_fetches"] == 1
        assert result["total_collected_case_gain"] == 2
        assert len(cycle.fetches) == 1
        assert len(cycle.store.feature_writes) == 2
        assert all(row[2]["pool_launch_window"]["status"] == "collected" for row in cycle.store.feature_writes)
        assert all(row[2]["alternate_pool_launch_probe"] is True for row in cycle.store.feature_writes)
        assert result["selected_primary_mutation"] is False
        assert result["domestic_window_fetches"] is False
    finally:
        runner.close()


def test_build61_revalidates_non_primary_pool_before_fetch(tmp_path: Path) -> None:
    now = time.time()
    created = now - 11 * 86400
    db_path = tmp_path / "sample.sqlite3"
    _db(db_path, created=created)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE dex_launch_pools SET selected_primary=1 WHERE asset_key IN ('fold-b','fold-u') AND pool_address='0xfold-alt'"
        )
        conn.commit()
    finally:
        conn.close()

    cycle = FakeCycle()
    runner = DexAlternateLaunchProbeRunner(
        db_path,
        cycle=cycle,
        audit_fn=_audit(created),
        status_path=tmp_path / "status.json",
        state_path=tmp_path / "state.json",
    )
    try:
        result = runner.run_once(max_sources=1, now=now)
        assert result["processed_sources"] == 1
        assert result["distinct_source_fetches"] == 0
        assert result["results"][0]["status"] == "stale_candidate"
        assert cycle.fetches == []
        assert cycle.store.feature_writes == []
    finally:
        runner.close()
