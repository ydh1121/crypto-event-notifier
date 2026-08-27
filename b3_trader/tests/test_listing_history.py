from __future__ import annotations

from b3_trader.listing_history import ListingCandle, prelisting_features, price_at_or_before
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


def test_prelisting_windows_are_foreign_quote_momentum_without_currency_mix() -> None:
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
        domestic_open_price=180_000,
        quote_asset="USDT",
    )
    windows = features["windows"]
    assert windows["t7d_price"] is None
    # At an hourly candle's exact start only its opening price is known.
    assert windows["t1d_price"] == 100
    assert windows["t1h_price"] == 140
    # Foreign price at domestic open is the completed -1h candle close=150.
    assert round(windows["t1h_to_foreign_open_pct"], 4) == 7.1429
    assert features["pre_domestic_ath_foreign_quote"] == 155
    assert features["pre_domestic_atl_foreign_quote"] == 90
    assert features["quote_to_krw_at_open"] is None
    assert features["foreign_open_price_krw"] is None
    assert features["domestic_listing_premium_pct"] is None
    assert features["foreign_listing_at"] is None
    assert features["foreign_first_price"] is None
    assert features["foreign_first_to_foreign_open_pct"] is None
    assert features["currency_safe"] is True


def test_domestic_premium_requires_quote_to_krw_conversion() -> None:
    domestic_open = 10 * 24 * 3600.0
    candles = [
        ListingCandle(
            ts=domestic_open - 3600,
            open=140,
            high=155,
            low=135,
            close=150,
        )
    ]
    features = prelisting_features(
        candles,
        domestic_open_at=domestic_open,
        domestic_open_price=220_000,
        quote_asset="USDT",
        quote_to_krw_at_open=1_400,
    )
    assert features["foreign_open_price"] == 150
    assert features["foreign_open_price_krw"] == 210_000
    assert round(features["domestic_listing_premium_pct"], 4) == 4.7619


def test_known_foreign_launch_provenance_is_compared_in_same_quote() -> None:
    domestic_open = 10 * 24 * 3600.0
    candles = [
        ListingCandle(
            ts=domestic_open - 3600,
            open=140,
            high=155,
            low=135,
            close=150,
        )
    ]
    features = prelisting_features(
        candles,
        domestic_open_at=domestic_open,
        domestic_open_price=220_000,
        quote_asset="USDT",
        foreign_listing_at=10_000,
        foreign_first_price=20,
    )
    assert features["foreign_listing_at"] == 10_000
    assert features["foreign_first_price"] == 20
    assert round(features["foreign_first_to_foreign_open_pct"], 4) == 650.0


def test_price_at_or_before_does_not_use_future_candle_close() -> None:
    target = 10_000.0
    candle = ListingCandle(
        ts=target,
        open=10,
        high=100,
        low=5,
        close=90,
        interval_seconds=3600,
    )
    point = price_at_or_before([candle], target)
    assert point is not None
    assert point["price"] == 10
    assert point["price_basis"] == "open"


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
