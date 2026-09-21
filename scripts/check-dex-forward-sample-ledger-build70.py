from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "b3_trader" / "forward_sample_ledger.py").read_text(encoding="utf-8")
VERIFY = (ROOT / "scripts" / "verify-dex-forward-sample-ledger-build70.py").read_text(encoding="utf-8")


def main() -> None:
    checks = {
        "build70_uses_build66_forward_scores": "audit_dex_shadow_score_v2_forward" in SOURCE,
        "build70_uses_frozen_build65_protocol": "FORWARD_VALIDATION_PROTOCOL" in SOURCE,
        "build70_event_and_asset_dedup_counts": "unique_asset_count" in SOURCE and "asset_dedup" in SOURCE,
        "build70_core_label_coverage": (
            "CORE_WINDOWS" in SOURCE
            and "event_labels" in SOURCE
            and "asset_labels" in SOURCE
            and '"label_coverage"' in SOURCE
        ),
        "build70_no_early_statistics": '"validation_statistics_calculated": False' in SOURCE,
        "build70_historical_contamination_fail_closed": "historical_contamination_blocked" in SOURCE,
        "build70_read_only": '"read_only": True' in SOURCE and '"database_mutation": False' in SOURCE,
        "build70_no_network": '"network_fetches": False' in SOURCE,
        "build70_no_orders": "place_order(" not in SOURCE and "create_order(" not in SOURCE,
        "build70_no_paper_ab_or_live": '"paper_ab_wired": False' in SOURCE and '"live_promotion_allowed": False' in SOURCE,
        "build70_no_fitting_or_threshold": '"training_or_fitting": False' in SOURCE and '"trade_threshold": None' in SOURCE,
        "build70_runtime_verifier": "DEX_FORWARD_SAMPLE_LEDGER_BUILD70_RUNTIME=PASS" in VERIFY,
        "build70_direct_import_bootstrap": "sys.path.insert" in VERIFY,
        "build70_no_check_same_thread_override": "check_same_thread" not in SOURCE,
    }
    print("=== DEX FORWARD SAMPLE LEDGER BUILD 70 CONTRACT ===")
    import json
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_FORWARD_SAMPLE_LEDGER_BUILD70=FAIL")
    print("DEX_FORWARD_SAMPLE_LEDGER_BUILD70=PASS")


if __name__ == "__main__":
    main()
