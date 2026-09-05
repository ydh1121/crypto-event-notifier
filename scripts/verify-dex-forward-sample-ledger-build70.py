from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.forward_sample_ledger import audit_forward_sample_ledger


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()
    if args.import_check:
        print("DEX_FORWARD_SAMPLE_LEDGER_BUILD70_IMPORT=PASS")
        return

    payload = audit_forward_sample_ledger()
    print("=== DEX FORWARD SAMPLE LEDGER BUILD 70 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload.get("ok"):
        raise SystemExit("DEX_FORWARD_SAMPLE_LEDGER_BUILD70_RUNTIME=FAIL")
    if payload.get("can_place_orders") or payload.get("score_wired") or payload.get("paper_ab_wired"):
        raise SystemExit("DEX_FORWARD_SAMPLE_LEDGER_BUILD70_RUNTIME=FAIL")
    if payload.get("validation_statistics_calculated"):
        raise SystemExit("DEX_FORWARD_SAMPLE_LEDGER_BUILD70_RUNTIME=FAIL")
    print("DEX_FORWARD_SAMPLE_LEDGER_BUILD70_RUNTIME=PASS")


if __name__ == "__main__":
    main()
