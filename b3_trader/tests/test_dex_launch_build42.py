from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from b3_trader.dex_launch_audit import audit_dex_launch
from b3_trader.dex_launch_features import domestic_window_features
from b3_trader.dex_launch_research_cycle import DexLaunchResearchCycle
from b3_trader.dex_launch_sources import DexCandle, normalize_contract_address
from b3_trader.dex_launch_store import DexLaunchStore
from b3_trader.listing_identity import ListingIdentity


def candle(ts: float, price: float, interval: int) -> DexCandle:
    return DexCandle(ts=ts, open=price, high=price, low=price, close=price, volume_usd=1000.0, interval_seconds=interval)


def test_contract_normalization_preserves_non_evm_case() -> None:
    assert normalize_contract_address("0xABCDef") == "0xabcdef"
    assert normalize_contract_address("SoLBase58CaseSensitive") == "SoLBase58CaseSensitive"


def test_domestic_feature_requires_exact_minute_for_p5m() -> None:
    open_at = 1_000_000.0
    hourly = [
        candle(open_at - 7 * 86400, 5.0, 3600),
        candle(open_at - 3600, 8.0, 3600),
        candle(open_at + 3600, 12.0, 3600),
    ]
    minute = [candle(open_at, 10.0, 60), candle(open_at + 300, 11.0, 60)]
    result = domestic_window_features(domestic_open_at=open_at, hourly=hourly, minute=minute)
    assert result["status"] == "collected"
    assert result["reference"]["interval_seconds"] == 60
    assert result["post"]["p5m"]["candle_ts"] == open_at + 300
    assert result["post"]["p5m"]["return_from_domestic_open_pct"] == 10.0
    assert result["p5m_exact_minute"] is True


def _create_listing_case(
    path: Path,
    *,
    open_at: float = 1_000_000.0,
    identity: dict | None = None,
) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE listing_history_cases (
          case_key TEXT PRIMARY KEY,
          domestic_exchange TEXT NOT NULL,
          domestic_market TEXT NOT NULL,
          symbol TEXT NOT NULL,
          domestic_open_at REAL NOT NULL,
          identity_json TEXT NOT NULL,
          identity_verified INTEGER NOT NULL,
          status TEXT NOT NULL,
          updated_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO listing_history_cases VALUES(?,?,?,?,?,?,?,?,?)",
        (
            "bithumb|KRW-TST|notice:1",
            "bithumb",
            "KRW-TST",
            "TST",
            open_at,
            json.dumps(identity or {"provider": "coingecko", "provider_id": "test-token"}),
            1,
            "complete",
            open_at,
        ),
    )
    conn.commit()
    conn.close()


class FakeSource:
    def coin_contracts(self, coin_id: str):
        assert coin_id == "test-token"
        return [{"platform_id": "ethereum", "token_address": "0xABC"}]

    def network_map(self, required_platforms=None):
        assert "ethereum" in required_platforms
        return {"ethereum": "eth"}

    def token_pools(self, network_id: str, token_address: str):
        assert network_id == "eth"
        assert normalize_contract_address(token_address) == "0xabc"
        return [
            {
                "pool_address": "0xPOOL",
                "name": "TST / USDT",
                "dex_id": "unit_dex",
                "pool_created_at": 900_000.0,
                "reserve_usd": 50_000.0,
                "volume_h24_usd": 20_000.0,
                "volume_h6_usd": 5_000.0,
                "volume_h1_usd": 1_000.0,
                "volume_m5_usd": 100.0,
                "base_token_address": "0xabc",
                "quote_token_address": "0xdef",
            },
            {
                "pool_address": "0xLOW",
                "name": "TST / LOW",
                "dex_id": "unit_dex",
                "pool_created_at": 910_000.0,
                "reserve_usd": 2_000.0,
                "volume_h24_usd": 100.0,
            },
        ]

    def ohlcv(self, network_id, pool_address, token_address, *, timeframe, before_timestamp, limit, aggregate=1):
        assert network_id == "eth"
        assert pool_address == "0xPOOL"
        open_at = 1_000_000.0
        if timeframe == "minute" and before_timestamp > open_at:
            if before_timestamp < open_at + 10_000:
                return [candle(open_at, 10.0, 60), candle(open_at + 300, 11.0, 60)]
        if timeframe == "hour" and before_timestamp > open_at:
            return [
                candle(open_at - 7 * 86400, 5.0, 3600),
                candle(open_at - 3600, 9.0, 3600),
                candle(open_at + 3600, 12.0, 3600),
                candle(open_at + 6 * 3600, 13.0, 3600),
                candle(open_at + 86400, 14.0, 3600),
                candle(open_at + 3 * 86400, 15.0, 3600),
                candle(open_at + 7 * 86400, 16.0, 3600),
            ]
        return []


