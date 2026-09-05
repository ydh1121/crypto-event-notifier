from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "b3_trader/dex_launch_sources.py"
QUALITY = ROOT / "b3_trader/dex_launch_quality.py"
DIVERSITY = ROOT / "b3_trader/dex_diversity_backfill.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    source = _text(SOURCE)
    quality = _text(QUALITY)
    diversity = _text(DIVERSITY)
    checks = {
        "build52_uses_json_api_network_pagination": (
            "def _network_page_has_next" in source
            and '"next" not in links' in source
            and "self._network_page_has_next(payload) is False" in source
        ),
        "build52_keeps_bounded_fallback": "MAX_NETWORK_PAGES = 10" in source,
        "build52_keeps_gt_pacing": (
            "DEFAULT_GT_MIN_INTERVAL_SECONDS = 6.2" in source
            and "GT_RETRY_DELAY_FLOOR_SECONDS = 12.0" in source
        ),
        "build52_does_not_swallow_http_errors_globally": "except requests.HTTPError" not in source,
        "build52_build45_thresholds_unchanged": (
            "MIN_USABLE_CASES = 20" in quality
            and "MIN_EXACT_P5M_COVERAGE = 0.60" in quality
        ),
        "build52_build51_diversity_policy_preserved": (
            '"fresh_unresearched_before_retry": True' in diversity
            and '"one_event_per_new_asset_per_batch": True' in diversity
        ),
        "build52_no_score_decision_order_wiring": (
            "place_order(" not in source
            and ".place_order(" not in source
            and "score_wired" not in source
        ),
    }
    print("=== DEX NETWORK PAGINATION BUILD 52 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_NETWORK_PAGINATION_BUILD52=FAIL")
    print("DEX_NETWORK_PAGINATION_BUILD52=PASS")


if __name__ == "__main__":
    main()
