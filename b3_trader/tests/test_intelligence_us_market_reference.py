from __future__ import annotations

import sqlite3

import pytest

from b3_trader.intelligence_us_market_reference import (
    UsMarketReferenceStore,
    normalize_us_market_reference_observation,
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _obs(source_id: str, ts: float, value: float, *, provider: str = "fixture"):
    return normalize_us_market_reference_observation(
        source_id=source_id,
        observed_at=ts,
        received_at=ts + 5,
        value=value,
        provider_id=provider,
        provider_url="https://example.com/market-data",
        data_rights="test_fixture_only",
        session_state="regular",
        latency_class="delayed",
        delayed_seconds=900,
    )


def test_market_reference_normalizer_requires_supported_series_provider_and_rights() -> None:
    item = _obs("us_sp500", 1000, 6500)
    assert item.series == "SP500"
    assert item.observation_id == "us_sp500:fixture:1000000"
    assert item.freshness_seconds(now=1030) == 30

    with pytest.raises(ValueError, match="unsupported"):
        _obs("dow", 1000, 45000)
    with pytest.raises(ValueError, match="data_rights"):
        normalize_us_market_reference_observation(
            source_id="us_cboe_vix",
            observed_at=1000,
            value=18,
            provider_id="provider",
            provider_url="https://example.com",
            data_rights="",
        )
    with pytest.raises(ValueError, match="https"):
        normalize_us_market_reference_observation(
            source_id="us_nasdaq_composite",
            observed_at=1000,
            value=20000,
            provider_id="provider",
            provider_url="http://example.com",
            data_rights="reviewed",
        )


def test_store_upserts_same_provider_timestamp_and_exposes_freshness() -> None:
    store = UsMarketReferenceStore(_conn())
    first = _obs("us_sp500", 1000, 6500)
    assert store.ingest([first], seen_at=1010, retention_seconds=10_000) == {
        "received": 1,
        "inserted": 1,
        "updated": 0,
    }
    revised = normalize_us_market_reference_observation(
        source_id="us_sp500",
        observed_at=1000,
        received_at=1020,
        value=6501,
        change_pct=0.5,
        provider_id="fixture",
        provider_url="https://example.com/market-data",
        data_rights="test_fixture_only",
        session_state="regular",
        latency_class="delayed",
        delayed_seconds=900,
        version=2,
    )
    assert store.ingest([revised], seen_at=1020, retention_seconds=10_000) == {
        "received": 1,
        "inserted": 0,
        "updated": 1,
    }
    latest = store.latest("us_sp500", now=1030)
    assert latest is not None
    assert latest["value"] == 6501
    assert latest["version"] == 2
    assert latest["freshness_seconds"] == 30
    assert store.latest("us_sp500", now=5000, max_age_seconds=60) is None


def test_nearest_and_aligned_return_fail_closed_when_timestamp_coverage_is_missing() -> None:
    store = UsMarketReferenceStore(_conn())
    store.ingest(
        [
            _obs("us_nasdaq_composite", 1000, 20000),
            _obs("us_nasdaq_composite", 1600, 20200),
        ],
        seen_at=1700,
        retention_seconds=10_000,
    )
    assert store.nearest("us_nasdaq_composite", 1010, max_skew_seconds=20, now=1700)["value"] == 20000
    assert store.nearest("us_nasdaq_composite", 1200, max_skew_seconds=20, now=1700) is None
    result = store.aligned_return(
        "us_nasdaq_composite",
        1005,
        1595,
        max_skew_seconds=10,
        now=1700,
    )
    assert result is not None
    assert result["return_pct"] == pytest.approx(1.0)
    assert result["provider_id"] == "fixture"
    assert store.aligned_return(
        "us_nasdaq_composite",
        1200,
        1595,
        max_skew_seconds=10,
        now=1700,
    ) is None


def test_aligned_return_never_mixes_market_data_providers() -> None:
    store = UsMarketReferenceStore(_conn())
    store.ingest(
        [
            _obs("us_sp500", 1000, 6500, provider="provider_a"),
            _obs("us_sp500", 1600, 6565, provider="provider_b"),
        ],
        seen_at=1700,
        retention_seconds=10_000,
    )
    assert store.aligned_return("us_sp500", 1000, 1600, max_skew_seconds=5, now=1700) is None

    store.ingest(
        [_obs("us_sp500", 1600, 6510, provider="provider_a")],
        seen_at=1701,
        retention_seconds=10_000,
    )
    result = store.aligned_return(
        "us_sp500",
        1000,
        1600,
        max_skew_seconds=5,
        provider_id="provider_a",
        now=1701,
    )
    assert result is not None
    assert result["provider_id"] == "provider_a"
    assert result["return_pct"] == pytest.approx((6510 / 6500 - 1) * 100)


def test_window_is_time_ordered_source_isolated_and_can_pin_provider() -> None:
    store = UsMarketReferenceStore(_conn())
    store.ingest(
        [
            _obs("us_sp500", 1200, 6510),
            _obs("us_sp500", 1000, 6500),
            _obs("us_sp500", 1100, 6490, provider="other"),
            _obs("us_cboe_vix", 1100, 19),
        ],
        seen_at=1300,
        retention_seconds=10_000,
    )
    rows = store.window("us_sp500", 900, 1300, now=1300)
    assert [row["observed_at"] for row in rows] == [1000, 1100, 1200]
    assert all(row["series"] == "SP500" for row in rows)
    pinned = store.window("us_sp500", 900, 1300, provider_id="fixture", now=1300)
    assert [row["observed_at"] for row in pinned] == [1000, 1200]


def test_retention_prunes_old_market_reference_rows() -> None:
    store = UsMarketReferenceStore(_conn())
    store.ingest(
        [
            _obs("us_cboe_vix", 100, 20),
            _obs("us_cboe_vix", 950, 18),
        ],
        seen_at=1000,
        retention_seconds=100,
    )
    rows = store.window("us_cboe_vix", 0, 2000, now=1000)
    assert [row["observed_at"] for row in rows] == [950]
