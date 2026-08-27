from __future__ import annotations

from b3_trader.listing_history import ListingCandle, prelisting_features
from b3_trader.listing_identity import ListingIdentity, listing_identity_gate


def test_listing_identity_rejects_ticker_only() -> None:
    gate = listing_identity_gate(ListingIdentity(symbol="ABC", match_confidence=1.0))
    assert gate["verified"] is False
    assert "provider_identity_missing" in gate["reasons"]
    assert "independent_identity_anchor_missing" in gate["reasons"]


def test_listing_identity_accepts_provider_plus_domain() -> None:
    identity = ListingIdentity(
        symbol="ABC",
        english_name="Alpha Beta Coin",
        provider="coingecko",
        provider_id="alpha-beta-coin",
        official_domains=("example.org",),
        match_confidence=0.96,
    )
    gate = listing_identity_gate(identity)
    assert gate["verified"] is True
    assert gate["provider_backed"] is True
    assert gate["domain_backed"] is True


def test_prelisting_windows_keep_missing_values_null() -> None:
    domestic_open = 10 * 24 * 3600.0
    candles = [
        ListingCandle(
            ts=domestic_open - 24 * 3600,
            open=100,
            high=110,
            low=90,
            close=105,
        ),
        ListingCandle(
            ts=domestic_open - 3600,
            open=140,
            high=155,
            low=135,
            close=150,
        ),
    ]
    features = prelisting_features(
        candles,
        domestic_open_at=domestic_open,
        domestic_open_price=180,
    )
    windows = features["windows"]
    assert windows["t7d_price"] is None
    assert windows["t1d_price"] == 105
    assert windows["t1h_price"] == 150
    assert round(windows["t1h_to_domestic_pct"], 4) == 20.0
    assert features["pre_domestic_ath"] == 155
    assert features["pre_domestic_atl"] == 90
    assert features["foreign_listing_at"] is None
    assert features["foreign_first_price"] is None
    assert features["foreign_first_to_domestic_pct"] is None


def test_known_foreign_launch_provenance_is_used() -> None:
    domestic_open = 10 * 24 * 3600.0
    candles = [
        ListingCandle(
            ts=domestic_open - 24 * 3600,
            open=100,
            high=110,
            low=90,
            close=105,
        )
    ]
    features = prelisting_features(
        candles,
        domestic_open_at=domestic_open,
        domestic_open_price=180,
        foreign_listing_at=10_000,
        foreign_first_price=20,
    )
    assert features["foreign_listing_at"] == 10_000
    assert features["foreign_first_price"] == 20
    assert round(features["foreign_first_to_domestic_pct"], 4) == 800.0


def test_unconfirmed_candle_is_not_used() -> None:
    domestic_open = 1_000_000.0
    candles = [
        ListingCandle(
            ts=domestic_open - 3600,
            open=10,
            high=12,
            low=9,
            close=11,
            confirmed=False,
        )
    ]
    features = prelisting_features(candles, domestic_open_at=domestic_open, domestic_open_price=20)
    assert features["windows"]["t1h_price"] is None
    assert features["candle_count"] == 0
