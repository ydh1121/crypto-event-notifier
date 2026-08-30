from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "b3_trader" / "dex_alternate_launch_probe.py"
VERIFY = ROOT / "scripts" / "verify-dex-alternate-launch-probe-build61.py"


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    verify = VERIFY.read_text(encoding="utf-8")
    checks = {
        "build61_paper_shadow_only": '"paper_only": True' in source and '"shadow_only": True' in source,
        "build61_no_orders": '"can_place_orders": False' in source and "place_order" not in source,
        "build61_no_score_wiring": '"score_wired": False' in source,
        "build61_non_primary_only": '"accepted_non_primary_only": True' in source and 'int(row["selected_primary"] or 0) != 0' in source,
        "build61_no_primary_mutation": '"selected_primary_mutation": False' in source and "UPDATE dex_launch_pools" not in source,
        "build61_no_domestic_fetch": '"domestic_window_fetches": False' in source and "_domestic_candles(" not in source,
        "build61_uses_build60_candidates": "audit_dex_launch_coverage" in source and "alternate_pool_opportunities" in source,
        "build61_shared_source_priority": "shared_case_gain_then_pool_freshness" in source and "potential_case_gain" in source,
        "build61_bounded_sources": "MAX_SOURCE_PROBES = 2" in source and "DEFAULT_MAX_SOURCE_PROBES = 1" in source,
        "build61_cooldown": "RETRY_AFTER_SECONDS = 6 * 3600" in source and "source_attempted_at" in source,
        "build61_launch_only_fetch": "_launch_candles(" in source and "launch_window_features(" in source,
        "build61_no_check_same_thread_override": "check_same_thread" not in source,
        "build61_runtime_verifier": "DEX_ALTERNATE_LAUNCH_PROBE_BUILD61_RUNTIME=PASS" in verify,
        "build61_direct_import_bootstrap": "DEX_ALTERNATE_LAUNCH_PROBE_BUILD61_IMPORT=PASS" in verify,
    }
    print("=== DEX ALTERNATE LAUNCH PROBE BUILD 61 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_ALTERNATE_LAUNCH_PROBE_BUILD61=FAIL")
    print("DEX_ALTERNATE_LAUNCH_PROBE_BUILD61=PASS")


if __name__ == "__main__":
    main()
