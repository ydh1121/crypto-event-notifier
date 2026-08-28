from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    source = text("b3_trader/dex_launch_sources.py")
    store = text("b3_trader/dex_launch_store.py")
    features = text("b3_trader/dex_launch_features.py")
    cycle = text("b3_trader/dex_launch_research_cycle.py")
    resolver = text("b3_trader/listing_identity_resolver.py")
    retry = text("b3_trader/http_retry.py")
    verifier = text("scripts/verify-dex-build42.py")
    lifecycle = text("b3_trader/cloudflare_snapshot_lifecycle.py")
    dex_snapshot = text("b3_trader/dex_launch_snapshot.py") if (ROOT / "b3_trader/dex_launch_snapshot.py").exists() else ""

    checks = {
        "build42_exact_contract_identity": (
            "coin_contracts" in source
            and '"platform_id"' in source
            and '"token_address"' in source
            and "normalize_contract_address" in source
        ),
        "build42_dynamic_network_mapping": (
            '"coingecko_asset_platform_id"' in source
            and '"/networks"' in source
            and "MAX_NETWORK_PAGES" in source
        ),
        "build42_token_address_pool_discovery": (
            "/tokens/{token}/pools" in source
            and '"h24_volume_usd_liquidity_desc"' in source
        ),
        "build42_address_oriented_ohlcv": (
            "/pools/{pool}/ohlcv/{frame}" in source
            and '"token": token' in source
            and '"before_timestamp"' in source
        ),
        "build42_public_rate_budget": (
            "DEFAULT_GT_MIN_INTERVAL_SECONDS = 6.2" in source
            and "MAX_CASES_PER_RUN = 1" in cycle
            and "MAX_CONTRACTS_PER_CASE = 2" in cycle
        ),
        "build42_rate_limit_backoff": (
            "retry_delay_floor_seconds" in retry
            and "retry_delay_cap_seconds" in retry
            and "GT_RETRY_DELAY_FLOOR_SECONDS = 12.0" in source
            and "CG_RETRY_DELAY_FLOOR_SECONDS = 15.0" in source
            and "retry_delay_floor_seconds=GT_RETRY_DELAY_FLOOR_SECONDS" in source
            and "retry_delay_floor_seconds=CG_RETRY_DELAY_FLOOR_SECONDS" in source
            and "CG_RETRY_DELAY_FLOOR_SECONDS = 15.0" in resolver
        ),
        "build42_liquidity_and_volume_gate": (
            "MIN_POOL_LIQUIDITY_USD = 25_000.0" in cycle
            and "MIN_POOL_VOLUME_H24_USD = 10_000.0" in cycle
            and "and _num(pool.get(\"volume_h24_usd\")) >= self.min_volume_h24_usd" in cycle
        ),
        "build42_local_additive_tables": all(
            name in store
            for name in (
                "dex_launch_case_status",
                "dex_launch_assets",
                "dex_launch_pools",
                "dex_launch_candles",
                "dex_launch_features",
            )
        ),
        "build42_exact_p5m_minute": (
            '"p5m_exact_minute"' in features
            and "def _exact_minute_point" in features
            and 'int(point.get("interval_seconds") or 0) == 60' in features
            and 'abs(float(point.get("candle_ts") or 0.0) - float(point.get("target_ts") or 0.0)) <= 1.0' in features
        ),
        "build42_verified_cross_provider_bridge": (
            "def _crosswalk_coingecko" in resolver
            and '"verified_cross_provider"' in resolver
            and "crosswalk = self._crosswalk_coingecko(identity)" in resolver
            and '"coingecko_crosswalk"' in resolver
        ),
        "build42_crosswalk_not_ticker_search": (
            'params={"query": identity.english_name}' in resolver
            and 'str(row.get("symbol") or "").strip().upper() == identity.symbol' in resolver
            and "_strong_name_match(identity.english_name, row.get(\"name\"))" in resolver
            and '"search_query_basis": "verified_english_name"' in resolver
        ),
        "build42_crosswalk_contract_reuse": (
            '"contracts_checked": True' in resolver
            and '"contracts": platform_contracts' in resolver
            and "def _verified_crosswalk_contracts" in cycle
            and 'contract_source = "identity_crosswalk" if bridged_contracts is not None else "coingecko_detail"' in cycle
            and "if bridged_contracts is not None:" in cycle
        ),
        "build42_targeted_case_qa": (
            '"--case-key"' in verifier
            and "_target_listing_case" in verifier
            and '"targeted_research"' in verifier
            and "cycle._research_case(target, time.time())" in verifier
        ),
        "build42_raw_dex_not_cloud_projected": (
            "dex_launch_candles" not in lifecycle
            and "SELECT" not in lifecycle
            and (
                not dex_snapshot
                or (
                    '"raw_candles_included": False' in dex_snapshot
                    and "dex_launch_candles" not in dex_snapshot
                )
            )
        ),
        "build42_paper_remains_unwired": (
            '"paper_only": True' in cycle
            and '"can_place_orders": False' in cycle
            and "from .decision" not in cycle
            and "from .order" not in cycle
        ),
        "build42_no_ticker_pool_search": (
            "/search/pools" not in source
            and "search/pools" not in cycle
        ),
    }
    print("=== DEX BUILD 42 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        failed = [name for name, ok in checks.items() if not ok]
        raise SystemExit(f"DEX_BUILD42=FAIL: {', '.join(failed)}")
    print("DEX_BUILD42=PASS")


if __name__ == "__main__":
    main()
