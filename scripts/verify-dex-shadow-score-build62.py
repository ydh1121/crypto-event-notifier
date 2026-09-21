from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.auto_demo_v2 import DB_PATH  # noqa: E402
from b3_trader.dex_shadow_score import (  # noqa: E402
    COMPONENT_WEIGHTS,
    SCORE_NAME,
    SCORE_VERSION,
    audit_dex_shadow_scores,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("DEX_SHADOW_SCORE_BUILD62_IMPORT=PASS")
        return

    payload = audit_dex_shadow_scores(Path(args.db))
    printable = dict(payload)
    if not args.full:
        printable.pop("case_scores", None)

    print("=== DEX SHADOW SCORE BUILD 62 RUNTIME ===")
    print(json.dumps(printable, ensure_ascii=False, indent=2))

    readiness = payload.get("readiness_gate") if isinstance(payload.get("readiness_gate"), dict) else {}
    distribution = payload.get("distribution") if isinstance(payload.get("distribution"), dict) else {}
    review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
    safe = bool(
        payload.get("ok")
        and payload.get("status") == "scored_read_only"
        and int(payload.get("score_version") or 0) == SCORE_VERSION
        and payload.get("score_name") == SCORE_NAME
        and payload.get("component_weights") == COMPONENT_WEIGHTS
        and payload.get("paper_only")
        and payload.get("shadow_only")
        and not payload.get("can_place_orders")
        and not payload.get("score_wired")
        and payload.get("read_only")
        and not payload.get("network_fetches")
        and not payload.get("strategy_signal_mutation")
        and not payload.get("order_path_mutation")
        and not payload.get("position_sizing_mutation")
        and not payload.get("cloudflare_publishing")
        and not payload.get("selected_primary_mutation")
        and not payload.get("training_or_fitting")
        and payload.get("trade_threshold") is None
        and not payload.get("uses_post_listing_features_in_score")
        and not payload.get("uses_pool_quality_levels_in_score")
        and readiness.get("shadow_readiness_advisory") is True
        and not readiness.get("blocking_reasons")
        and payload.get("scoring_enabled_for_audit") is True
        and payload.get("all_usable_cases_scored") is True
        and int(payload.get("case_score_count") or 0) == int(payload.get("expected_usable_case_count") or -1)
        and int(distribution.get("count") or 0) == int(payload.get("case_score_count") or 0)
        and review.get("paper_ab_wired") is False
        and review.get("existing_strategy_signal_changed") is False
        and review.get("position_sizing_changed") is False
        and review.get("orders_changed") is False
    )
    if not safe:
        raise SystemExit("DEX_SHADOW_SCORE_BUILD62_RUNTIME=FAIL")
    print("DEX_SHADOW_SCORE_BUILD62_RUNTIME=PASS")


if __name__ == "__main__":
    main()
