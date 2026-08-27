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
    sector_page = text(PUBLIC / "modules" / "pages" / "sectors-v36.js")
    sector_table = text(PUBLIC / "modules" / "pages" / "sector-coin-table.js")
    continuity = text(PUBLIC / "modules" / "shared" / "ui-continuity.js")
    lifecycle_js = text(PUBLIC / "modules" / "shared" / "market-lifecycle.js")
    lifecycle_css = text(PUBLIC / "modules" / "styles" / "market-lifecycle.css")
    sector_market_css = text(PUBLIC / "modules" / "styles" / "sector-market-data.css")
    sector_api = text(ROOT / "cloudflare-pages" / "functions" / "api" / "sector-summary.ts")
    lifecycle_domain = text(ROOT / "b3_trader" / "market_lifecycle.py")
    lifecycle_store = text(ROOT / "b3_trader" / "market_lifecycle_store.py")
    lifecycle_service = text(ROOT / "b3_trader" / "market_lifecycle_service.py")
    notice_domain = text(ROOT / "b3_trader" / "market_notice.py")
    notice_sources = text(ROOT / "b3_trader" / "market_notice_sources.py")
    notice_store = text(ROOT / "b3_trader" / "market_notice_store.py")
    notice_collector = text(ROOT / "b3_trader" / "market_notice_collector.py")
    control = text(ROOT / "b3_trader" / "research_control.py")
    supervisor = text(ROOT / "b3_trader" / "research_supervisor.py")
    market_features = text(ROOT / "b3_trader" / "market_feature_store.py")
    returns = text(ROOT / "b3_trader" / "market_return_windows.py")
    detail_projection = text(ROOT / "b3_trader" / "market_detail_feature_projection.py")
    paper = text(ROOT / "b3_trader" / "multi_exchange_paper.py")
    architecture = text(ROOT / "docs" / "MODULAR_ARCHITECTURE.md")

    checks = {
        "sector_build_38": 'crypto-sector-build" content="2026.08.27-38' in index,
        "main_v14": '/modules/main.js?v=14' in index and 'sectors-v36.js?v=38' in main_js,
        "continuity_shared": all(token in continuity for token in ("installSamePageInteractionContinuity", "captureScrollableAncestors", "data-preserve-scroll")),
        "continuity_installed_once": "installSamePageInteractionContinuity(root)" in main_js,
        "sector_scroll_anchor": 'data-preserve-scroll' in sector_page,
        "sector_table_modular": "renderSectorCoinTable" in sector_page and "sector-coin-row columns" not in sector_page,
        "sector_table_history": all(token in sector_table for token in ("d5_pct", "D-5", "d1_pct", "D-1", "change_24h_pct", "24H")),
        "sector_table_uses_lifecycle_helper": "lifecycleMeta" in sector_table and "market-lifecycle.js" in sector_table,
        "lifecycle_shared_mapping": all(token in lifecycle_js for token in ("NEW_LISTING", "CAUTION", "TERMINATION_SCHEDULED", "TERMINATED")),
        "lifecycle_color_contract": "market-lifecycle-caution" in lifecycle_css and "market-lifecycle-terminated" in lifecycle_css,
        "sector_history_responsive": "sector-return-strip" in sector_market_css and "repeat(6" in sector_market_css,
        "sector_api_projects_returns": all(token in sector_api for token in ("$.return_windows.d1_pct", "$.return_windows.d2_pct", "$.return_windows.d3_pct", "$.return_windows.d4_pct", "$.return_windows.d5_pct")),
        "sector_api_projects_lifecycle": "$.lifecycle_state" in sector_api and "lifecycle_counts" in sector_api,
        "return_window_domain": all(token in returns for token in ("d1_pct", "d2_pct", "d3_pct", "d4_pct", "d5_pct")),
        "return_window_store_reuses_memory": "research_market_memory_mx" in market_features and "return_windows" in market_features,
        "detail_projection_thin": "return_windows" in detail_projection and "lifecycle_state" in detail_projection,
        "lifecycle_domain_separate": "decide_lifecycle_state" in lifecycle_domain and "merge_lifecycle_state" in lifecycle_domain,
        "lifecycle_store_separate": "MarketLifecycleStore" in lifecycle_store and "market_lifecycle_events" in lifecycle_store,
        "lifecycle_partial_api_fail_closed": "MIN_EXISTING_COVERAGE_RATIO" in lifecycle_store and "observation_rejected" in lifecycle_store,
        "notice_domain_separate": all(token in notice_domain for token in ("MarketNotice", "classify_notice_title", "extract_notice_symbols", "lifecycle_state_for_notice")),
        "notice_sources_separate": "BithumbNoticeSource" in notice_sources and "UpbitNoticeSource" in notice_sources and "get_with_retry" in notice_sources,
        "notice_store_separate": "MarketNoticeStore" in notice_store and "market_lifecycle_notice_state" in notice_store,
        "notice_unknown_timestamp_fail_closed": "never allowed to become a current lifecycle override" in notice_store and "effective_at <= 0" in notice_store,
        "lifecycle_service_composes_notice": "MarketLifecycleService" in lifecycle_service and "merge_lifecycle_state" in lifecycle_service and "notice_only" in lifecycle_service,
        "notice_collector_order_independent": "MarketNoticeCollector" in notice_collector and "sources_failed" in notice_collector and "can_place_orders" in notice_collector,
        "notice_supervisor_component": '"market-notice-watch"' in control and '"market-notice-watch": self.market_notice_collector.run_once' in supervisor,
        "paper_consumes_lifecycle_service": "MarketLifecycleService" in paper and "MarketLifecycleStore" not in paper,
        "paper_does_not_parse_notices": "BithumbNoticeSource" not in paper and "UpbitNoticeSource" not in paper and "classify_notice_title" not in paper,
        "paper_lifecycle_stays_shadow": '"shadow_only": True' in paper and '"market_lifecycle_shadow_only": True' in paper,
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
