from __future__ import annotations

import json
from pathlib import Path

from b3_trader.listing_history_audit import audit_listing_history
from b3_trader.listing_history_store import ListingHistoryStore
from b3_trader.listing_identity import ListingIdentity


def test_audit_missing_database_is_safe(tmp_path: Path) -> None:
    result = audit_listing_history(tmp_path / "missing.sqlite3", rows=3)
    assert result["ok"] is True
    assert result["path_exists"] is False
    assert result["case_count"] == 0


def test_audit_summarizes_cases_sources_and_foreign_postlisting_features(tmp_path: Path) -> None:
    path = tmp_path / "listing.sqlite3"
    store = ListingHistoryStore(path)
    try:
        identity = ListingIdentity(
            symbol="ABC",
            english_name="Alpha Beta Coin",
            provider="coingecko",
            provider_id="alpha-beta-coin",
            official_domains=("example.org",),
            match_confidence=0.95,
        )
        key = store.upsert_case(
            domestic_exchange="bithumb",
            domestic_market="KRW-ABC",
            domestic_notice_id="notice-1",
            symbol="ABC",
            announcement_at=100,
            domestic_open_at=200,
            domestic_open_price=20,
            identity=identity,
            identity_verified=True,
            status="tracking_postlisting",
        )
        store.upsert_source(
            case_key=key,
            source_exchange="binance",
            source_market="ABCUSDT",
            base_asset="ABC",
            quote_asset="USDT",
            source_listing_at=10,
            first_price=2,
            match_confidence=0.95,
            match_basis={"provider_pair_verification": {"coin_id": "alpha-beta-coin"}},
        )
        store.upsert_features(
            case_key=key,
            source_exchange="binance",
            source_market="ABCUSDT",
            feature_version=3,
            features={
                "prelisting": {"status": "ready", "windows": {"t1d": {"price": 10}}},
                "foreign_postlisting": {
                    "status": "tracking",
                    "windows": {
                        "p5m": {"return_pct": 2, "interval_seconds": 60},
                        "p1h": {"return_pct": 5, "interval_seconds": 3600},
                    },
                    "p5m_source_interval_seconds": 60,
                },
                "fine_reaction_source": {"status": "collected", "candles": 15, "interval_seconds": 60},
            },
        )
    finally:
        store.close()

    result = audit_listing_history(path, rows=3)
    assert result["ok"] is True
    assert result["case_count"] == 1
    assert result["status_counts"] == {"tracking_postlisting": 1}
    assert result["identity_verified"] == 1
    assert result["with_domestic_open_price"] == 1
    assert result["source_count"] == 1
    assert result["sources_by_exchange"] == {"binance": 1}
    assert result["feature_count"] == 1
    assert result["latest_cases"][0]["market"] == "KRW-ABC"
    sample = result["feature_samples"][0]
    assert sample["feature_version"] == 3
    assert sample["prelisting_windows"]["t1d"]["price"] == 10
    assert sample["postlisting_windows"]["p5m"]["return_pct"] == 2
    assert sample["postlisting_windows"]["p1h"]["return_pct"] == 5
    assert sample["p5m_source_interval_seconds"] == 60
    assert sample["fine_reaction_status"] == "collected"
    assert sample["fine_reaction_candles"] == 15
    assert json.dumps(result, ensure_ascii=False)


def test_complete_v2_case_is_requeued_once_for_v3_feature_backfill(tmp_path: Path) -> None:
    path = tmp_path / "listing.sqlite3"
    store = ListingHistoryStore(path)
    try:
        identity = ListingIdentity(
            symbol="ABC",
            english_name="Alpha Beta Coin",
            provider="coingecko",
            provider_id="alpha-beta-coin",
            official_domains=("example.org",),
            match_confidence=0.95,
        )
        key = store.upsert_case(
            domestic_exchange="bithumb",
            domestic_market="KRW-ABC",
            domestic_notice_id="notice-1",
            symbol="ABC",
            announcement_at=100,
            domestic_open_at=200,
            domestic_open_price=20,
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
        )
        store.upsert_features(
            case_key=key,
            source_exchange="binance",
            source_market="ABCUSDT",
            feature_version=2,
            features={"version": 2},
        )
        assert [row["case_key"] for row in store.pending_cases(required_feature_version=3)] == [key]
        store.upsert_features(
            case_key=key,
            source_exchange="binance",
            source_market="ABCUSDT",
            feature_version=3,
            features={"version": 3},
        )
        assert store.pending_cases(required_feature_version=3) == []
    finally:
        store.close()
