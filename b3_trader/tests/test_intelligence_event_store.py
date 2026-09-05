from __future__ import annotations

import sqlite3

import pytest

from b3_trader.intelligence_event import normalize_intelligence_event
from b3_trader.intelligence_event_store import IntelligenceEventStore
from b3_trader.intelligence_source_registry import (
    MACRO_CALENDAR,
    default_intelligence_sources,
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_default_registry_contains_required_us_macro_market_and_regulatory_sources() -> None:
    sources = default_intelligence_sources()
    ids = {source.source_id for source in sources}
    assert {
        "us_bls_release_calendar",
        "us_bea_release_schedule",
        "us_fed_fomc_calendar",
        "us_nasdaq_composite",
        "us_sp500",
        "us_cboe_vix",
        "us_sec_press_releases",
        "us_cftc_press_releases",
    } <= ids
    assert all(source.official for source in sources)
    assert not any(source.collection_enabled for source in sources)


def test_normalized_event_identity_is_source_specific_but_content_hash_can_cluster_sources() -> None:
    common = dict(
        source_family=MACRO_CALENDAR,
        event_type="US_CPI",
        title="US CPI August 2026",
        source_url="https://example.com/event",
        published_at=1_780_000_000,
        entities=("US", "BTC"),
        received_at=1_780_000_010,
    )
    first = normalize_intelligence_event(source_id="source_a", **common)
    second = normalize_intelligence_event(source_id="source_b", **common)
    assert first.event_id != second.event_id
    assert first.dedup_hash == second.dedup_hash
    assert first.entities == ("US", "BTC")
    assert first.freshness_seconds(now=1_780_000_030) == 30


def test_store_syncs_registry_and_preserves_known_fields_on_partial_refresh() -> None:
    conn = _conn()
    store = IntelligenceEventStore(conn)
    source_rows = store.source_snapshot()
    assert len(source_rows) == len(default_intelligence_sources())
    assert all(row["collection_enabled"] is False for row in source_rows)

    first = normalize_intelligence_event(
        source_id="us_bls_release_calendar",
        source_family=MACRO_CALENDAR,
        event_type="US_CPI",
        title="Consumer Price Index release",
        source_url="https://www.bls.gov/cpi/",
        external_id="cpi-2026-08",
        published_at=1_780_000_000,
        received_at=1_780_000_010,
        entities=("US",),
        market_scope=("GLOBAL", "CRYPTO"),
        raw_text="official release body",
        summary_ko="미국 소비자물가지수 발표",
        attributes={"reference_period": "2026-08"},
    )
    assert store.ingest([first], seen_at=1_780_000_011) == {
        "received": 1,
        "inserted": 1,
        "updated": 0,
    }

    partial = normalize_intelligence_event(
        source_id="us_bls_release_calendar",
        source_family=MACRO_CALENDAR,
        event_type="US_CPI",
        title="Consumer Price Index release",
        source_url="https://www.bls.gov/cpi/",
        external_id="cpi-2026-08",
        received_at=1_780_000_100,
    )
    assert store.ingest([partial], seen_at=1_780_000_101) == {
        "received": 1,
        "inserted": 0,
        "updated": 1,
    }
    row = store.event(first.event_id, now=1_780_000_120)
    assert row is not None
    assert row["published_at"] == 1_780_000_000
    assert row["raw_text"] == "official release body"
    assert row["summary_ko"] == "미국 소비자물가지수 발표"
    assert row["attributes"] == {"reference_period": "2026-08"}
    assert row["freshness_seconds"] == 120


def test_store_upcoming_uses_scheduled_time_without_marking_future_event_stale() -> None:
    conn = _conn()
    store = IntelligenceEventStore(conn)
    now = 1_780_000_000.0
    event = normalize_intelligence_event(
        source_id="us_fed_fomc_calendar",
        source_family=MACRO_CALENDAR,
        event_type="FOMC_MEETING",
        title="FOMC meeting",
        source_url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        external_id="fomc-2026-09",
        scheduled_at=now + 3600,
        received_at=now,
        market_scope=("GLOBAL", "US_EQUITY", "CRYPTO"),
    )
    store.ingest([event], seen_at=now)
    upcoming = store.upcoming(now=now, horizon_seconds=7200)
    assert len(upcoming) == 1
    assert upcoming[0]["event_id"] == event.event_id
    assert upcoming[0]["freshness_seconds"] is None


def test_store_rejects_family_or_event_type_outside_source_contract() -> None:
    store = IntelligenceEventStore(_conn())
    bad_family = normalize_intelligence_event(
        source_id="us_bls_release_calendar",
        source_family="official_news",
        event_type="US_CPI",
        title="CPI",
        source_url="https://www.bls.gov/cpi/",
        received_at=1_780_000_000,
    )
    with pytest.raises(ValueError, match="source family mismatch"):
        store.ingest([bad_family])

    bad_type = normalize_intelligence_event(
        source_id="us_bls_release_calendar",
        source_family=MACRO_CALENDAR,
        event_type="SP500",
        title="not a BLS event",
        source_url="https://www.bls.gov/",
        received_at=1_780_000_000,
    )
    with pytest.raises(ValueError, match="event type"):
        store.ingest([bad_type])
