from __future__ import annotations

from b3_trader.dex_launch_quality import evaluate_dex_launch_quality
from b3_trader.dex_launch_store import DexLaunchStore


def _feature(*, exact: bool = True, launch: bool = True) -> dict:
    return {
        "version": 1,
        "paper_only": True,
        "shadow_only": True,
        "pool_quality": {
            "reserve_usd": 100_000.0,
            "volume_h24_usd": 50_000.0,
            "min_liquidity_usd": 25_000.0,
            "min_volume_h24_usd": 10_000.0,
            "passed": True,
        },
        "domestic_listing_window": {
            "status": "collected",
            "reference": {"candle_ts": 1000.0, "price": 1.0, "interval_seconds": 60},
            "pre": {},
            "post": {},
            "p5m_exact_minute": exact,
        },
        "pool_launch_window": {
            "status": "collected" if launch else "launch_ohlcv_unavailable",
            "windows": {},
            "p5m_exact_minute": exact if launch else False,
        },
    }


def _asset(store: DexLaunchStore, *, case_key: str, platform: str, token: str, with_feature: bool) -> str:
    asset_key = store.upsert_asset(
        case_key=case_key,
        coingecko_id=case_key.split("|")[0],
        platform_id=platform,
        network_id=platform,
        token_address=token,
        identity_status="exact_contract_verified",
    )
    pool = f"{token}-pool"
    store.upsert_pool(
        asset_key=asset_key,
        pool={
            "pool_address": pool,
            "dex_id": "test-dex",
            "name": "TEST/USDT",
            "pool_created_at": 100.0,
            "reserve_usd": 100_000.0,
            "volume_h24_usd": 50_000.0,
        },
        gate_status="accepted",
        selected_primary=True,
    )
    if with_feature:
        store.upsert_features(
            asset_key=asset_key,
            pool_address=pool,
            feature_version=1,
            features=_feature(),
        )
    return asset_key


def test_quality_gate_derives_multichain_partial_without_mutating_stored_status(tmp_path) -> None:
    path = tmp_path / "quality.sqlite3"
    store = DexLaunchStore(path)
    try:
        full = "full|case"
        partial = "partial|case"
        store.upsert_case_status(full, coingecko_id="full", status="complete", contract_count=2, accepted_pool_count=2)
        store.upsert_case_status(partial, coingecko_id="partial", status="complete", contract_count=2, accepted_pool_count=1)
        _asset(store, case_key=full, platform="eth", token="0x1111", with_feature=True)
        _asset(store, case_key=full, platform="bsc", token="0x2222", with_feature=True)
        _asset(store, case_key=partial, platform="eth", token="0x3333", with_feature=True)
        _asset(store, case_key=partial, platform="bsc", token="0x4444", with_feature=False)
    finally:
        store.close()

    quality = evaluate_dex_launch_quality(path)
    assert quality["ok"] is True
    assert quality["sample_ready"] is False
    assert quality["shadow_score_wired"] is False
    assert quality["can_place_orders"] is False
    assert quality["usable_case_count"] == 2
    assert quality["exact_p5m_case_count"] == 2
    assert quality["complete_partial_case_count"] == 1
    rows = {row["case_key"]: row for row in quality["cases"]}
    assert rows[full]["derived_completion"] == "complete"
    assert rows[partial]["stored_status"] == "complete"
    assert rows[partial]["derived_completion"] == "complete_partial"
    assert rows[partial]["all_expected_assets_researched"] is False


def test_quality_gate_can_open_shadow_candidate_only_when_thresholds_pass(tmp_path) -> None:
    path = tmp_path / "ready.sqlite3"
    store = DexLaunchStore(path)
    try:
        case_key = "ready|case"
        store.upsert_case_status(case_key, coingecko_id="ready", status="complete", contract_count=1, accepted_pool_count=1)
        _asset(store, case_key=case_key, platform="eth", token="0x5555", with_feature=True)
    finally:
        store.close()

    default = evaluate_dex_launch_quality(path)
    assert default["sample_ready"] is False
    assert "usable_cases_below_min:1/20" in default["blocking_reasons"]

    relaxed = evaluate_dex_launch_quality(path, min_usable_cases=1, min_exact_p5m_coverage=1.0)
    assert relaxed["sample_ready"] is True
    assert relaxed["shadow_score_candidate_ready"] is True
    assert relaxed["shadow_score_wired"] is False
    assert relaxed["paper_only"] is True
    assert relaxed["shadow_only"] is True
