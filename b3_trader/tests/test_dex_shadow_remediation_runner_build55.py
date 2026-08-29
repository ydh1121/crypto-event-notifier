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

    def _launch_candles(self, *, pool_created_at: float, **_: object):
        created = float(pool_created_at)
        minute = [
            DexCandle(created, 1.0, 1.0, 1.0, 1.0, 100.0, 60),
            DexCandle(created + 300, 1.1, 1.1, 1.1, 1.1, 120.0, 60),
        ]
        hourly = [
            DexCandle(created + 3600, 1.2, 1.2, 1.2, 1.2, 500.0, 3600),
        ]
        return hourly, minute


def _seed(path: Path, *, now: float) -> DexLaunchStore:
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
    case_key = "bithumb|KRW-REC|notice:1"
    conn.execute(
        "INSERT INTO listing_history_cases VALUES(?,?,?,?,?,?,?,?,?)",
        (case_key, "bithumb", "KRW-REC", "REC", now - 1000, "{}", 1, "complete", now),
    )
    conn.commit()
    conn.close()

    store = DexLaunchStore(path)
    asset_key = store.upsert_asset(
        case_key=case_key,
        coingecko_id="recoverable",
        platform_id="ethereum",
        network_id="eth",
        token_address="0x0000000000000000000000000000000000000001",
        identity_status="exact_contract_verified",
    )
    store.upsert_pool(
        asset_key=asset_key,
        pool={
            "pool_address": "0x0000000000000000000000000000000000000100",
            "dex_id": "test-dex",
            "name": "REC / USD",
            "pool_created_at": now - 86400,
            "reserve_usd": 100000,
            "volume_h24_usd": 50000,
        },
        gate_status="accepted",
        selected_primary=True,
    )
    store.upsert_features(
        asset_key=asset_key,
        pool_address="0x0000000000000000000000000000000000000100",
        feature_version=1,
        features={
            "paper_only": True,
            "shadow_only": True,
            "pool_quality": {"passed": True},
            "domestic_listing_window": {"status": "collected", "p5m_exact_minute": True},
            "pool_launch_window": {"status": "launch_ohlcv_unavailable"},
        },
    )
    return store


def test_build55_recovers_launch_and_runs_one_history_page(monkeypatch, tmp_path: Path) -> None:
    now = 1_800_000_000.0
    db = tmp_path / "sample.sqlite3"
    store = _seed(db, now=now)
    case_key = "bithumb|KRW-REC|notice:1"

    monkeypatch.setattr(
        "b3_trader.dex_shadow_remediation_runner.evaluate_dex_launch_quality",
        lambda _path: {"cases": [{"case_key": case_key, "usable_for_shadow_analysis": True}]},
    )
    monkeypatch.setattr(
        "b3_trader.dex_shadow_remediation_runner.plan_dex_shadow_remediation",
        lambda _path, now=None: {
            "ok": True,
            "readiness": {
                "shadow_readiness_advisory": False,
                "blocking_reasons": [
                    "launch_feature_coverage_below_min:0.150000/0.30",
                    "temporal_concentration_above_max:0.600000/0.40",
                ],
            },
            "temporal_remediation": {"historical_expansion_likely_required": True},
        },
    )

    runner = DexShadowRemediationRunner(
        db,
        status_path=tmp_path / "status.json",
        state_path=tmp_path / "state.json",
        cycle=FakeCycle(store),
        historical=FakeHistorical(),
    )
    try:
        plan = runner.plan(now=now)
        assert plan["action"] == "launch_recovery_plus_historical_expansion"
        assert plan["launch_recovery"]["candidate_count"] == 1
        assert plan["historical_expansion"]["pages_per_exchange"] == 1

        result = runner.run_once(max_launch_cases=2, now=now)
        assert result["processed_launch"] == 1
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
