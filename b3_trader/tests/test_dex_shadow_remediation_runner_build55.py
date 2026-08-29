from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from b3_trader.dex_launch_sources import DexCandle
from b3_trader.dex_launch_store import DexLaunchStore
from b3_trader.dex_shadow_remediation_runner import DexShadowRemediationRunner


class FakeHistorical:
    def plan(self) -> dict:
        return {
            "status": "planned",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "official_sources_only": True,
            "pages_per_exchange": 1,
            "next_page": {"bithumb": 5, "upbit": 5},
        }

    def run_once(self) -> dict:
        return {
            "status": "backfilled",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "official_sources_only": True,
            "pages_per_exchange": 1,
            "listing_cases_seeded": 3,
        }


class FakeCycle:
    def __init__(self, store: DexLaunchStore) -> None:
        self.store = store
        self.calls = 0

    def _launch_candles(self, *, pool_created_at: float, **_: object):
        self.calls += 1
        created = float(pool_created_at)
        minute = [
            DexCandle(created, 1.0, 1.0, 1.0, 1.0, 100.0, 60),
            DexCandle(created + 300, 1.1, 1.1, 1.1, 1.1, 120.0, 60),
        ]
        hourly = [
            DexCandle(created + 3600, 1.2, 1.2, 1.2, 1.2, 500.0, 3600),
        ]
        return hourly, minute


