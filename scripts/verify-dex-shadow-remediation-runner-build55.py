from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_shadow_remediation_runner import (  # noqa: E402
    DEFAULT_MAX_LAUNCH_RECOVERY_CASES,
    MAX_LAUNCH_RECOVERY_CASES,
    DexShadowRemediationRunner,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--launch-cases", type=int, default=DEFAULT_MAX_LAUNCH_RECOVERY_CASES)
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("DEX_SHADOW_REMEDIATION_RUNNER_BUILD55_IMPORT=PASS")
        return

    runner = DexShadowRemediationRunner()
    try:
        plan = runner.plan()
        payload = {
            "ok": True,
            "mode": "run" if args.run else "plan",
            "plan": plan,
            "safety": {
                "paper_only": bool(plan.get("paper_only")),
                "shadow_only": bool(plan.get("shadow_only")),
                "can_place_orders": bool(plan.get("can_place_orders")),
                "score_wired": bool(plan.get("score_wired")),
                "official_sources_only": bool(plan.get("historical_expansion", {}).get("official_sources_only")),
            },
        }
        if args.run:
            payload["run"] = runner.run_once(max_launch_cases=args.launch_cases)
    finally:
        runner.close()

    print("=== DEX SHADOW REMEDIATION RUNNER BUILD 55 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    launch = plan.get("launch_recovery") if isinstance(plan.get("launch_recovery"), dict) else {}
    history = plan.get("historical_expansion") if isinstance(plan.get("historical_expansion"), dict) else {}
    safe = bool(
        payload["safety"]["paper_only"]
        and payload["safety"]["shadow_only"]
        and not payload["safety"]["can_place_orders"]
        and not payload["safety"]["score_wired"]
        and payload["safety"]["official_sources_only"]
        and int(launch.get("hard_max_cases") or 0) == MAX_LAUNCH_RECOVERY_CASES
        and int(history.get("pages_per_exchange") or 0) == 1
    )
    if args.run:
        result = payload.get("run") if isinstance(payload.get("run"), dict) else {}
        safe = bool(
            safe
            and result.get("paper_only")
            and result.get("shadow_only")
            and not result.get("can_place_orders")
            and not result.get("score_wired")
            and 0 <= int(result.get("processed_launch") or 0) <= MAX_LAUNCH_RECOVERY_CASES
            and int(result.get("historical_pages_per_exchange") or 0) in {0, 1}
        )
    if not safe:
        raise SystemExit("DEX_SHADOW_REMEDIATION_RUNNER_BUILD55_RUNTIME=FAIL")
    print("DEX_SHADOW_REMEDIATION_RUNNER_BUILD55_RUNTIME=PASS")


if __name__ == "__main__":
    main()
