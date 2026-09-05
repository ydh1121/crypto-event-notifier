from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_shadow_readiness_audit import audit_dex_shadow_readiness  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("DEX_SHADOW_READINESS_BUILD53_IMPORT=PASS")
        return

    payload = audit_dex_shadow_readiness()
    print("=== DEX SHADOW READINESS BUILD 53 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    safe = bool(
        payload.get("ok")
        and payload.get("paper_only")
        and payload.get("shadow_only")
        and not payload.get("can_place_orders")
        and not payload.get("score_wired")
        and payload.get("advisory_only")
        and not payload.get("changes_build45_thresholds")
        and not payload.get("changes_build51_policy")
        and payload.get("review", {}).get("wire_shadow_score_now") is False
    )
    if not safe:
        raise SystemExit("DEX_SHADOW_READINESS_BUILD53_RUNTIME=FAIL")
    print("DEX_SHADOW_READINESS_BUILD53_RUNTIME=PASS")


if __name__ == "__main__":
    main()
