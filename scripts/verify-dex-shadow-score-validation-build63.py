from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.auto_demo_v2 import DB_PATH  # noqa: E402
from b3_trader.dex_shadow_score_validation import (  # noqa: E402
    CORE_WINDOWS,
    HIGH_CONFIDENCE,
    MIN_ASSET_LABELS_PER_CORE,
    MIN_EVENT_LABELS_PER_CORE,
    MIN_LATE_POSITIVE_CORE_WINDOWS,
    MIN_POSITIVE_CORE_WINDOWS,
    MIN_RHO,
    STRONG_NEGATIVE_RHO,
    VALIDATION_NAME,
    VALIDATION_VERSION,
    audit_dex_shadow_score_validation,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("DEX_SHADOW_SCORE_VALIDATION_BUILD63_IMPORT=PASS")
        return

    payload = audit_dex_shadow_score_validation(Path(args.db))
    print("=== DEX SHADOW SCORE VALIDATION BUILD 63 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    protocol = payload.get("validation_protocol") if isinstance(payload.get("validation_protocol"), dict) else {}
    thresholds = protocol.get("thresholds") if isinstance(protocol.get("thresholds"), dict) else {}
    gate = payload.get("validation_gate") if isinstance(payload.get("validation_gate"), dict) else {}
    review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
    event_level = payload.get("event_level") if isinstance(payload.get("event_level"), dict) else {}
    asset_level = payload.get("asset_level_dedup") if isinstance(payload.get("asset_level_dedup"), dict) else {}

    safe = bool(
        payload.get("ok")
        and payload.get("status") == "validated_read_only"
        and int(payload.get("validation_version") or 0) == VALIDATION_VERSION
        and payload.get("validation_name") == VALIDATION_NAME
        and payload.get("paper_only")
        and payload.get("shadow_only")
        and not payload.get("can_place_orders")
        and not payload.get("paper_ab_wired")
        and payload.get("read_only")
        and not payload.get("network_fetches")
        and not payload.get("database_mutation")
        and not payload.get("cloudflare_publishing")
        and not payload.get("strategy_signal_mutation")
        and not payload.get("position_sizing_mutation")
        and not payload.get("score_formula_changed")
        and not payload.get("score_weights_changed")
        and not payload.get("training_or_fitting")
        and payload.get("trade_threshold") is None
        and payload.get("post_listing_outcomes_used_for_evaluation_only")
        and payload.get("forward_validation_required")
        and payload.get("promotion_to_live_blocked")
        and payload.get("score_audit_ready")
        and int(payload.get("event_case_count") or 0) == int(event_level.get("row_count") or -1)
        and int(payload.get("asset_count_dedup") or 0) == int(asset_level.get("row_count") or -1)
        and int(payload.get("event_case_count") or 0) >= int(payload.get("asset_count_dedup") or 0)
        and thresholds.get("core_windows") == list(CORE_WINDOWS)
        and thresholds.get("min_event_labels_per_core") == MIN_EVENT_LABELS_PER_CORE
        and thresholds.get("min_asset_labels_per_core") == MIN_ASSET_LABELS_PER_CORE
        and thresholds.get("min_positive_core_windows") == MIN_POSITIVE_CORE_WINDOWS
        and thresholds.get("min_late_positive_core_windows") == MIN_LATE_POSITIVE_CORE_WINDOWS
        and thresholds.get("min_spearman_rho") == MIN_RHO
        and thresholds.get("strong_negative_spearman_rho") == STRONG_NEGATIVE_RHO
        and isinstance(gate.get("paper_ab_candidate_advisory"), bool)
        and gate.get("forward_validation_required") is True
        and gate.get("live_promotion_allowed") is False
        and review.get("paper_ab_wired") is False
        and review.get("orders_changed") is False
        and review.get("existing_strategy_signal_changed") is False
        and review.get("position_sizing_changed") is False
        and HIGH_CONFIDENCE == 0.80
    )
    if not safe:
        raise SystemExit("DEX_SHADOW_SCORE_VALIDATION_BUILD63_RUNTIME=FAIL")
    print("DEX_SHADOW_SCORE_VALIDATION_BUILD63_RUNTIME=PASS")


if __name__ == "__main__":
    main()
