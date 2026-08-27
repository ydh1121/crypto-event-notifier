from __future__ import annotations

from types import SimpleNamespace

import b3_trader.listing_identity_resolver as module
from b3_trader.listing_identity_resolver import ListingIdentityResolver


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_resolver_accepts_only_remote_and_local_verified_identity(monkeypatch) -> None:
    monkeypatch.setattr(ListingIdentityResolver, "_endpoint", staticmethod(lambda: ("https://viewer/api/coin-profile-identity", "secret")))
    monkeypatch.setattr(
        module,
        "get_with_retry",
        lambda *args, **kwargs: (
            FakeResponse(
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
                }
            ),
            0,
        ),
    )
    result = ListingIdentityResolver().resolve("bithumb", "KRW-ABC")
    assert result["verified"] is True
    assert result["identity"].provider_id == "1234"
    assert result["identity"].official_domains == ("example.org",)


def test_resolver_keeps_single_source_profile_pending(monkeypatch) -> None:
    monkeypatch.setattr(ListingIdentityResolver, "_endpoint", staticmethod(lambda: ("https://viewer/api/coin-profile-identity", "secret")))
    monkeypatch.setattr(
        module,
        "get_with_retry",
        lambda *args, **kwargs: (
            FakeResponse(
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
                }
            ),
            0,
        ),
    )
    result = ListingIdentityResolver().resolve("bithumb", "KRW-ABC")
    assert result["verified"] is False
    assert result["identity"] is None
