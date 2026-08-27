from __future__ import annotations

import b3_trader.listing_venue_verifier as module
from b3_trader.listing_history_sources import CexSpotMarket
from b3_trader.listing_identity import ListingIdentity
from b3_trader.listing_venue_verifier import ListingVenueVerifier


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def identity(provider="coingecko") -> ListingIdentity:
    return ListingIdentity(
        symbol="ABC",
        english_name="Alpha Beta Coin",
        provider=provider,
        provider_id="alpha-beta-coin",
        official_domains=("example.org",),
        match_confidence=0.95,
    )


def market(exchange="okx", quote="USDT") -> CexSpotMarket:
    return CexSpotMarket(
        exchange=exchange,
        market="ABC-USDT",
        base_asset="ABC",
        quote_asset=quote,
        match_confidence=0.95,
    )


def test_exact_provider_exchange_pair_is_verified(monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "get_with_retry",
        lambda *args, **kwargs: (
            FakeResponse(
                {
                    "tickers": [
                        {
                            "base": "ABC",
                            "target": "USDT",
                            "market": {"identifier": "okex"},
                            "is_anomaly": False,
                            "is_stale": False,
                            "trade_url": "https://example.test/trade",
                        }
                    ]
                }
            ),
            0,
        ),
    )
    result = ListingVenueVerifier().verify(identity(), market())
    assert result["verified"] is True
    assert result["evidence"]["exchange_id"] == "okex"


def test_wrong_pair_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "get_with_retry",
        lambda *args, **kwargs: (
            FakeResponse(
                {
                    "tickers": [
                        {
                            "base": "OTHER",
                            "target": "USDT",
                            "market": {"identifier": "okex"},
                            "is_anomaly": False,
                        }
                    ]
                }
            ),
            0,
        ),
    )
    result = ListingVenueVerifier().verify(identity(), market())
    assert result["verified"] is False
    assert result["status"] == "provider_pair_not_found"


def test_non_coingecko_identity_does_not_fall_back_to_ticker() -> None:
    result = ListingVenueVerifier().verify(identity("multi-source"), market())
    assert result["verified"] is False
    assert result["status"] == "provider_venue_evidence_unavailable"
