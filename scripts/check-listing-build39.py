from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def main() -> None:
    identity = text(ROOT / "b3_trader" / "listing_identity.py")
    identity_resolver = text(ROOT / "b3_trader" / "listing_identity_resolver.py")
    venue = text(ROOT / "b3_trader" / "listing_venue_verifier.py")
    domain = text(ROOT / "b3_trader" / "listing_history.py")
    store = text(ROOT / "b3_trader" / "listing_history_store.py")
    sources = text(ROOT / "b3_trader" / "listing_history_sources.py")
    planner = text(ROOT / "b3_trader" / "listing_history_planner.py")
    collector = text(ROOT / "b3_trader" / "listing_history_collector.py")
    cycle = text(ROOT / "b3_trader" / "listing_history_research_cycle.py")
    domestic_price = text(ROOT / "b3_trader" / "domestic_listing_price.py")
    domestic_utils = text(ROOT / "b3_trader" / "domestic_candle_utils.py")
    quote_rate = text(ROOT / "b3_trader" / "listing_quote_rate.py")
    audit = text(ROOT / "b3_trader" / "listing_history_audit.py")
    control = text(ROOT / "b3_trader" / "research_control.py")
    supervisor = text(ROOT / "b3_trader" / "research_supervisor.py")
    paper = text(ROOT / "b3_trader" / "multi_exchange_paper.py")
    profile_identity_api = text(ROOT / "cloudflare-pages" / "functions" / "api" / "coin-profile-identity.ts")
    architecture = text(ROOT / "docs" / "MODULAR_ARCHITECTURE.md")

    pre_windows = ("t7d", "t5d", "t3d", "t1d", "t6h", "t1h")
    post_windows = ("p5m", "p1h", "p6h", "p24h", "p3d", "p7d")
    checks = {
        "build39_identity_domain": all(token in identity for token in (
            "ListingIdentity", "listing_identity_gate", "provider_identity_missing",
            "independent_identity_anchor_missing", "MIN_VERIFIED_CONFIDENCE",
        )),
        "build39_identity_not_ticker_only": "ticker alone is never sufficient" in identity.lower(),
        "build39_profile_identity_bridge_auth": all(token in profile_identity_api for token in (
            "INGEST_TOKEN", "bearer(request)", "coinGeckoId", "coingecko_id",
            "verified", "source_count", "match_confidence",
        )),
        "build39_identity_reuses_profile_cache": all(token in identity_resolver for token in (
            "/api/coin-profile-identity", "profile_not_verified", "coingecko_venue_id",
            "listing_identity_gate",
        )),
        "build39_venue_provider_pair_verification": all(token in venue for token in (
            "ListingVenueVerifier", "COINGECKO_TICKERS_URL", "exchange_ids",
            "provider_pair_verified", "provider_pair_not_found", "is_anomaly",
        )),
        "build39_cex_sources_modular": all(token in sources for token in (
            "BinanceSpotSource", "OkxSpotSource", "BybitSpotSource",
            "CexSpotMarket", "ListingCandle", "default_cex_sources",
        )),
        "build39_history_domain_windows": all(token in domain for token in (*pre_windows, *post_windows, "PRE_LISTING_WINDOWS", "POST_LISTING_WINDOWS", "prelisting_features", "reaction_features")),
        "build39_history_store_separate": all(token in store for token in (
            "ListingHistoryStore", "listing_history_cases", "listing_history_sources",
            "listing_history_candles", "listing_history_features", "domestic_notice_id",
        )),
        "build39_case_key_stable_notice": "notice:" in store and "domestic_notice_id" in store,
        "build39_reseed_preserves_progress": "excluded.status='pending_identity'" in store and "listing_history_cases.status<>'pending_identity'" in store,
        "build39_planner_krw_fail_closed": all(token in planner for token in (
            "ListingHistoryPlanner", "event_kind", "LISTING", "KRW", "pending_identity",
        )),
        "build39_domestic_open_price_public_candle": all(token in domestic_price for token in (
            "DomesticListingPriceResolver", "BithumbClient", "UpbitClient", "candles_minutes",
            "nearest_opening_price",
        )) and all(token in domestic_utils for token in (
            "parse_candle_ts", "nearest_opening_price", "opening_price",
        )),
        "build39_quote_to_krw_separate": all(token in quote_rate for token in (
            "ListingQuoteRateResolver", "KRW-USDT", "KRW-USDC", "KRW-BTC",
            "quote_rate_at_or_before", "unsupported_quote", "No stablecoin parity is invented",
        )),
        "build39_currency_safe_features": all(token in domain for token in (
            "quote_to_krw_at_open", "foreign_open_price_krw", "domestic_listing_premium_pct",
            "to_foreign_open_pct", "foreign_first_to_foreign_open_pct", "currency_safe",
            "_candle_price_without_lookahead",
        )) and "to_domestic_pct" not in domain and all(token in collector for token in (
            "ListingQuoteRateResolver", "quote_to_krw", "foreign_postlisting", "reaction_features",
        )),
        "build39_collector_requires_venue_verifier": all(token in collector for token in (
            "ListingVenueVerifier", "_verified_market", "venue_unverified",
            "provider_pair_verification",
        )),
        "build39_launch_price_not_window_inferred": (
            "T-8d" in collector
            and "first_candle" in collector
            and "listing_at - 60.0" in collector
            and "if first_price <= 0 and candles" not in collector
            and "if listing_at <= 0 and candles" not in collector
            and "T-8d is never a proxy" in domain
            and "foreign_listing_at\": first_ts if first_ts > 0 else None" in domain
            and "foreign_first_price\": first if first > 0 else None" in domain
            and "first = rows[0].open" not in domain
            and "first_ts = foreign_listing_at or (rows[0].ts" not in domain
        ),
        "build39_postlisting_tracks_7d": "tracking_postlisting" in collector and "POST_COMPLETE_SECONDS = 7 * 24 * 3600" in collector,
        "build39_cycle_bounded": all(token in cycle for token in (
            "ListingHistoryResearchCycle", "MAX_CASES_PER_RUN = 3",
            "SEED_NOTICE_LIMIT_PER_EXCHANGE", "paper_only", "can_place_orders",
        )),
        "build39_cycle_composes_owners": all(token in cycle for token in (
            "ListingHistoryPlanner", "ListingIdentityResolver", "DomesticListingPriceResolver",
            "ListingHistoryCollector", "ListingHistoryStore",
        )),
        "build39_audit_read_only": all(token in audit for token in (
            "audit_listing_history", "status_counts", "sources_by_exchange", "feature_samples",
            "paper_only", "can_place_orders", "--rows",
        )),
        "build39_supervisor_component": all(token in control for token in (
            '"listing-history-research"', '"default_interval_seconds":900', '"min_interval_seconds":300',
        )) and all(token in supervisor for token in (
            "ListingHistoryResearchCycle", '"listing-history-research": self.listing_history_research.run_once',
            "self.listing_history_research.close()",
        )),
        "build39_paper_remains_unwired": all(token not in paper for token in (
            "ListingHistoryCollector", "ListingHistoryResearchCycle", "listing_history_features",
            "prelisting_features", "ListingQuoteRateResolver",
        )),
        "build39_architecture_rule": all(token in architecture for token in (
            "collector", "store", "feature", "score", "service/API", "page/view",
        )),
    }

    print("=== LISTING BUILD 39 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        print("LISTING_BUILD39=FAIL")
        raise SystemExit(1)
    print("LISTING_BUILD39=PASS")


if __name__ == "__main__":
    main()
