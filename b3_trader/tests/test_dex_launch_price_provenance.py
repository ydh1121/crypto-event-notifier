from __future__ import annotations

from b3_trader.dex_launch_features import FEATURE_VERSION, launch_window_features
from b3_trader.dex_launch_snapshot import _compact_feature
from b3_trader.dex_launch_sources import DexCandle


def candle(ts: float, price: float, *, volume: float, interval: int = 60) -> DexCandle:
    return DexCandle(
        ts=ts,
        open=price,
        high=price,
        low=price,
        close=price,
        volume_usd=volume,
        interval_seconds=interval,
    )


def test_feature_v2_separates_observed_launch_price_from_validated_liquidity_price() -> None:
    created = 1_000_000.0
    minute = [
        candle(created + 60, 0.01, volume=12.5),
        candle(created + 300, 0.012, volume=400.0),
    ]
    result = launch_window_features(
        pool_created_at=created,
        hourly=[],
        minute=minute,
        domestic_open_at=created + 30 * 86400,
    )

    assert FEATURE_VERSION == 2
    assert result["status"] == "collected"
    assert result["reference"]["price"] == 0.01
    assert result["reference"]["volume_usd"] == 12.5
    proof = result["launch_price_provenance"]
    assert proof["status"] == "observed_price_only_historical_liquidity_unverified"
    assert proof["observed_reference_price"] == 0.01
    assert proof["observed_reference_volume_usd"] == 12.5
    assert proof["historical_liquidity_verified"] is False
    assert proof["validated_launch_price"] is None
    assert proof["validated_launch_at"] is None


def test_compact_snapshot_fails_closed_for_legacy_launch_feature() -> None:
    payload = {
        "version": 1,
        "pool_quality": {"reserve_usd": 50_000, "volume_h24_usd": 20_000, "passed": True},
        "domestic_listing_window": {"status": "collected", "reference": {"price": 100}, "pre": {}, "post": {}},
        "pool_launch_window": {
            "status": "collected",
            "reference": {"candle_ts": 100.0, "price": 0.05, "interval_seconds": 60},
            "windows": {},
        },
    }
    compact = _compact_feature(payload, 1)
    proof = compact["launch"]["provenance"]

    assert compact["feature_version"] == 1
    assert compact["launch"]["reference_price"] == 0.05
    assert proof["status"] == "legacy_feature_without_historical_liquidity_provenance"
    assert proof["historical_liquidity_verified"] is False
    assert proof["validated_launch_price"] is None
    assert proof["source_limitation"] == "feature_v1_predates_historical_liquidity_provenance"


def test_compact_snapshot_preserves_v2_launch_provenance_without_raw_ohlcv() -> None:
    payload = {
        "version": 2,
        "pool_quality": {"reserve_usd": 50_000, "volume_h24_usd": 20_000, "passed": True},
        "domestic_listing_window": {"status": "collected", "reference": {"price": 100}, "pre": {}, "post": {}},
        "pool_launch_window": {
            "status": "collected",
            "reference": {"candle_ts": 100.0, "price": 0.05, "volume_usd": 250.0, "interval_seconds": 60},
            "launch_price_provenance": {
                "status": "observed_price_only_historical_liquidity_unverified",
                "observed_reference_ts": 100.0,
                "observed_reference_price": 0.05,
                "observed_reference_volume_usd": 250.0,
                "historical_liquidity_verified": False,
                "validated_launch_price": None,
                "validated_launch_at": None,
                "source_limitation": "ohlcv_has_trade_volume_but_not_historical_pool_reserve",
            },
            "windows": {},
        },
    }
    compact = _compact_feature(payload, 2)
    proof = compact["launch"]["provenance"]

    assert compact["feature_version"] == 2
    assert compact["launch"]["reference_volume_usd"] == 250.0
    assert proof["observed_reference_volume_usd"] == 250.0
    assert proof["historical_liquidity_verified"] is False
    assert proof["validated_launch_price"] is None
