from __future__ import annotations

from pathlib import Path

from b3_trader.listing_history_research_cycle import ListingHistoryResearchCycle, _rotate_cases
from b3_trader.listing_identity import ListingIdentity


def verified_identity() -> ListingIdentity:
    return ListingIdentity(
        symbol="ABC",
        english_name="Alpha Beta Coin",
        provider="coingecko",
        provider_id="alpha-beta-coin",
        official_domains=("example.org",),
        match_confidence=0.95,
    )


def legacy_identity() -> ListingIdentity:
    return ListingIdentity(
        symbol="ABC",
        english_name="Alpha Beta Coin",
        provider="multi-source",
        provider_id="1234",
        official_domains=("example.org",),
        match_confidence=0.95,
    )


class FakePlanner:
    def seed_once(self, *, per_exchange_limit: int):
        return {"status": "seeded", "seeded_cases": 1}


class FakeStore:
    def __init__(self, rows):
        self.rows = rows
        self.upserts = []

    def pending_cases(self, limit: int = 50):
        return list(self.rows)

    def upsert_case(self, **kwargs):
        self.upserts.append(kwargs)
        return "case"


class FakeIdentityResolver:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def resolve(self, exchange: str, market: str):
        self.calls.append((exchange, market))
        return self.result


class FakePriceResolver:
    def __init__(self, price=0.0):
        self.price = price
        self.calls = []

    def resolve(self, exchange: str, market: str, open_at: float):
        self.calls.append((exchange, market, open_at))
        return {"status": "resolved", "found": self.price > 0, "price": self.price}


class FakeCollector:
    def __init__(self, status="tracking_postlisting"):
        self.status = status
        self.cases = []

    def collect_case(self, case):
        self.cases.append(case)
        return {"status": self.status, "sources_ok": 1, "sources": {"fake": {"status": "collected"}}}


def row(*, verified=False, identity=None, open_at=1.0, open_price=0.0):
    return {
        "case_key": "bithumb|KRW-ABC|notice:1",
        "domestic_exchange": "bithumb",
        "domestic_market": "KRW-ABC",
        "domestic_notice_id": "1",
        "symbol": "ABC",
        "announcement_at": 1.0,
        "domestic_open_at": open_at,
        "domestic_open_price": open_price,
        "identity_verified": 1 if verified else 0,
        "identity": identity.to_dict() if identity else {},
        "status": "pending_identity",
    }


def test_rotation_is_bounded_and_wraps() -> None:
    rows = [{"case_key": str(index)} for index in range(5)]
    picked, cursor = _rotate_cases(rows, 4, 3)
    assert [item["case_key"] for item in picked] == ["4", "0", "1"]
    assert cursor == 2


def test_cycle_keeps_unverified_profile_out_of_foreign_sources(tmp_path: Path) -> None:
    store = FakeStore([row()])
    resolver = FakeIdentityResolver({"status": "profile_not_verified", "verified": False, "identity": None})
    collector = FakeCollector()
    cycle = ListingHistoryResearchCycle(
        planner=FakePlanner(),
        store=store,
        identity_resolver=resolver,
        price_resolver=FakePriceResolver(100),
        collector=collector,
        state_path=tmp_path / "state.json",
    )
    result = cycle.run_once()
    assert result["identity_waiting"] == 1
    assert collector.cases == []
    assert store.upserts == []


def test_cycle_reuses_venue_capable_verified_identity_and_resolves_domestic_open(tmp_path: Path, monkeypatch) -> None:
    identity = verified_identity()
    store = FakeStore([row(verified=True, identity=identity, open_at=100, open_price=0)])
    resolver = FakeIdentityResolver({"status": "should_not_run", "verified": False, "identity": None})
    price = FakePriceResolver(250)
    collector = FakeCollector("tracking_postlisting")
    monkeypatch.setattr("b3_trader.listing_history_research_cycle.time.time", lambda: 200.0)
    cycle = ListingHistoryResearchCycle(
        planner=FakePlanner(),
        store=store,
        identity_resolver=resolver,
        price_resolver=price,
        collector=collector,
        state_path=tmp_path / "state.json",
    )
    result = cycle.run_once()
    assert resolver.calls == []
    assert price.calls == [("bithumb", "KRW-ABC", 100.0)]
    assert collector.cases[0].open_price == 250
    assert result["collected"] == 1
    assert store.upserts[0]["identity_verified"] is True


def test_cycle_refreshes_legacy_verified_identity_when_coingecko_identity_is_available(tmp_path: Path, monkeypatch) -> None:
    old_identity = legacy_identity()
    refreshed = verified_identity()
    store = FakeStore([row(verified=True, identity=old_identity, open_at=100, open_price=0)])
    resolver = FakeIdentityResolver({"status": "verified", "verified": True, "identity": refreshed})
    collector = FakeCollector("tracking_postlisting")
    monkeypatch.setattr("b3_trader.listing_history_research_cycle.time.time", lambda: 200.0)
    cycle = ListingHistoryResearchCycle(
        planner=FakePlanner(),
        store=store,
        identity_resolver=resolver,
        price_resolver=FakePriceResolver(250),
        collector=collector,
        state_path=tmp_path / "state.json",
    )
    result = cycle.run_once()
    assert resolver.calls == [("bithumb", "KRW-ABC")]
    assert result["results"][0]["identity"]["status"] == "stored_refreshed"
    assert collector.cases[0].identity.provider == "coingecko"
    assert collector.cases[0].identity.provider_id == "alpha-beta-coin"
    assert store.upserts[0]["identity"].provider == "coingecko"


def test_cycle_does_not_claim_refresh_when_new_identity_is_still_not_venue_capable(tmp_path: Path, monkeypatch) -> None:
    old_identity = legacy_identity()
    still_legacy = ListingIdentity(
        symbol="ABC",
        english_name="Alpha Beta Coin",
        provider="multi-source",
        provider_id="5678",
        official_domains=("example.org",),
        match_confidence=0.99,
    )
    store = FakeStore([row(verified=True, identity=old_identity, open_at=100, open_price=0)])
    resolver = FakeIdentityResolver({"status": "verified", "verified": True, "identity": still_legacy})
    collector = FakeCollector("venue_verification_waiting")
    monkeypatch.setattr("b3_trader.listing_history_research_cycle.time.time", lambda: 200.0)
    cycle = ListingHistoryResearchCycle(
        planner=FakePlanner(),
        store=store,
        identity_resolver=resolver,
        price_resolver=FakePriceResolver(250),
        collector=collector,
        state_path=tmp_path / "state.json",
    )
    result = cycle.run_once()
    assert result["results"][0]["identity"]["status"] == "stored_verified_legacy"
    assert collector.cases[0].identity.provider_id == "1234"
    assert store.upserts[0]["identity"].provider_id == "1234"
