from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_launch_recovery_priority import (  # noqa: E402
    BUILD59_PRIORITY_POLICY,
    DexLaunchRecoveryPriorityRunner,
)
from b3_trader.dex_shadow_remediation_runner import (  # noqa: E402
    DEFAULT_MAX_LAUNCH_RECOVERY_CASES,
    MAX_LAUNCH_RECOVERY_CASES,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--launch-cases", type=int, default=DEFAULT_MAX_LAUNCH_RECOVERY_CASES)
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("DEX_LAUNCH_RECOVERY_PRIORITY_BUILD59_IMPORT=PASS")
        return

    runner = DexLaunchRecoveryPriorityRunner()
    try:
        plan = runner.plan()
        payload = {
            "ok": True,
            "mode": "run" if args.run else "plan",
            "build59_priority_policy": BUILD59_PRIORITY_POLICY,
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

    print("=== DEX LAUNCH RECOVERY PRIORITY BUILD 59 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    launch = plan.get("launch_recovery") if isinstance(plan.get("launch_recovery"), dict) else {}
    priority = launch.get("build59_priority") if isinstance(launch.get("build59_priority"), dict) else {}
    preview = launch.get("preview") if isinstance(launch.get("preview"), list) else []
    source_keys = {
        (
            str(row.get("network_id") or ""),
            str(row.get("token_address") or ""),
            str(row.get("pool_address") or ""),
            float(row.get("pool_created_at") or 0.0),
        )
        for row in preview
        if isinstance(row, dict)
    }
    safe = bool(
        payload["safety"]["paper_only"]
        and payload["safety"]["shadow_only"]
        and not payload["safety"]["can_place_orders"]
        and not payload["safety"]["score_wired"]
        and payload["safety"]["official_sources_only"]
        and int(launch.get("hard_max_cases") or 0) == MAX_LAUNCH_RECOVERY_CASES
        and priority.get("policy") == BUILD59_PRIORITY_POLICY
        and priority.get("distinct_source_representatives_only") is True
        and priority.get("previously_attempted_sources_deprioritized") is True
        and len(source_keys) == len(preview)
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
            and 0 <= int(result.get("distinct_launch_source_fetches") or 0) <= MAX_LAUNCH_RECOVERY_CASES
        )
    if not safe:
        raise SystemExit("DEX_LAUNCH_RECOVERY_PRIORITY_BUILD59_RUNTIME=FAIL")
    print("DEX_LAUNCH_RECOVERY_PRIORITY_BUILD59_RUNTIME=PASS")


if __name__ == "__main__":
    main()
