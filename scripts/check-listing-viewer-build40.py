from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def main() -> None:
    projection = text(ROOT / "b3_trader" / "listing_history_snapshot.py")
    lifecycle = text(ROOT / "b3_trader" / "cloudflare_snapshot_lifecycle.py")
    ingest = text(ROOT / "cloudflare-pages" / "functions" / "api" / "ingest.ts")
    research = text(ROOT / "cloudflare-pages" / "public" / "modules" / "pages" / "research.js")
    research_css = text(ROOT / "cloudflare-pages" / "public" / "modules" / "styles" / "research.css")
    main_js = text(ROOT / "cloudflare-pages" / "public" / "modules" / "main.js")
    index = text(ROOT / "cloudflare-pages" / "public" / "index.html")
    paper = text(ROOT / "b3_trader" / "multi_exchange_paper.py")

    checks = {
        "build40_compact_projection_read_only": all(token in projection for token in (
            "build_listing_history_snapshot",
            "listing_history_cases",
            "listing_history_sources",
            "listing_history_features",
            '"raw_candles_included": False',
            '"paper_only": True',
            '"shadow_only": True',
        )),
        "build40_raw_candles_stay_local": (
            "listing_history_candles" not in projection
            and "SELECT candle_ts" not in projection
            and "quote_volume" not in projection
            and '"ohlcv"' not in projection.lower()
        ),
        "build40_projection_has_named_windows": all(token in projection for token in (
            'PRE_WINDOWS = ("t7d", "t5d", "t3d", "t1d", "t6h", "t1h")',
            'POST_WINDOWS = ("p5m", "p1h", "p6h", "p24h", "p3d", "p7d")',
            "domestic_listing_premium_pct",
            "prelisting_returns",
            "postlisting_returns",
            "p5m_source_interval_seconds",
        )),
        "build40_existing_snapshot_transport": all(token in lifecycle for token in (
            "build_listing_history_snapshot",
            'public["listing_history"]',
            "DEMO_DB_PATH",
        )) and all(token in ingest for token in (
            "JSON.stringify(payload.public)",
            "INSERT INTO snapshots",
            "SNAPSHOT_RETENTION = 24",
        )),
        "build40_no_d1_listing_migration": "listing_history" not in text(ROOT / "cloudflare-pages" / "migrations" / "0001.sql"),
        "build40_research_viewer_panel": all(token in research for token in (
            "listing_history",
            "renderListingHistory",
            "listing-history-panel",
            "domestic_open_price",
            "domestic_listing_premium_pct",
            "pre.t1d",
            "pre.t1h",
            "post.p5m",
            "post.p1h",
            "post.p24h",
            "post.p7d",
            "NO RAW CANDLES",
        )),
        "build40_viewer_responsive_style": all(token in research_css for token in (
            ".listing-history-panel",
            ".listing-case-grid",
            ".listing-metrics",
            "@media(max-width:820px)",
            "@media(max-width:520px)",
        )),
        "build40_cache_boundary": (
            "./pages/research.js?v=40" in main_js
            and 'crypto-viewer-build" content="2026.08.28-40"' in index
            and "/modules/styles/research.css?v=4" in index
            and "/modules/main.js?v=15" in index
        ),
        "build40_paper_remains_unwired": all(token not in paper for token in (
            "listing_history_snapshot",
            "build_listing_history_snapshot",
            "listing_history_features",
        )),
    }

    print("=== LISTING VIEWER BUILD 40 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        print("LISTING_VIEWER_BUILD40=FAIL")
        raise SystemExit(1)
    print("LISTING_VIEWER_BUILD40=PASS")


if __name__ == "__main__":
    main()
