from __future__ import annotations

import json
import sqlite3

from b3_trader.dex_launch_snapshot import build_dex_launch_snapshot
from b3_trader.dex_launch_sources import DexCandle
from b3_trader.dex_launch_store import DexLaunchStore


def _feature() -> dict:
    return {
        "version": 1,
        "paper_only": True,
        "shadow_only": True,
        "pool_quality": {
            "reserve_usd": 1_887_904.35,
            "volume_h24_usd": 4_144_247.43,
            "min_liquidity_usd": 25_000.0,
            "min_volume_h24_usd": 10_000.0,
            "passed": True,
        },
        "domestic_listing_window": {
            "status": "collected",
            "reference": {"candle_ts": 1000.0, "price": 0.097, "interval_seconds": 60},
            "pre": {
                "t1d": {"return_to_domestic_open_pct": 12.5},
                "t1h": {"return_to_domestic_open_pct": 0.4},
            },
            "post": {
                "p5m": {"return_from_domestic_open_pct": -0.9},
                "p1h": {"return_from_domestic_open_pct": -1.2},
            },
            "p5m_exact_minute": True,
        },
        "pool_launch_window": {
            "status": "collected",
            "reference": {"candle_ts": 100.0, "price": 0.05, "interval_seconds": 60},
            "pool_age_days_at_domestic_listing": 48.6,
            "windows": {
                "p5m": {"return_from_launch_pct": 2.0},
                "p1h": {"return_from_launch_pct": 5.0},
            },
            "p5m_exact_minute": True,
        },
    }


def test_dex_launch_snapshot_projects_only_compact_identity_pool_and_features(tmp_path) -> None:
    path = tmp_path / "dex.sqlite3"
    store = DexLaunchStore(path)
    try:
        store.conn.execute(
            """
            CREATE TABLE listing_history_cases(
              case_key TEXT PRIMARY KEY,
              domestic_exchange TEXT,
              domestic_market TEXT,
              symbol TEXT,
              domestic_open_at REAL
            )
            """
        )
        store.conn.execute(
            "INSERT INTO listing_history_cases VALUES(?,?,?,?,?)",
            ("bithumb|KRW-FOLD|notice:1654658", "bithumb", "KRW-FOLD", "FOLD", 1000.0),
        )
        store.conn.commit()

        case_key = "bithumb|KRW-FOLD|notice:1654658"
        token = "0xe172e9b6cfbeeb5593bdce3f077356fdb33af904"
        pool_address = "0x909e4a022a7505d44b19b36fe76ee18567379ee4c9697438acde2e159c006c32"
        store.upsert_case_status(
            case_key,
            coingecko_id="interfold",
            status="complete",
            contract_count=1,
            accepted_pool_count=3,
        )
        asset_key = store.upsert_asset(
            case_key=case_key,
            coingecko_id="interfold",
            platform_id="ethereum",
            network_id="eth",
            token_address=token,
            identity_status="exact_contract_verified",
        )
        store.upsert_pool(
            asset_key=asset_key,
            pool={
                "pool_address": pool_address,
                "dex_id": "uniswap-v4-ethereum",
                "name": "FOLD / ETH 0.3%",
                "pool_created_at": 100.0,
                "reserve_usd": 1_887_904.35,
                "volume_h24_usd": 4_144_247.43,
            },
            gate_status="accepted",
            selected_primary=True,
        )
        store.upsert_candles(
            asset_key=asset_key,
            pool_address=pool_address,
            series_kind="domestic_minute",
            candles=[DexCandle(ts=1000.0, interval_seconds=60, open=0.097, high=0.099, low=0.096, close=0.098, volume_usd=12345.0)],
        )
        store.upsert_features(
            asset_key=asset_key,
            pool_address=pool_address,
            feature_version=1,
            features=_feature(),
        )
    finally:
        store.close()

    payload = build_dex_launch_snapshot(path)
    assert payload["paper_only"] is True
    assert payload["shadow_only"] is True
    assert payload["raw_candles_included"] is False
    assert payload["case_count"] == 1
    assert payload["asset_count"] == 1
    assert payload["pool_count"] == 1
    assert payload["feature_count"] == 1
    assert payload["status_counts"] == {"complete": 1}

    case = payload["cases"][0]
    assert case["market"] == "KRW-FOLD"
    assert case["coingecko_id"] == "interfold"
    assert case["contract_count"] == 1
    assert case["accepted_pool_count"] == 3
    asset = case["assets"][0]
    assert asset["token_address"] == token
    assert asset["network_id"] == "eth"
    assert asset["primary_pool"]["pool_address"] == pool_address
    assert asset["primary_pool"]["reserve_usd"] == 1_887_904.35
    assert asset["feature"]["domestic"]["pre_returns"]["t1d"] == 12.5
    assert asset["feature"]["domestic"]["post_returns"]["p5m"] == -0.9
    assert asset["feature"]["domestic"]["p5m_exact_minute"] is True
    assert asset["feature"]["launch"]["returns"]["p1h"] == 5.0

    encoded = json.dumps(payload, ensure_ascii=False)
    assert "dex_launch_candles" not in encoded
    assert '"high"' not in encoded
    assert '"low"' not in encoded
    assert '"close"' not in encoded
    assert "12345.0" not in encoded


def test_dex_launch_snapshot_fails_closed_when_schema_is_missing(tmp_path) -> None:
    path = tmp_path / "empty.sqlite3"
    sqlite3.connect(path).close()
    payload = build_dex_launch_snapshot(path)
    assert payload["path_exists"] is True
    assert payload["raw_candles_included"] is False
    assert payload["cases"] == []
    assert payload["case_count"] == 0
