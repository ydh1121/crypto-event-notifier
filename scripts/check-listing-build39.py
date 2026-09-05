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
    work_lock = text(ROOT / "b3_trader" / "research_work_lock.py")
    supervisor = text(ROOT / "b3_trader" / "research_supervisor.py")
    paper = text(ROOT / "b3_trader" / "multi_exchange_paper.py")
    notice_domain = text(ROOT / "b3_trader" / "market_notice.py")
    notice_store = text(ROOT / "b3_trader" / "market_notice_store.py")
    notice_timing = text(ROOT / "b3_trader" / "market_notice_timing.py")
    notice_sources = text(ROOT / "b3_trader" / "market_notice_sources.py")
    runtime_verify = text(ROOT / "scripts" / "verify-build39-runtime.ps1")
    safe_runtime_runner = text(ROOT / "scripts" / "run-build39-listing-cycle-safe.py")
    profile_identity_api = text(ROOT / "cloudflare-pages" / "functions" / "api" / "coin-profile-identity.ts")
    architecture = text(ROOT / "docs" / "MODULAR_ARCHITECTURE.md")

    pre_windows = ("t7d", "t5d", "t3d", "t1d", "t6h", "t1h")
    post_windows = ("p5m", "p1h", "p6h", "p24h", "p3d", "p7d")
    notice_refresh_at = runtime_verify.find("b3_trader.market_notice_collector")
    locked_cycle_at = runtime_verify.find("run-build39-listing-cycle-safe.py")
    supervisor_init_start = supervisor.find("def __init__(self) -> None:")
    supervisor_lazy_start = supervisor.find("def _run_listing_history_once")
    supervisor_init = (
        supervisor[supervisor_init_start:supervisor_lazy_start]
        if supervisor_init_start >= 0 and supervisor_lazy_start > supervisor_init_start
        else ""
    )
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
        "build39_legacy_identity_refresh": all(token in cycle for token in (
            "_venue_capable_identity", "stored_refreshed", "stored_verified_legacy",
            "refresh_provider", "previous_provider", "coingecko",
        )),
        "build39_venue_provider_pair_verification": all(token in venue for token in (
            "ListingVenueVerifier", "COINGECKO_TICKERS_URL", "exchange_ids",
            "provider_pair_verified", "provider_pair_not_found", "is_anomaly",
        )),
        "build39_transient_venue_not_market_absence": all(token in collector for token in (
            "venue_verification_waiting", "foreign_source_waiting", "no_foreign_market_found",
            'if "venue_unverified" in source_statuses',
        )),
        "build39_cex_sources_modular": all(token in sources for token in (
            "BinanceSpotSource", "OkxSpotSource", "BybitSpotSource",
            "CexSpotMarket", "ListingCandle", "default_cex_sources",
        )),
        "build39_exact_p5m_minute_reaction": (
            all(token in sources for token in (
                "def minute_candles", 'interval="1m"', 'bar="1m"', 'interval="1"',
            ))
            and all(token in domain for token in (
                "fine_candles", 'key == "p5m"', "max_lead_seconds=120",
                "p5m_source_interval_seconds",
            ))
            and all(token in collector for token in (
                "FEATURE_VERSION = 3", "FINE_POST_WINDOW_SECONDS", "minute_candles",
                "fine_reaction_source", "fine_candles=minute_rows",
            ))
        ),
        "build39_history_domain_windows": all(token in domain for token in (*pre_windows, *post_windows, "PRE_LISTING_WINDOWS", "POST_LISTING_WINDOWS", "prelisting_features", "reaction_features")),
        "build39_history_store_separate": all(token in store for token in (
            "ListingHistoryStore", "listing_history_cases", "listing_history_sources",
            "listing_history_candles", "listing_history_features", "domestic_notice_id",
        )),
        "build39_case_key_stable_notice": "notice:" in store and "domestic_notice_id" in store,
        "build39_reseed_preserves_progress": "excluded.status='pending_identity'" in store and "listing_history_cases.status<>'pending_identity'" in store,
        "build39_complete_v2_requeues_for_v3": all(token in store for token in (
            "required_feature_version", "status <> 'complete'", "COALESCE(f.feature_version,0) < ?",
        )) and all(token in cycle for token in (
            "required_feature_version=FEATURE_VERSION", '"feature_version": FEATURE_VERSION',
        )),
        "build39_planner_krw_fail_closed": all(token in planner for token in (
            "ListingHistoryPlanner", "event_kind", "LISTING", "KRW", "pending_identity",
        )),
        "build39_promotional_notice_fail_closed": (
            'if "이벤트" in compact' in notice_domain
            and 'if "이벤트" in compact' in planner
            and "rejected_notice" in planner
            and "rejected_notice" in store
        ),
        "build39_notice_timing_nonzero_preserved": all(token in notice_store for token in (
            "CASE WHEN excluded.published_at>0 THEN excluded.published_at ELSE market_notices.published_at END",
            "CASE WHEN excluded.announcement_at>0 THEN excluded.announcement_at ELSE market_notices.announcement_at END",
            "CASE WHEN excluded.trade_open_at>0 THEN excluded.trade_open_at ELSE market_notices.trade_open_at END",
        )),
        "build39_notice_revision_uses_final_time": all(token in notice_timing for token in (
            "_REVISION_MARKERS", "_revised_datetime", "clocks[-1]",
            "entire bounded segment", "split across line breaks",
        )),
        "build39_upbit_public_notice_id": all(token in notice_sources for token in (
            "_upbit_public_notice_id", "announcement_id", "service_center/notice",
            "stable_id", "public_id", "self._detail(public_id, stable_id)",
        )),
        "build39_upbit_detail_endpoint_fallback": all(token in notice_sources for token in (
            "current_url", "legacy_url", "for notice_id in notice_ids",
            "self.legacy_url}/{clean_id}",
        )),
        "build39_runtime_refreshes_notices_first": (
            notice_refresh_at >= 0 and locked_cycle_at >= 0 and notice_refresh_at < locked_cycle_at
        ),
        "build39_runtime_cycle_uses_shared_lock": (
            all(token in safe_runtime_runner for token in (
                "ResearchWorkLock", "ListingHistoryResearchCycle", "MAX_CASES_PER_RUN",
                "deferred_forward_research_work_lock_busy", '"network_fetches": False',
                '"database_mutation": False', "raise SystemExit(75)",
            ))
            and all(token in runtime_verify for token in (
                "run-build39-listing-cycle-safe.py", "$cycleCode -eq 75",
                "disabled_by_forward_pipeline_dedicated_mode",
                "No listing-history network or DB work was started",
            ))
        ),
        "build39_shared_lock_cross_process": all(token in work_lock for token in (
            "ResearchWorkLock", "LK_NBLCK", "LOCK_EX", "LOCK_NB",
            "automatically if a process exits", "return False",
        )),
        "build39_domestic_open_price_public_candle": all(token in domestic_price for token in (
            "DomesticListingPriceResolver", "BithumbClient", "UpbitClient", "candles_minutes",
            "opening_price_at_or_after", "OPEN_SEARCH_SECONDS", "response_count",
        )) and all(token in domestic_utils for token in (
            "parse_candle_ts", "candle_date_time_kst", "opening_price_at_or_after",
            "first_opening_price_at_or_after_trade_open",
        )),
        "build39_missing_open_first_trade_fail_closed": all(token in domestic_price for token in (
            "resolve_first_trade", "unit=240", "len(rows) < 200", "history_window_exhausted",
            "unit=60", "unit=1", "first_public_trade_candle",
        )) and all(token in cycle for token in (
            "_resolve_domestic_open", "resolve_first_trade", "domestic_open_at=open_at",
            "domestic_open_price=open_price",
        )),
        "build39_domestic_candle_exchange_timezone": all(token in domestic_price for token in (
            "candle_query_to", "KST", "Bithumb documents `to` as a KST clock time",
            "Upbit accepts ISO-8601 UTC Zulu time",
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
        "build39_audit_reads_foreign_postlisting": all(token in audit for token in (
            'payload.get("foreign_postlisting")', "p5m", "p1h", "p6h", "p24h", "p3d", "p7d",
            "p5m_source_interval_seconds", "fine_reaction_status",
        )),
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
            "ListingHistoryResearchCycle", '"listing-history-research": self._run_listing_history_once',
            "def _run_listing_history_once", "def _close_component_resources", "cycle.close()",
        )),
        "build39_listing_history_thread_owned": (
            "self.listing_history_research: ListingHistoryResearchCycle | None = None" in supervisor_init
            and "self.listing_history_research = ListingHistoryResearchCycle()" not in supervisor_init
            and '"listing-history-research": self._run_listing_history_once' in supervisor
            and "self._close_component_resources(name)" in supervisor
        ),
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
