from __future__ import annotations

import b3_trader.listing_identity_resolver as module
from b3_trader.listing_identity_resolver import ListingIdentityResolver


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def _install_response(monkeypatch, payload) -> None:
    monkeypatch.setattr(ListingIdentityResolver, "_endpoint", staticmethod(lambda: ("https://viewer/api/coin-profile-identity", "secret")))
    monkeypatch.setattr(module, "get_with_retry", lambda *args, **kwargs: (FakeResponse(payload), 0))


def test_resolver_accepts_only_remote_and_local_verified_identity(monkeypatch) -> None:
    _install_response(
        monkeypatch,
        {
            "ok": True,
            "found": True,
            "verified": True,
            "identity": {
                "symbol": "ABC",
                "english_name": "Alpha Beta Coin",
                "provider": "multi-source",
                "provider_id": "1234",
                "homepage": "https://example.org",
                "match_confidence": 0.95,
                "last_verified_at": 100,
            },
            "gate": {"research_status": "verified", "source_count": 3},
        },
    )
    result = ListingIdentityResolver().resolve("bithumb", "KRW-ABC")
    assert result["verified"] is True
    assert result["identity"].provider_id == "1234"
    assert result["identity"].official_domains == ("example.org",)


def test_resolver_prefers_existing_coingecko_evidence_for_venue_checks(monkeypatch) -> None:
    _install_response(
        monkeypatch,
        {
            "ok": True,
            "found": True,
            "verified": True,
            "identity": {
                "symbol": "ABC",
                "english_name": "Alpha Beta Coin",
                "provider": "multi-source",
                "provider_id": "1234",
                "homepage": "https://example.org",
                "match_confidence": 0.95,
                "last_verified_at": 100,
                "evidence": [
                    {
                        "source": "coingecko",
                        "url": "https://www.coingecko.com/en/coins/alpha-beta-coin",
                    }
                ],
            },
            "gate": {"research_status": "verified", "source_count": 3},
        },
    )
    result = ListingIdentityResolver().resolve("bithumb", "KRW-ABC")
    assert result["verified"] is True
    assert result["identity"].provider == "coingecko"
    assert result["identity"].provider_id == "alpha-beta-coin"
    assert result["coingecko_venue_id"] == "alpha-beta-coin"


def test_resolver_keeps_single_source_profile_pending(monkeypatch) -> None:
    _install_response(
        monkeypatch,
        {
            "ok": True,
            "found": True,
            "verified": False,
            "identity": {
                "symbol": "ABC",
                "english_name": "Alpha Beta Coin",
                "provider": "coingecko",
                "provider_id": "abc",
                "homepage": "https://example.org",
                "match_confidence": 0.82,
                "last_verified_at": 100,
            },
            "gate": {"research_status": "single_source", "source_count": 1},
        },
    )
    result = ListingIdentityResolver().resolve("bithumb", "KRW-ABC")
    assert result["verified"] is False
    assert result["identity"] is None
