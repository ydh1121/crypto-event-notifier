from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    module = _text("b3_trader/listing_history_accelerator.py")
    cycle = _text("b3_trader/listing_history_research_cycle.py")
    control = _text("b3_trader/research_control.py")
    supervisor = _text("b3_trader/research_supervisor.py")
    verifier = _text("scripts/verify-listing-accelerator-build48.py")

    checks = {
        "build48_additive_accelerator": "class ListingHistoryAccelerator" in module,
        "build48_reuses_existing_cycle": "ListingHistoryResearchCycle" in module and "self.cycle.run_once()" in module,
        "build48_default_two_cycles": "DEFAULT_CYCLES_PER_RUN = 2" in module,
        "build48_max_four_cycles": "MAX_CYCLES_PER_RUN = 4" in module,
        "build48_inter_cycle_pacing": "INTER_CYCLE_SECONDS = 15.0" in module and "self.sleeper(INTER_CYCLE_SECONDS)" in module,
        "build48_supervisor_overlap_guard": "listing-history-research" in module and "supervisor_became_busy" in module,
        "build48_source_error_guard": "source_error_guard" in module and "cycle_source_errors >= cycle_processed" in module,
        "build48_existing_three_case_limit_unchanged": "MAX_CASES_PER_RUN = 3" in cycle,
        "build48_existing_900s_schedule_unchanged": '"listing-history-research"' in control and '"default_interval_seconds":900' in control,
        "build48_no_supervisor_wiring": "listing_history_accelerator" not in supervisor.lower(),
        "build48_direct_verifier_bootstrap": "sys.path.insert" in verifier and "--import-check" in verifier,
        "build48_no_dex_score_order_wiring": "DexLaunch" not in module and ".place_order(" not in module and '"score_wired": False' in module,
    }
    print("=== LISTING ACCELERATOR BUILD 48 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("LISTING_ACCELERATOR_BUILD48=FAIL")
    print("LISTING_ACCELERATOR_BUILD48=PASS")


if __name__ == "__main__":
    main()
