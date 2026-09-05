from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_launch_quality import (  # noqa: E402
    MIN_EXACT_P5M_COVERAGE,
    MIN_USABLE_CASES,
    evaluate_dex_launch_quality,
)


def main() -> None:
    if "--import-check" in sys.argv:
        print("DEX_QUALITY_BUILD45_IMPORT=PASS")
        return

    quality = evaluate_dex_launch_quality()
    cases = quality.get("cases") if isinstance(quality.get("cases"), list) else []
    partial = [
        {
            "case_key": row.get("case_key"),
            "coingecko_id": row.get("coingecko_id"),
            "stored_status": row.get("stored_status"),
            "derived_completion": row.get("derived_completion"),
            "expected_research_assets": row.get("expected_research_assets"),
            "usable_feature_asset_count": row.get("usable_feature_asset_count"),
        }
        for row in cases
        if isinstance(row, dict) and row.get("derived_completion") == "complete_partial"
    ]
    payload = {
        "ok": bool(quality.get("ok")),
        "sample_ready": bool(quality.get("sample_ready")),
        "shadow_score_candidate_ready": bool(quality.get("shadow_score_candidate_ready")),
        "blocking_reasons": quality.get("blocking_reasons") or [],
        "thresholds": quality.get("thresholds") or {},
        "case_count": int(quality.get("case_count") or 0),
        "stored_status_counts": quality.get("stored_status_counts") or {},
        "derived_completion_counts": quality.get("derived_completion_counts") or {},
        "usable_case_count": int(quality.get("usable_case_count") or 0),
        "usable_asset_count": int(quality.get("usable_asset_count") or 0),
        "exact_p5m_case_count": int(quality.get("exact_p5m_case_count") or 0),
        "exact_p5m_coverage": float(quality.get("exact_p5m_coverage") or 0.0),
        "launch_feature_case_count": int(quality.get("launch_feature_case_count") or 0),
        "complete_partial_case_count": int(quality.get("complete_partial_case_count") or 0),
        "partial_cases": partial,
        "safety": {
            "paper_only": bool(quality.get("paper_only")),
            "shadow_only": bool(quality.get("shadow_only")),
            "can_place_orders": bool(quality.get("can_place_orders")),
            "shadow_score_wired": bool(quality.get("shadow_score_wired")),
        },
    }
    print("=== DEX QUALITY BUILD 45 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    safe = bool(
        payload["ok"]
        and payload["thresholds"].get("min_usable_cases") == MIN_USABLE_CASES
        and float(payload["thresholds"].get("min_exact_p5m_coverage") or 0.0) == MIN_EXACT_P5M_COVERAGE
        and payload["safety"]["paper_only"]
        and payload["safety"]["shadow_only"]
        and not payload["safety"]["can_place_orders"]
        and not payload["safety"]["shadow_score_wired"]
    )
    if not safe:
        raise SystemExit("DEX_QUALITY_BUILD45_RUNTIME=FAIL")
    print("DEX_QUALITY_BUILD45_RUNTIME=PASS")


if __name__ == "__main__":
    main()
