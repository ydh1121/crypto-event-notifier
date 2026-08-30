from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_launch_coverage_audit import audit_dex_launch_coverage  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()
    if args.import_check:
        print("DEX_LAUNCH_COVERAGE_AUDIT_BUILD60_IMPORT=PASS")
        return

    payload = audit_dex_launch_coverage()
    print("=== DEX LAUNCH COVERAGE AUDIT BUILD 60 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    criteria = payload.get("launch_feature_criteria") if isinstance(payload.get("launch_feature_criteria"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
    usable = int(summary.get("usable_event_cases") or 0)
    launch = int(summary.get("launch_feature_cases") or 0)
    required = int(summary.get("required_launch_feature_cases") or 0)
    additional = int(summary.get("additional_launch_cases_needed") or 0)
    safe = bool(
        payload.get("ok")
        and payload.get("paper_only")
        and payload.get("shadow_only")
        and payload.get("read_only")
        and payload.get("network_fetches") is False
        and payload.get("can_place_orders") is False
        and payload.get("score_wired") is False
        and payload.get("changes_build53_thresholds") is False
        and payload.get("changes_feature_criteria") is False
        and criteria.get("counted_when") == "feature_json.pool_launch_window.status == collected"
        and criteria.get("partial_hourly_rows_alone_are_not_sufficient") is True
        and 0 <= launch <= usable
        and 0 <= required <= usable
        and additional == max(0, required - launch)
        and review.get("wire_shadow_score_now") is False
    )
    if not safe:
        raise SystemExit("DEX_LAUNCH_COVERAGE_AUDIT_BUILD60_RUNTIME=FAIL")
    print("DEX_LAUNCH_COVERAGE_AUDIT_BUILD60_RUNTIME=PASS")


if __name__ == "__main__":
    main()
