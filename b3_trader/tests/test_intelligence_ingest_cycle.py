from __future__ import annotations

import sqlite3

from b3_trader.intelligence_event import normalize_intelligence_event
from b3_trader.intelligence_ingest_cycle import IntelligenceIngestCycle
from b3_trader.intelligence_source_registry import MACRO_CALENDAR, OFFICIAL_NEWS


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _cpi(now: float):
    return normalize_intelligence_event(
        source_id="us_bls_release_calendar",
        source_family=MACRO_CALENDAR,
        event_type="US_CPI",
        title="Consumer Price Index release",
        source_url="https://www.bls.gov/cpi/",
        external_id="cpi-fixture",
        scheduled_at=now + 3600,
        received_at=now,
        entities=("US",),
    )


def _sec(now: float):
    return normalize_intelligence_event(
        source_id="us_sec_press_releases",
        source_family=OFFICIAL_NEWS,
        event_type="US_SEC_POLICY",
        title="SEC Clarifies the Application of Federal Securities Laws to Crypto Assets",
        source_url="https://www.sec.gov/newsroom/press-releases/fixture",
        external_id="sec-fixture",
        published_at=now - 60,
        received_at=now,
        entities=("US", "SEC", "CRYPTO"),
        attributes={"direction": None, "severity": None},
    )


def test_ingest_cycle_defaults_to_network_disabled_and_calls_nothing() -> None:
    called: list[str] = []

    def fetch(now: float):
        called.append("bls")
        return [_cpi(now)]

    cycle = IntelligenceIngestCycle(conn=_conn(), fetchers={"us_bls_release_calendar": fetch})
    result = cycle.run_once(source_ids=["us_bls_release_calendar"], now=1000)
    assert result["status"] == "network_disabled"
    assert result["network_enabled"] is False
    assert result["paper_only"] is True
    assert result["can_place_orders"] is False
    assert result["score_mutation"] is False
    assert called == []
    assert cycle.store.recent(limit=10, now=1000) == []


def test_enabled_cycle_ingests_multiple_sources_into_shared_store() -> None:
    calls: list[str] = []

    def bls(now: float):
        calls.append("bls")
        return [_cpi(now)]

    def sec(now: float):
        calls.append("sec")
        return [_sec(now)]

    cycle = IntelligenceIngestCycle(
        conn=_conn(),
        fetchers={
            "us_bls_release_calendar": bls,
            "us_sec_press_releases": sec,
        },
    )
    result = cycle.run_once(
        network_enabled=True,
        source_ids=["us_bls_release_calendar", "us_sec_press_releases"],
        now=2000,
    )
    assert result["status"] == "ok"
    assert result["events_received"] == 2
    assert result["events_inserted"] == 2
    assert result["events_updated"] == 0
    assert result["source_failures"] == 0
    assert calls == ["bls", "sec"]
    rows = cycle.store.recent(limit=10, now=2100)
    assert {row["source_id"] for row in rows} == {
        "us_bls_release_calendar",
        "us_sec_press_releases",
    }


def test_source_failure_is_isolated_and_other_sources_continue() -> None:
    calls: list[str] = []

    def broken(now: float):
        calls.append("broken")
        raise RuntimeError("fixture source failure")

    def sec(now: float):
        calls.append("sec")
        return [_sec(now)]

    cycle = IntelligenceIngestCycle(
        conn=_conn(),
        fetchers={
            "us_bls_release_calendar": broken,
            "us_sec_press_releases": sec,
        },
    )
    result = cycle.run_once(
        network_enabled=True,
        source_ids=["us_bls_release_calendar", "us_sec_press_releases"],
        now=3000,
    )
    assert result["status"] == "partial"
    assert result["source_failures"] == 1
    assert result["events_inserted"] == 1
    assert result["source_results"]["us_bls_release_calendar"]["status"] == "source_error"
    assert result["source_results"]["us_sec_press_releases"]["status"] == "ok"
    assert calls == ["broken", "sec"]


def test_unsupported_requested_source_is_fail_closed_without_network_guess() -> None:
    cycle = IntelligenceIngestCycle(conn=_conn(), fetchers={})
    result = cycle.run_once(network_enabled=True, source_ids=["unknown_source"], now=4000)
    assert result["status"] == "partial"
    assert result["source_failures"] == 1
    assert result["events_inserted"] == 0
    assert result["source_results"]["unknown_source"]["status"] == "unsupported_source"


def test_repeated_ingest_updates_same_event_instead_of_duplication() -> None:
    def bls(now: float):
        return [_cpi(now)]

    cycle = IntelligenceIngestCycle(conn=_conn(), fetchers={"us_bls_release_calendar": bls})
    first = cycle.run_once(network_enabled=True, source_ids=["us_bls_release_calendar"], now=5000)
    second = cycle.run_once(network_enabled=True, source_ids=["us_bls_release_calendar"], now=5010)
    assert first["events_inserted"] == 1
    assert second["events_inserted"] == 0
    assert second["events_updated"] == 1
    assert len(cycle.store.recent(limit=10, now=5100)) == 1
