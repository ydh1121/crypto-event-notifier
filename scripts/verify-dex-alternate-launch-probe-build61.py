from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_trader.dex_alternate_launch_probe import (  # noqa: E402
    DEFAULT_MAX_SOURCE_PROBES,
    MAX_SOURCE_PROBES,
    PRIORITY_POLICY,
    DexAlternateLaunchProbeRunner,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--max-sources", type=int, default=DEFAULT_MAX_SOURCE_PROBES)
    parser.add_argument("--import-check", action="store_true")
    args = parser.parse_args()

    if args.import_check:
        print("DEX_ALTERNATE_LAUNCH_PROBE_BUILD61_IMPORT=PASS")
        return

    runner = DexAlternateLaunchProbeRunner()
    try:
        plan = runner.plan()
        payload = {
            "ok": True,
            "mode": "run" if args.run else "plan",
            "priority_policy": PRIORITY_POLICY,
            "plan": plan,
            "safety": {
                "paper_only": bool(plan.get("paper_only")),
                "shadow_only": bool(plan.get("shadow_only")),
                "can_place_orders": bool(plan.get("can_place_orders")),
                "score_wired": bool(plan.get("score_wired")),
                "accepted_non_primary_only": bool(plan.get("alternate_probe", {}).get("accepted_non_primary_only")),
                "selected_primary_mutation": bool(plan.get("alternate_probe", {}).get("selected_primary_mutation")),
                "domestic_window_fetches": bool(plan.get("alternate_probe", {}).get("domestic_window_fetches")),
            },
        }
        if args.run:
            payload["run"] = runner.run_once(max_sources=args.max_sources)
    finally:
        runner.close()

    print("=== DEX ALTERNATE LAUNCH PROBE BUILD 61 RUNTIME ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    probe = plan.get("alternate_probe") if isinstance(plan.get("alternate_probe"), dict) else {}
    preview = probe.get("preview") if isinstance(probe.get("preview"), list) else []
    safe = bool(
        payload["safety"]["paper_only"]
        and payload["safety"]["shadow_only"]
        and not payload["safety"]["can_place_orders"]
        and not payload["safety"]["score_wired"]
        and payload["safety"]["accepted_non_primary_only"]
        and not payload["safety"]["selected_primary_mutation"]
        and not payload["safety"]["domestic_window_fetches"]
        and probe.get("priority_policy") == PRIORITY_POLICY
        and int(probe.get("hard_max_source_probes") or 0) == MAX_SOURCE_PROBES
        and all(int(row.get("potential_case_gain") or 0) >= 1 for row in preview if isinstance(row, dict))
    )
    if args.run:
        result = payload.get("run") if isinstance(payload.get("run"), dict) else {}
        safe = bool(
            safe
            and result.get("paper_only")
            and result.get("shadow_only")
            and not result.get("can_place_orders")
            and not result.get("score_wired")
            and not result.get("selected_primary_mutation")
            and not result.get("domestic_window_fetches")
            and 0 <= int(result.get("processed_sources") or 0) <= MAX_SOURCE_PROBES
            and 0 <= int(result.get("distinct_source_fetches") or 0) <= MAX_SOURCE_PROBES
        )
    if not safe:
        raise SystemExit("DEX_ALTERNATE_LAUNCH_PROBE_BUILD61_RUNTIME=FAIL")
    print("DEX_ALTERNATE_LAUNCH_PROBE_BUILD61_RUNTIME=PASS")


if __name__ == "__main__":
    main()