def _create_listing_table(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE listing_history_cases (
          case_key TEXT PRIMARY KEY,
          domestic_exchange TEXT NOT NULL,
          domestic_market TEXT NOT NULL,
          symbol TEXT NOT NULL,
          domestic_open_at REAL NOT NULL,
          identity_json TEXT NOT NULL DEFAULT '{}',
          identity_verified INTEGER NOT NULL,
          status TEXT NOT NULL,
          updated_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_listing(path: Path, *, case_key: str, exchange: str, market: str, now: float) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "INSERT INTO listing_history_cases VALUES(?,?,?,?,?,?,?,?,?)",
        (case_key, exchange, market, market.removeprefix("KRW-"), now - 1000, "{}", 1, "complete", now),
    )
    conn.commit()
    conn.close()


def _add_primary(
    store: DexLaunchStore,
    *,
    case_key: str,
    platform_id: str,
    network_id: str,
    token_address: str,
    pool_address: str,
    pool_created_at: float,
    launch_status: str,
) -> str:
    asset_key = store.upsert_asset(
        case_key=case_key,
        coingecko_id="recoverable",
        platform_id=platform_id,
        network_id=network_id,
        token_address=token_address,
        identity_status="exact_contract_verified",
    )
    store.upsert_pool(
        asset_key=asset_key,
        pool={
            "pool_address": pool_address,
            "dex_id": "test-dex",
            "name": "REC / USD",
            "pool_created_at": pool_created_at,
            "reserve_usd": 100000,
            "volume_h24_usd": 50000,
        },
        gate_status="accepted",
        selected_primary=True,
    )
    store.upsert_features(
        asset_key=asset_key,
        pool_address=pool_address,
        feature_version=1,
        features={
            "paper_only": True,
            "shadow_only": True,
            "pool_quality": {"passed": True},
            "domestic_listing_window": {"status": "collected", "p5m_exact_minute": True},
            "pool_launch_window": {"status": launch_status},
        },
    )
    return asset_key


def _seed(path: Path, *, now: float) -> DexLaunchStore:
    _create_listing_table(path)
    case_key = "bithumb|KRW-REC|notice:1"
    _insert_listing(path, case_key=case_key, exchange="bithumb", market="KRW-REC", now=now)
    store = DexLaunchStore(path)
    _add_primary(
        store,
        case_key=case_key,
        platform_id="ethereum",
        network_id="eth",
        token_address="0x0000000000000000000000000000000000000001",
        pool_address="0x0000000000000000000000000000000000000100",
        pool_created_at=now - 86400,
        launch_status="launch_ohlcv_unavailable",
    )
    return store


def _mock_remediation(monkeypatch, *, temporal: bool = True) -> None:
    blockers = ["launch_feature_coverage_below_min:0.150000/0.30"]
    if temporal:
        blockers.append("temporal_concentration_above_max:0.600000/0.40")
    monkeypatch.setattr(
        "b3_trader.dex_shadow_remediation_runner.plan_dex_shadow_remediation",
        lambda _path, now=None: {
            "ok": True,
            "readiness": {
                "shadow_readiness_advisory": False,
                "blocking_reasons": blockers,
            },
            "temporal_remediation": {"historical_expansion_likely_required": temporal},
        },
    )


def test_build55_recovers_launch_and_runs_one_history_page(monkeypatch, tmp_path: Path) -> None:
    now = 1_800_000_000.0
    db = tmp_path / "sample.sqlite3"
    store = _seed(db, now=now)
    case_key = "bithumb|KRW-REC|notice:1"

    monkeypatch.setattr(
        "b3_trader.dex_shadow_remediation_runner.evaluate_dex_launch_quality",
        lambda _path: {"cases": [{"case_key": case_key, "usable_for_shadow_analysis": True}]},
    )
    _mock_remediation(monkeypatch, temporal=True)
    cycle = FakeCycle(store)
    runner = DexShadowRemediationRunner(
        db,
        status_path=tmp_path / "status.json",
        state_path=tmp_path / "state.json",
        cycle=cycle,
        historical=FakeHistorical(),
    )
    try:
        plan = runner.plan(now=now)
        assert plan["action"] == "launch_recovery_plus_historical_expansion"
        assert plan["launch_recovery"]["candidate_count"] == 1
        assert plan["launch_recovery"]["case_level_missing_only"] is True
        assert plan["launch_recovery"]["shared_source_fetch_reuse"] is True
        assert plan["historical_expansion"]["pages_per_exchange"] == 1

        result = runner.run_once(max_launch_cases=2, now=now)
        assert result["processed_launch"] == 1
        assert result["distinct_launch_source_fetches"] == 1
        assert cycle.calls == 1
        assert result["launch_results"][0]["status"] == "collected"
        assert result["historical_pages_per_exchange"] == 1
        assert result["historical_result"]["official_sources_only"] is True

        row = store.conn.execute("SELECT feature_json FROM dex_launch_features").fetchone()
        feature = json.loads(str(row[0]))
        assert feature["domestic_listing_window"]["status"] == "collected"
        assert feature["pool_launch_window"]["status"] == "collected"
        launch_candles = store.conn.execute(
            "SELECT COUNT(*) FROM dex_launch_candles WHERE series_kind LIKE 'launch_%'"
        ).fetchone()[0]
        assert int(launch_candles) >= 3
    finally:
        runner.close()
        store.close()


def test_build55_excludes_case_already_collected_and_reuses_shared_source(monkeypatch, tmp_path: Path) -> None:
    now = 1_800_000_000.0
    db = tmp_path / "shared.sqlite3"
    _create_listing_table(db)
    case_a = "bithumb|KRW-DUP|notice:1"
    case_b = "upbit|KRW-DUP|notice:2"
    case_ready = "bithumb|KRW-READY|notice:3"
    for case_key, exchange, market in (
        (case_a, "bithumb", "KRW-DUP"),
        (case_b, "upbit", "KRW-DUP"),
        (case_ready, "bithumb", "KRW-READY"),
    ):
        _insert_listing(db, case_key=case_key, exchange=exchange, market=market, now=now)

    store = DexLaunchStore(db)
    shared_token = "0x00000000000000000000000000000000000000aa"
    shared_pool = "0x0000000000000000000000000000000000000aaa"
    for case_key in (case_a, case_b):
        _add_primary(
            store,
            case_key=case_key,
            platform_id="ethereum",
            network_id="eth",
            token_address=shared_token,
            pool_address=shared_pool,
            pool_created_at=now - 86400,
            launch_status="launch_ohlcv_unavailable",
        )

    _add_primary(
        store,
        case_key=case_ready,
        platform_id="ethereum",
        network_id="eth",
        token_address="0x00000000000000000000000000000000000000b1",
        pool_address="0x0000000000000000000000000000000000000b01",
        pool_created_at=now - 2 * 86400,
        launch_status="collected",
    )
    _add_primary(
        store,
        case_key=case_ready,
        platform_id="base",
        network_id="base",
        token_address="0x00000000000000000000000000000000000000b2",
        pool_address="0x0000000000000000000000000000000000000b02",
        pool_created_at=now - 86400,
        launch_status="launch_ohlcv_unavailable",
    )

    monkeypatch.setattr(
        "b3_trader.dex_shadow_remediation_runner.evaluate_dex_launch_quality",
        lambda _path: {
            "cases": [
                {"case_key": case_a, "usable_for_shadow_analysis": True},
                {"case_key": case_b, "usable_for_shadow_analysis": True},
                {"case_key": case_ready, "usable_for_shadow_analysis": True},
            ]
        },
    )
    _mock_remediation(monkeypatch, temporal=False)
    cycle = FakeCycle(store)
    runner = DexShadowRemediationRunner(
        db,
        status_path=tmp_path / "status.json",
        state_path=tmp_path / "state.json",
        cycle=cycle,
        historical=FakeHistorical(),
    )
    try:
        plan = runner.plan(now=now)
        assert plan["action"] == "launch_recovery_only"
        assert plan["launch_recovery"]["candidate_count"] == 2
        assert plan["launch_recovery"]["distinct_source_count"] == 1
        assert all(row["case_key"] != case_ready for row in plan["launch_recovery"]["preview"])
        assert all(row["shared_source_case_count"] == 2 for row in plan["launch_recovery"]["preview"])

        result = runner.run_once(max_launch_cases=2, now=now)
        assert result["processed_launch"] == 2
        assert result["distinct_launch_source_fetches"] == 1
        assert cycle.calls == 1
        assert [row["source_reused"] for row in result["launch_results"]] == [False, True]
        assert all(row["status"] == "collected" for row in result["launch_results"])
    finally:
        runner.close()
        store.close()
