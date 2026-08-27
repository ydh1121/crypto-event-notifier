from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "cloudflare-pages" / "public"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def main() -> None:
    index = text(PUBLIC / "index.html")
    main_js = text(PUBLIC / "modules" / "main.js")
    selectors = text(PUBLIC / "modules" / "shared" / "selectors.js")
    sector_page = text(PUBLIC / "modules" / "pages" / "sectors-v36.js")
    sector_table = text(PUBLIC / "modules" / "pages" / "sector-coin-table.js")
    lifecycle_panel = text(PUBLIC / "modules" / "pages" / "market-lifecycle-panel.js")
    continuity = text(PUBLIC / "modules" / "shared" / "ui-continuity.js")
    lifecycle_js = text(PUBLIC / "modules" / "shared" / "market-lifecycle.js")
    lifecycle_css = text(PUBLIC / "modules" / "styles" / "market-lifecycle.css")
    lifecycle_panel_css = text(PUBLIC / "modules" / "styles" / "market-lifecycle-panel.css")
    sector_market_css = text(PUBLIC / "modules" / "styles" / "sector-market-data.css")
    sector_api = text(ROOT / "cloudflare-pages" / "functions" / "api" / "sector-summary.ts")
    lifecycle_domain = text(ROOT / "b3_trader" / "market_lifecycle.py")
    lifecycle_store = text(ROOT / "b3_trader" / "market_lifecycle_store.py")
    lifecycle_service = text(ROOT / "b3_trader" / "market_lifecycle_service.py")
    lifecycle_projection = text(ROOT / "b3_trader" / "cloudflare_snapshot_lifecycle.py")
    notice_domain = text(ROOT / "b3_trader" / "market_notice.py")
    notice_timing = text(ROOT / "b3_trader" / "market_notice_timing.py")
    notice_sources = text(ROOT / "b3_trader" / "market_notice_sources.py")
    notice_store = text(ROOT / "b3_trader" / "market_notice_store.py")
    notice_collector = text(ROOT / "b3_trader" / "market_notice_collector.py")
    notice_audit = text(ROOT / "b3_trader" / "market_notice_audit.py")
    control = text(ROOT / "b3_trader" / "research_control.py")
    supervisor = text(ROOT / "b3_trader" / "research_supervisor.py")
    market_features = text(ROOT / "b3_trader" / "market_feature_store.py")
    returns = text(ROOT / "b3_trader" / "market_return_windows.py")
    detail_projection = text(ROOT / "b3_trader" / "market_detail_feature_projection.py")
    paper = text(ROOT / "b3_trader" / "multi_exchange_paper.py")
    architecture = text(ROOT / "docs" / "MODULAR_ARCHITECTURE.md")

    timing_fields = ("announcement_at", "deposit_at", "trade_open_at", "termination_at")
    checks = {
        "sector_build_38": 'crypto-sector-build" content="2026.08.27-38' in index,
        "main_v14": '/modules/main.js?v=14' in index and 'sectors-v36.js?v=38' in main_js,
        "continuity_shared": all(token in continuity for token in ("installSamePageInteractionContinuity", "captureScrollableAncestors", "data-preserve-scroll")),
        "continuity_installed_once": "installSamePageInteractionContinuity(root)" in main_js,
        "sector_scroll_anchor": 'data-preserve-scroll' in sector_page,
        "sector_table_modular": "renderSectorCoinTable" in sector_page and "sector-coin-row columns" not in sector_page,
        "sector_table_history": all(token in sector_table for token in ("d5_pct", "D-5", "d1_pct", "D-1", "change_24h_pct", "24H")),
        "sector_table_uses_lifecycle_helper": "lifecycleMeta" in sector_table and "market-lifecycle.js" in sector_table,
        "lifecycle_shared_mapping": all(token in lifecycle_js for token in ("LISTING_ANNOUNCED", "NEW_LISTING", "CAUTION", "TERMINATION_SCHEDULED", "TERMINATED")),
        "lifecycle_color_contract": "market-lifecycle-caution" in lifecycle_css and "market-lifecycle-terminated" in lifecycle_css,
        "lifecycle_selector_shared": "marketLifecycle" in selectors and "notice_only" in selectors,
        "lifecycle_panel_modular": all(token in lifecycle_panel for token in ("renderMarketLifecyclePanel", "refreshMarketLifecyclePanel", "notice_only", "LISTING_ANNOUNCED", "data-market-lifecycle-panel")),
        "lifecycle_panel_live_refresh": "refreshMarketLifecyclePanel" in sector_page and "m.type==='snapshot'" in sector_page,
        "lifecycle_panel_structured_schedule": "scheduleText" in lifecycle_panel and "trade_open_at" in lifecycle_panel and "termination_at" in lifecycle_panel and "dt(" in lifecycle_panel,
        "lifecycle_panel_responsive": "market-lifecycle-row" in lifecycle_panel_css and "@media(max-width:700px)" in lifecycle_panel_css,
        "sector_history_responsive": "sector-return-strip" in sector_market_css and "repeat(6" in sector_market_css,
        "sector_api_projects_returns": all(token in sector_api for token in ("$.return_windows.d1_pct", "$.return_windows.d2_pct", "$.return_windows.d3_pct", "$.return_windows.d4_pct", "$.return_windows.d5_pct")),
        "sector_api_projects_lifecycle": "$.lifecycle_state" in sector_api and "lifecycle_counts" in sector_api,
        "return_window_domain": all(token in returns for token in ("PRIOR_DAY_COUNT = 5", "prior_daily_returns", 'result[f"d{day}_pct"]', "range(1, PRIOR_DAY_COUNT + 1)")),
        "return_window_store_reuses_memory": "research_market_memory_mx" in market_features and "return_windows" in market_features,
        "detail_projection_thin": "return_windows" in detail_projection and "lifecycle_state" in detail_projection,
        "lifecycle_domain_separate": all(token in lifecycle_domain for token in ("decide_lifecycle_state", "merge_lifecycle_state", "lifecycle_entry_policy", "LifecycleEntryPolicy")),
        "lifecycle_store_separate": "MarketLifecycleStore" in lifecycle_store and "market_lifecycle_events" in lifecycle_store,
        "lifecycle_partial_api_fail_closed": "MIN_EXISTING_COVERAGE_RATIO" in lifecycle_store and "observation_rejected" in lifecycle_store,
        "lifecycle_notice_projection": all(token in lifecycle_projection for token in ("notice_only", "notice_state_count", "notice_overlay")),
        "notice_domain_separate": all(token in notice_domain for token in ("MarketNotice", "classify_notice_title", "extract_notice_symbols", "lifecycle_state_for_notice")),
        "notice_domain_structured_timing": all(token in notice_domain for token in timing_fields) and "parse_notice_timing" in notice_domain,
        "notice_timing_pure_module": all(token in notice_timing for token in ("NoticeTiming", "parse_notice_timing", "DEPOSIT_LABELS", "TRADE_OPEN_LABELS", "TERMINATION_LABELS", "Date-only wording")),
        "notice_sources_separate": "BithumbNoticeSource" in notice_sources and "UpbitNoticeSource" in notice_sources and "get_with_retry" in notice_sources,
        "notice_sources_detail_timing": "_upbit_detail_text" in notice_sources and 'f"{self.current_url}/{notice_id}"' in notice_sources and "detail_text=detail_text" in notice_sources,
        "notice_store_separate": "MarketNoticeStore" in notice_store and "market_lifecycle_notice_state" in notice_store,
        "notice_store_additive_timing": "_ensure_notice_timing_columns" in notice_store and all(token in notice_store for token in timing_fields),
        "notice_unknown_timestamp_fail_closed": "never allowed to become a current lifecycle override" in notice_store and "effective_at <= 0" in notice_store,
        "notice_audit_compact": all(token in notice_audit for token in ("TIMING_FIELDS", "structured_sample", "latest_sample", "--rows")),
        "lifecycle_service_composes_notice": "MarketLifecycleService" in lifecycle_service and "merge_lifecycle_state" in lifecycle_service and "notice_only" in lifecycle_service,
        "lifecycle_service_projects_timing": "NOTICE_DETAIL_FIELDS" in lifecycle_service and all(token in lifecycle_service for token in timing_fields),
        "lifecycle_service_owns_entry_policy": "def entry_policy" in lifecycle_service and "lifecycle_entry_policy" in lifecycle_service,
        "notice_collector_order_independent": "MarketNoticeCollector" in notice_collector and "sources_failed" in notice_collector and "can_place_orders" in notice_collector,
        "notice_supervisor_component": '"market-notice-watch"' in control and '"market-notice-watch": self.market_notice_collector.run_once' in supervisor,
        "paper_consumes_lifecycle_service": "MarketLifecycleService" in paper and "MarketLifecycleStore" not in paper,
        "paper_does_not_parse_notices": "BithumbNoticeSource" not in paper and "UpbitNoticeSource" not in paper and "classify_notice_title" not in paper,
        "paper_termination_gate_only": all(token in paper for token in ("def _entry_policy", "lifecycle.entry_policy", "lifecycle_entry_policy(NORMAL", "lifecycle_block", '"paper_gate": "termination_only"', '"market_lifecycle_mode": "termination_gate_only"', '"caution_remains_shadow_for_current_adaptive": True')),
        "paper_enriches_detail_via_feature_store": "MarketFeatureStore" in paper and "enrich_market_detail" in paper,
        "architecture_rule_present": all(token in architecture for token in ("collector", "store", "feature", "score", "Viewer", "PAPER")),
    }

    print("=== SECTOR BUILD 38 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        print("SECTOR_BUILD38=FAIL")
        raise SystemExit(1)
    print("SECTOR_BUILD38=PASS")


if __name__ == "__main__":
    main()
