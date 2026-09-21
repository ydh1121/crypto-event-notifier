from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_sample_audit import audit_dex_sample  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("DEX_SAMPLE_AUDIT_BUILD50_IMPORT=PASS")
        return

    payload = audit_dex_sample()
    print("=== DEX SAMPLE AUDIT BUILD 50 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    safe = bool(
        payload.get("ok")
        and payload.get("paper_only")
        and payload.get("shadow_only")
        and not payload.get("can_place_orders")
        and not payload.get("score_wired")
        and payload.get("advisory_only")
        and not payload.get("changes_build45_thresholds")
        and payload.get("review", {}).get("do_not_enable_shadow_score_yet")
    )
    if not safe:
        raise SystemExit("DEX_SAMPLE_AUDIT_BUILD50_RUNTIME=FAIL")
    print("DEX_SAMPLE_AUDIT_BUILD50_RUNTIME=PASS")


if __name__ == "__main__":
    main()
