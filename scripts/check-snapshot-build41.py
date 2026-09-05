from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def main() -> None:
    budget = text(ROOT / "b3_trader" / "cloudflare_snapshot_budget.py")
    lifecycle = text(ROOT / "b3_trader" / "cloudflare_snapshot_lifecycle.py")
    publisher = text(ROOT / "b3_trader" / "cloudflare_snapshot_publisher.py")
    listing = text(ROOT / "b3_trader" / "listing_history_snapshot.py")
    selectors = text(ROOT / "cloudflare-pages" / "public" / "modules" / "shared" / "selectors.js")
    paper = text(ROOT / "b3_trader" / "multi_exchange_paper.py")
    migrations = "\n".join(text(path) for path in sorted((ROOT / "cloudflare-pages" / "migrations").glob("*.sql")))

    checks = {
        "build41_hard_limit_preserved": (
            "MAX_BODY_BYTES = 1_800_000" in publisher
            and "snapshot is too large" in publisher
            and "MAX_BODY_BYTES = 1_800_000" in budget
        ),
        "build41_reserves_future_headroom": all(token in budget for token in (
            "TARGET_BODY_BYTES = 1_400_000",
            "RESERVED_HEADROOM_BYTES = MAX_BODY_BYTES - TARGET_BODY_BYTES",
            "MAX_PROJECTED_MARKETS_PER_EXCHANGE = 600",
            '"within_target"',
            '"within_hard_limit"',
        )),
        "build41_bithumb_duplicate_removed": all(token in budget for token in (
            "_deduplicate_bithumb",
            '("leaderboard", "best_market", "market_lifecycle")',
            'exchange_records.pop("bithumb", None)',
            'bithumb["projection_inherits_root"] = True',
        )),
        "build41_selector_inherits_root": (
            "return{...pub,...selected" in selectors
            and "recent_records:pub.exchange_records?.[exchange]||pub.recent_records" in selectors
        ),
        "build41_adaptive_optional_compaction": all(token in budget for token in (
            "_trim_strategy_history(public, 384)",
            "_trim_strategy_history(public, 288)",
            "_trim_strategy_history(public, 144)",
            "_trim_recent_records(public, 60, 40)",
            "_trim_coin_matrix_to_visible(public)",
        )),
        "build41_budget_after_listing_projection": (
            'public["listing_history"] = build_listing_history_snapshot(DEMO_DB_PATH)' in lifecycle
            and "return apply_snapshot_budget(snapshot)" in lifecycle
        ),
        "build41_listing_history_stays_compact": (
            "DEFAULT_CASE_LIMIT = 24" in listing
            and '"raw_candles_included": False' in listing
            and "listing_history_candles" not in listing
        ),
        "build41_no_new_d1_research_tables": (
            "listing_history" not in migrations
            and "dex_" not in migrations.lower()
        ),
        "build41_paper_remains_unwired": all(token not in paper for token in (
            "cloudflare_snapshot_budget",
            "apply_snapshot_budget",
            "listing_history_snapshot",
        )),
    }

    print("=== SNAPSHOT BUILD 41 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        print("SNAPSHOT_BUILD41=FAIL")
        raise SystemExit(1)
    print("SNAPSHOT_BUILD41=PASS")


if __name__ == "__main__":
    main()
