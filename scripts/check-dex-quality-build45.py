from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    quality = text("b3_trader/dex_launch_quality.py")
    cycle = text("b3_trader/dex_launch_research_cycle.py")

    checks = {
        "build45_read_only_quality_gate": (
            "def evaluate_dex_launch_quality" in quality
            and "shadow_score_wired" in quality
            and '"can_place_orders": False' in quality
            and '"paper_only": True' in quality
            and '"shadow_only": True' in quality
        ),
        "build45_minimum_sample_gate": (
            "MIN_USABLE_CASES = 20" in quality
            and "MIN_EXACT_P5M_COVERAGE = 0.60" in quality
            and "usable_cases_below_min" in quality
            and "exact_p5m_coverage_below_min" in quality
        ),
        "build45_multichain_partial_is_derived": (
            'derived = "complete_partial"' in quality
            and '"expected_research_assets"' in quality
            and '"all_expected_assets_researched"' in quality
            and "upsert_case_status" not in quality
        ),
        "build45_existing_collection_semantics_unchanged": (
            'status = "complete"' in cycle
            and "DexLaunchResearchCycle" not in quality
        ),
        "build45_raw_ohlcv_not_queried": (
            "dex_launch_candles" not in quality
            and "raw OHLCV rows" in quality
        ),
        "build45_no_score_decision_order_wiring": (
            "from .decision" not in quality
            and "from .order" not in quality
            and "place_order(" not in quality
            and "shadow_score_wired\": False" in quality
        ),
    }

    print("=== DEX QUALITY BUILD 45 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        failed = [name for name, ok in checks.items() if not ok]
        raise SystemExit(f"DEX_QUALITY_BUILD45=FAIL: {', '.join(failed)}")
    print("DEX_QUALITY_BUILD45=PASS")


if __name__ == "__main__":
    main()
