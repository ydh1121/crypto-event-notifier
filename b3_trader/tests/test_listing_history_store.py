from __future__ import annotations

from pathlib import Path

from b3_trader.listing_history import ListingCandle
from b3_trader.listing_history_store import ListingHistoryStore
from b3_trader.listing_identity import ListingIdentity


def test_listing_history_store_round_trip(tmp_path: Path) -> None:
    store = ListingHistoryStore(tmp_path / "listing.sqlite3")
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
            symbol="ABC",
            announcement_at=100,
            domestic_open_at=200,
            domestic_open_price=1000,
            identity=identity,
            identity_verified=True,
            status="collecting",
        )
        store.upsert_source(
            case_key=key,
            source_exchange="okx",
            source_market="ABC-USDT",
            base_asset="ABC",
            quote_asset="USDT",
            source_listing_at=50,
            first_price=10,
            match_confidence=0.95,
            match_basis={"identity_gate": "verified"},
        )
        stored = store.upsert_candles(
            case_key=key,
            source_exchange="okx",
            source_market="ABC-USDT",
            candles=[
                ListingCandle(ts=100, open=10, high=12, low=9, close=11, volume=5, quote_volume=55),
                ListingCandle(ts=200, open=11, high=13, low=10, close=12, volume=6, quote_volume=72),
            ],
        )
        assert stored == 2
        rows = store.candles(case_key=key, source_exchange="okx", source_market="ABC-USDT")
        assert [row.close for row in rows] == [11, 12]
        store.upsert_features(
            case_key=key,
            source_exchange="okx",
            source_market="ABC-USDT",
            features={"windows": {"t1d_price": 11}},
        )
        pending = store.pending_cases()
        assert len(pending) == 1
        assert pending[0]["case_key"] == key
        assert pending[0]["identity"]["provider_id"] == "alpha-beta-coin"
    finally:
        store.close()
