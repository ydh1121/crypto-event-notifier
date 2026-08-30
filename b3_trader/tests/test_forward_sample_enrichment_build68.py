from __future__ import annotations

from pathlib import Path

from b3_trader.dex_shadow_score_v2_preregistration import FORWARD_CUTOFF_TS
from b3_trader.forward_sample_enrichment import ForwardSampleEnrichment, _forward_candidates
from b3_trader.listing_history_store import ListingHistoryStore
from b3_trader.listing_identity import ListingIdentity


def _seed(path: Path, *, market: str, notice_id: str, announcement_at: float, open_at: float) -> str:
    store = ListingHistoryStore(path)
    try:
        return store.upsert_case(
            domestic_exchange="bithumb",
            domestic_market=market,
            domestic_notice_id=notice_id,
            symbol=market.split("-", 1)[-1],
            announcement_at=announcement_at,
            domestic_open_at=open_at,
            domestic_open_price=0.0,
            identity=None,
            identity_verified=False,
            status="pending_identity",
        )
    finally:
        store.close()


def test_build68_candidates_exclude_pre_cutoff_and_include_pending(tmp_path: Path) -> None:
    path = tmp_path / "research.sqlite3"
    _seed(path, market="KRW-OLD", notice_id="old", announcement_at=FORWARD_CUTOFF_TS - 100, open_at=FORWARD_CUTOFF_TS - 50)
    confirmed = _seed(path, market="KRW-NEW", notice_id="new", announcement_at=FORWARD_CUTOFF_TS + 100, open_at=FORWARD_CUTOFF_TS + 200)
    pending = _seed(path, market="KRW-PEND", notice_id="pend", announcement_at=FORWARD_CUTOFF_TS + 300, open_at=0.0)

    rows = _forward_candidates(path, now=FORWARD_CUTOFF_TS + 1000, state={})
    keys = {row["case_key"] for row in rows}
    assert keys == {confirmed, pending}
    assert all(
        row["domestic_open_at"] >= FORWARD_CUTOFF_TS
        or (row["domestic_open_at"] <= 0 and row["announcement_at"] >= FORWARD_CUTOFF_TS)
        for row in rows
    )


def test_build68_no_forward_case_is_safe_noop(tmp_path: Path) -> None:
    path = tmp_path / "research.sqlite3"
    _seed(path, market="KRW-OLD", notice_id="old", announcement_at=FORWARD_CUTOFF_TS - 100, open_at=FORWARD_CUTOFF_TS - 50)

    def fail_factory(**kwargs):
        raise AssertionError("network-capable owner must not be created without forward candidates")

    runner = ForwardSampleEnrichment(
        path,
        state_path=tmp_path / "state.json",
        listing_cycle_factory=fail_factory,
        dex_cycle_factory=fail_factory,
    )
    result = runner.run_once()
    assert result["status"] == "waiting_no_forward_cases"
    assert result["processed"] == 0
    assert result["network_fetches"] is False
    assert result["database_mutation"] is False


class _FakeCollector:
    def collect_case(self, case):
        return {"status": "complete", "sources_ok": 1}


class _FakeListingCycle:
    processed: list[str] = []

    def __init__(self, *, path: Path):
        self.path = Path(path)
        self.store = ListingHistoryStore(self.path)
        self.collector = _FakeCollector()

    def _resolve_identity(self, row):
        self.processed.append(str(row["case_key"]))
        return (
            ListingIdentity(
                symbol=str(row["symbol"]),
                english_name=str(row["symbol"]),
                provider="coingecko",
                provider_id=str(row["symbol"]).lower(),
                official_domains=("example.com",),
                match_confidence=1.0,
                verified_at=FORWARD_CUTOFF_TS + 1,
            ),
            {"status": "fake_verified", "verified": True},
        )

    def _resolve_domestic_open(self, row, now):
        return float(row["domestic_open_at"]), 100.0, {
            "status": "fake_stored",
            "found": True,
            "open_at": float(row["domestic_open_at"]),
            "price": 100.0,
        }

    def close(self):
        self.store.close()


class _FakeDexCycle:
    processed: list[str] = []

    def __init__(self, *, path: Path):
        self.path = Path(path)

    def _research_case(self, row, now):
        self.processed.append(str(row["case_key"]))
        return {"case_key": str(row["case_key"]), "status": "complete"}

    def close(self):
        pass


def test_build68_processes_only_one_forward_case(tmp_path: Path) -> None:
    _FakeListingCycle.processed = []
    _FakeDexCycle.processed = []
    path = tmp_path / "research.sqlite3"
    older = _seed(path, market="KRW-A", notice_id="a", announcement_at=FORWARD_CUTOFF_TS + 100, open_at=FORWARD_CUTOFF_TS + 200)
    newer = _seed(path, market="KRW-B", notice_id="b", announcement_at=FORWARD_CUTOFF_TS + 300, open_at=FORWARD_CUTOFF_TS + 400)

    def quality_fn(_path):
        return {
            "cases": [
                {"case_key": newer, "usable_for_shadow_analysis": True},
                {"case_key": older, "usable_for_shadow_analysis": False},
            ]
        }

    runner = ForwardSampleEnrichment(
        path,
        state_path=tmp_path / "state.json",
        quality_fn=quality_fn,
        listing_cycle_factory=_FakeListingCycle,
        dex_cycle_factory=_FakeDexCycle,
    )
    result = runner.run_once()
    assert result["status"] == "enriched"
    assert result["processed"] == 1
    assert result["usable_gain"] == 1
    assert _FakeListingCycle.processed == [newer]
    assert _FakeDexCycle.processed == [newer]
    assert result["forward_boundary"]["pre_cutoff_cases_processed"] == 0
