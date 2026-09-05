from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    module = _text("b3_trader/historical_listing_backfill.py")
    verifier = _text("scripts/verify-historical-listing-build47.py")
    supervisor = _text("b3_trader/research_supervisor.py")
    quality = _text("b3_trader/dex_launch_quality.py")

    checks = {
        "build47_additive_historical_backfill": "class HistoricalListingBackfill" in module,
        "build47_official_bithumb_pages": "https://feed.bithumb.com" in module and '"page": page' in module,
        "build47_official_upbit_pages": "https://api-manager.upbit.com/api/v1/announcements" in module and '"per_page": self.per_page' in module,
        "build47_listing_detail_only": "if preliminary.event_kind != LISTING" in module,
        "build47_final_krw_gate": "is_krw_listing_notice" in module,
        "build47_stable_notice_case_key": "domestic_notice_id=notice.notice_id" in module,
        "build47_bounded_pages": "DEFAULT_PAGES_PER_EXCHANGE = 4" in module and "MAX_PAGES_PER_EXCHANGE = 8" in module,
        "build47_cursor_is_local_state": "historical-listing-backfill-state.json" in module and "next_page" in module,
        "build47_no_supervisor_wiring": "historical-listing" not in supervisor.lower(),
        "build47_no_identity_or_dex_execution": "ListingIdentityResolver" not in module and "DexLaunchResearchCycle" not in module and "GeckoTerminal" not in module,
        "build47_quality_thresholds_unchanged": "MIN_USABLE_CASES = 20" in quality and "MIN_EXACT_P5M_COVERAGE = 0.60" in quality,
        "build47_direct_verifier_bootstrap": "sys.path.insert" in verifier and "--import-check" in verifier,
        "build47_no_score_decision_order_wiring": '"can_place_orders": False' in module and '"score_wired": False' in module and ".place_order(" not in module,
    }
    print("=== HISTORICAL LISTING BUILD 47 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("HISTORICAL_LISTING_BUILD47=FAIL")
    print("HISTORICAL_LISTING_BUILD47=PASS")


if __name__ == "__main__":
    main()
