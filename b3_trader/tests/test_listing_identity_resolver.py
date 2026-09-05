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


def test_resolver_crosswalks_verified_provider_by_name_symbol_and_domain(monkeypatch) -> None:
    monkeypatch.setattr(ListingIdentityResolver, "_endpoint", staticmethod(lambda: ("https://viewer/api/coin-profile-identity", "secret")))

    profile = {
        "ok": True,
        "found": True,
        "verified": True,
        "identity": {
            "symbol": "FOLD",
            "english_name": "Interfold",
            "korean_name": "인터폴드",
            "provider": "multi-source",
            "provider_id": "987654",
            "homepage": "https://interfold.example",
            "match_confidence": 0.99,
            "last_verified_at": 100,
        },
        "gate": {"research_status": "verified", "source_count": 3},
    }
    search = {
        "coins": [
            {"id": "wrong-fold", "symbol": "FOLD", "name": "Different Fold", "market_cap_rank": 10},
            {"id": "interfold", "symbol": "FOLD", "name": "The Interfold", "market_cap_rank": 700},
        ]
    }
    detail = {
        "id": "interfold",
        "symbol": "fold",
        "name": "The Interfold",
        "links": {"homepage": ["https://interfold.example/"]},
        "platforms": {"ethereum": "0xABCDEF"},
    }

    def fake_get(url, **kwargs):
        if url == "https://viewer/api/coin-profile-identity":
            return FakeResponse(profile), 0
        if url == module.CG_SEARCH_URL:
            assert kwargs["params"]["query"] == "Interfold"
            return FakeResponse(search), 0
        if url == module.CG_DETAIL_URL.format(coin_id="interfold"):
            return FakeResponse(detail), 0
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(module, "get_with_retry", fake_get)
    result = ListingIdentityResolver().resolve("bithumb", "KRW-FOLD")
    assert result["verified"] is True
    assert result["status"] == "verified_cross_provider"
    assert result["identity"].provider == "coingecko"
    assert result["identity"].provider_id == "interfold"
    assert result["coingecko_venue_id"] == "interfold"
    assert result["coingecko_crosswalk"]["basis"]["domain_overlap"] == ["interfold.example"]
    assert result["coingecko_crosswalk"]["basis"]["search_query_basis"] == "verified_english_name"
    assert result["coingecko_crosswalk"]["contracts_checked"] is True
    assert result["coingecko_crosswalk"]["contracts"] == [
        {"platform_id": "ethereum", "token_address": "0xabcdef"}
    ]


def test_resolver_never_promotes_same_ticker_with_wrong_project_name(monkeypatch) -> None:
    monkeypatch.setattr(ListingIdentityResolver, "_endpoint", staticmethod(lambda: ("https://viewer/api/coin-profile-identity", "secret")))
    profile = {
        "ok": True,
        "found": True,
        "verified": True,
        "identity": {
            "symbol": "FOLD",
            "english_name": "Interfold",
            "provider": "multi-source",
            "provider_id": "987654",
            "homepage": "https://interfold.example",
            "match_confidence": 0.99,
            "last_verified_at": 100,
        },
        "gate": {"research_status": "verified", "source_count": 3},
    }
    search = {"coins": [{"id": "clarity-protocol", "symbol": "FOLD", "name": "Clarity Protocol"}]}

    def fake_get(url, **kwargs):
        if url == "https://viewer/api/coin-profile-identity":
            return FakeResponse(profile), 0
        if url == module.CG_SEARCH_URL:
            assert kwargs["params"]["query"] == "Interfold"
            return FakeResponse(search), 0
        raise AssertionError("wrong-name ticker candidate must not be detailed")

    monkeypatch.setattr(module, "get_with_retry", fake_get)
    result = ListingIdentityResolver().resolve("bithumb", "KRW-FOLD")
    assert result["verified"] is True
    assert result["identity"].provider == "multi-source"
    assert result["identity"].provider_id == "987654"
    assert result["coingecko_venue_id"] == ""
    assert result["coingecko_crosswalk"]["status"] == "coingecko_crosswalk_unverified"
