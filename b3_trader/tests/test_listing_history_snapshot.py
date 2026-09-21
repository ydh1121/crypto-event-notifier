from __future__ import annotations

import json
from pathlib import Path

from b3_trader.listing_history import ListingCandle
from b3_trader.listing_history_snapshot import build_listing_history_snapshot
from b3_trader.listing_history_store import ListingHistoryStore
from b3_trader.listing_identity import ListingIdentity


def test_listing_history_snapshot_missing_database_is_safe(tmp_path: Path) -> None:
    result = build_listing_history_snapshot(tmp_path / "missing.sqlite3")
    assert result["paper_only"] is True
    assert result["shadow_only"] is True
    assert result["raw_candles_included"] is False
    assert result["path_exists"] is False
    assert result["cases"] == []


def test_listing_history_snapshot_projects_features_without_raw_candles(tmp_path: Path) -> None:
    path = tmp_path / "listing.sqlite3"
    store = ListingHistoryStore(path)
    try:
        identity = ListingIdentity(
            symbol="ABC",
            english_name="Alpha Beta Coin",
            provider="coingecko",
            provider_id="alpha-beta-coin",
            official_domains=("example.org",),
            match_confidence=0.97,
        )
        key = store.upsert_case(
            domestic_exchange="bithumb",
            domestic_market="KRW-ABC",
            domestic_notice_id="notice-40",
            symbol="ABC",
            announcement_at=100,
            domestic_open_at=200,
            domestic_open_price=1200,
            identity=identity,
            identity_verified=True,
            status="complete",
        )
        store.upsert_source(
            case_key=key,
            source_exchange="binance",
            source_market="ABCUSDT",
            base_asset="ABC",
            quote_asset="USDT",
            source_listing_at=10,
            first_price=0.5,
            match_confidence=0.97,
            match_basis={"provider_pair_verification": {"coin_id": "alpha-beta-coin"}},
        )
        store.upsert_candles(
            case_key=key,
            source_exchange="binance",
            source_market="ABCUSDT",
            candles=[
                ListingCandle(
                    ts=200,
                    open=1,
                    high=2,
                    low=0.5,
                    close=1.5,
                    volume=999999,
                    quote_volume=888888,
                    interval_seconds=60,
                )
            ],
        )
        store.upsert_features(
            case_key=key,
            source_exchange="binance",
            source_market="ABCUSDT",
            feature_version=3,
            features={
                "version": 3,
                "quote_to_krw": {
                    "rate": 1400,
                    "source_exchange": "upbit",
                    "source_market": "KRW-USDT",
                },
                "fine_reaction_source": {"status": "collected", "candles": 16, "interval_seconds": 60},
                "prelisting": {
                    "currency_safe": True,
                    "domestic_listing_premium_pct": 4.25,
                    "foreign_first_to_foreign_open_pct": 12.5,
                    "foreign_open_vs_pre_ath_pct": -8.0,
                    "foreign_open_vs_pre_atl_pct": 30.0,
                    "windows": {
                        "t7d_to_foreign_open_pct": 21.0,
                        "t1d_to_foreign_open_pct": 7.0,
                        "t1h_to_foreign_open_pct": 2.0,
                    },
                },
                "foreign_postlisting": {
                    "p5m_source_interval_seconds": 60,
                    "windows": {
                        "p5m_return_pct": 3.5,
                        "p1h_return_pct": 6.0,
                        "p7d_return_pct": -2.0,
                    },
                },
            },
        )
    finally:
        store.close()

    result = build_listing_history_snapshot(path)
    assert result["case_count"] == 1
    assert result["source_count"] == 1
    assert result["feature_count"] == 1
    assert result["status_counts"] == {"complete": 1}
    assert result["raw_candles_included"] is False

    case = result["cases"][0]
    assert case["market"] == "KRW-ABC"
    assert case["domestic_open_price"] == 1200
    source = case["sources"][0]
    assert source["exchange"] == "binance"
    assert source["market"] == "ABCUSDT"
    assert source["verified"] is True
    assert source["feature_version"] == 3
    assert source["domestic_listing_premium_pct"] == 4.25
    assert source["prelisting_returns"]["t1d"] == 7.0
    assert source["prelisting_returns"]["t1h"] == 2.0
    assert source["postlisting_returns"]["p5m"] == 3.5
    assert source["postlisting_returns"]["p7d"] == -2.0
    assert source["p5m_source_interval_seconds"] == 60
    assert source["fine_reaction_status"] == "collected"
    assert source["fine_reaction_candles"] == 16
    assert source["quote_to_krw"]["rate"] == 1400

    encoded = json.dumps(result, ensure_ascii=False)
    assert "999999" not in encoded
    assert "888888" not in encoded
    assert '"open"' not in encoded
    assert '"high"' not in encoded
    assert '"low"' not in encoded
    assert '"close"' not in encoded
    assert '"volume"' not in encoded
