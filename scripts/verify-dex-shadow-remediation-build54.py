from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_shadow_remediation_plan import plan_dex_shadow_remediation  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("DEX_SHADOW_REMEDIATION_BUILD54_IMPORT=PASS")
        return

    payload = plan_dex_shadow_remediation()
    print("=== DEX SHADOW REMEDIATION BUILD 54 RUNTIME ===")
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
        and not payload.get("changes_build53_thresholds")
        and payload.get("review", {}).get("wire_shadow_score_now") is False
    )
    if not safe:
        raise SystemExit("DEX_SHADOW_REMEDIATION_BUILD54_RUNTIME=FAIL")
    print("DEX_SHADOW_REMEDIATION_BUILD54_RUNTIME=PASS")


if __name__ == "__main__":
    main()