class FailIdentityResolver:
    def resolve(self, exchange: str, market: str):
        raise AssertionError("stored exact CoinGecko identity should be used")


class CrosswalkIdentityResolver:
    def resolve(self, exchange: str, market: str):
        assert exchange == "bithumb"
        assert market == "KRW-TST"
        return {
            "status": "verified_cross_provider",
            "verified": True,
            "identity": ListingIdentity(
                symbol="TST",
                english_name="Test Token",
                provider="coingecko",
                provider_id="test-token",
                official_domains=("example.org",),
                match_confidence=0.99,
            ),
            "coingecko_crosswalk": {
                "verified": True,
                "contracts_checked": True,
                "contracts": [{"platform_id": "ethereum", "token_address": "0xABC"}],
            },
        }


class NoCoinDetailSource(FakeSource):
    def coin_contracts(self, coin_id: str):
        raise AssertionError("verified crosswalk contracts must prevent duplicate CoinGecko detail fetch")


def test_cycle_persists_only_exact_contract_primary_pool(tmp_path: Path) -> None:
    db = tmp_path / "research.sqlite3"
    _create_listing_case(db)
    store = DexLaunchStore(db)
    cycle = DexLaunchResearchCycle(
        db,
        store=store,
        identity_resolver=FailIdentityResolver(),
        source=FakeSource(),
        state_path=tmp_path / "state.json",
        max_cases_per_run=1,
    )
    result = cycle.run_once()
    assert result["paper_only"] is True
    assert result["can_place_orders"] is False
    assert result["processed"] == 1
    assert result["complete"] == 1

    audit = audit_dex_launch(db)
    assert audit["ok"] is True
    assert audit["case_status_counts"] == {"complete": 1}
    assert audit["asset_count"] == 1
    assert audit["pool_count"] == 2
    assert audit["accepted_pool_count"] == 1
    assert audit["primary_pool_count"] == 1
    assert audit["feature_count"] == 1
    assert audit["paper_only"] is True
    assert audit["can_place_orders"] is False

    row = store.conn.execute(
        "SELECT platform_id,network_id,token_address,identity_status FROM dex_launch_assets"
    ).fetchone()
    assert dict(row) == {
        "platform_id": "ethereum",
        "network_id": "eth",
        "token_address": "0xabc",
        "identity_status": "exact_contract_verified",
    }
    pools = store.conn.execute(
        "SELECT pool_address,gate_status,selected_primary FROM dex_launch_pools ORDER BY selected_primary DESC"
    ).fetchall()
    assert dict(pools[0]) == {"pool_address": "0xpool", "gate_status": "accepted", "selected_primary": 1}
    assert dict(pools[1]) == {"pool_address": "0xlow", "gate_status": "rejected_quality", "selected_primary": 0}
    store.close()


def test_cycle_reuses_verified_crosswalk_contracts_without_second_coin_detail(tmp_path: Path) -> None:
    db = tmp_path / "crosswalk.sqlite3"
    _create_listing_case(
        db,
        identity={
            "provider": "multi-source",
            "provider_id": "provider-123",
            "symbol": "TST",
            "english_name": "Test Token",
        },
    )
    store = DexLaunchStore(db)
    cycle = DexLaunchResearchCycle(
        db,
        store=store,
        identity_resolver=CrosswalkIdentityResolver(),
        source=NoCoinDetailSource(),
        state_path=tmp_path / "crosswalk-state.json",
        max_cases_per_run=1,
    )
    result = cycle.run_once()
    assert result["complete"] == 1
    row = result["results"][0]
    assert row["identity_status"] == "verified_cross_provider"
    assert row["coingecko_id"] == "test-token"
    assert row["contract_source"] == "identity_crosswalk"
    assert row["contract_count"] == 1
    assert row["mapped_contract_count"] == 1
    store.close()


def test_store_does_not_seed_without_listing_cases(tmp_path: Path) -> None:
    store = DexLaunchStore(tmp_path / "empty.sqlite3")
    assert store.listing_cases() == []
    audit = store.audit()
    assert audit["ok"] is True
    assert audit["case_count"] == 0
    store.close()
