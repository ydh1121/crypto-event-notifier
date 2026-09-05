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


def ticker_payload(exchange_id="okex", base="ABC", target="USDT"):
    return {
        "tickers": [
            {
                "base": base,
                "target": target,
                "market": {"identifier": exchange_id},
                "is_anomaly": False,
                "is_stale": False,
                "trade_url": "https://example.test/trade",
            }
        ]
    }


def test_exact_provider_exchange_pair_is_verified(monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "get_with_retry",
        lambda *args, **kwargs: (FakeResponse(ticker_payload()), 0),
    )
    result = ListingVenueVerifier().verify(identity(), market())
    assert result["verified"] is True
    assert result["evidence"]["exchange_id"] == "okex"


def test_wrong_pair_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "get_with_retry",
        lambda *args, **kwargs: (FakeResponse(ticker_payload(base="OTHER")), 0),
    )
    result = ListingVenueVerifier().verify(identity(), market())
    assert result["verified"] is False
    assert result["status"] == "provider_pair_not_found"


def test_non_coingecko_identity_does_not_fall_back_to_ticker() -> None:
    result = ListingVenueVerifier().verify(identity("multi-source"), market())
    assert result["verified"] is False
    assert result["status"] == "provider_venue_evidence_unavailable"


def test_coingecko_requests_use_rate_limit_backoff(monkeypatch) -> None:
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(kwargs)
        return FakeResponse(ticker_payload()), 2

    monkeypatch.setattr(module, "get_with_retry", fake_get)
    result = ListingVenueVerifier().verify(identity(), market())
    assert result["verified"] is True
    assert result["evidence"]["retries"] == 2
    assert calls[0]["attempts"] == module.COINGECKO_RETRY_ATTEMPTS
    assert calls[0]["retry_delay_floor_seconds"] == module.COINGECKO_RETRY_DELAY_FLOOR_SECONDS
    assert calls[0]["retry_delay_cap_seconds"] == module.COINGECKO_RETRY_DELAY_CAP_SECONDS


def test_provider_requests_are_paced_between_exchanges(monkeypatch) -> None:
    now = [100.0]
    sleeps = []

    def clock():
        return now[0]

    def sleeper(delay):
        sleeps.append(delay)
        now[0] += delay

    def fake_get(*args, **kwargs):
        now[0] += 0.25
        exchange_id = kwargs["params"]["exchange_ids"]
        return FakeResponse(ticker_payload(exchange_id=exchange_id)), 0

    monkeypatch.setattr(module, "get_with_retry", fake_get)
    verifier = ListingVenueVerifier(clock=clock, sleeper=sleeper)
    assert verifier.verify(identity(), market("okx"))["verified"] is True
    assert verifier.verify(identity(), market("bybit"))["verified"] is True
    assert sleeps == [module.COINGECKO_MIN_REQUEST_INTERVAL_SECONDS]
