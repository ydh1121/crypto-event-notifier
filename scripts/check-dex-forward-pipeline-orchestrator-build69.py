from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "b3_trader" / "forward_pipeline_orchestrator.py"
VERIFIER = ROOT / "scripts" / "verify-dex-forward-pipeline-orchestrator-build69.py"


def main() -> None:
    text = MODULE.read_text(encoding="utf-8")
    verifier_text = VERIFIER.read_text(encoding="utf-8")
    tree = ast.parse(text)
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    checks = {
        "build69_composes_build67_build68_build66": (
            "ForwardSampleIntake" in text
            and "ForwardSampleEnrichment" in text
            and "audit_dex_shadow_score_v2_forward" in text
        ),
        "build69_single_intake_run": '"intake_runs_per_invocation": 1' in text,
        "build69_single_enrichment_run": '"enrichment_runs_per_invocation": 1' in text,
        "build69_single_score_audit": '"score_audits_per_invocation": 1' in text,
        "build69_max_one_enrichment_case": '"max_enrichment_cases_per_invocation": 1' in text,
        "build69_partial_intake_fail_closed": "intake_partial_stop" in text,
        "build69_pre_cutoff_blocked": '"pre_cutoff_cases_selectable": False' in text,
        "build69_no_generic_supervisor_enable": (
            '"generic_listing_history_supervisor_enabled": False' in text
            and '"generic_dex_launch_supervisor_enabled": False' in text
        ),
        "build69_no_strategy_position_order_cloudflare_mutation": (
            '"strategy_signal_mutation": False' in text
            and '"position_sizing_mutation": False' in text
            and '"order_path_mutation": False' in text
            and '"cloudflare_publishing": False' in text
        ),
        "build69_no_fitting_or_trade_threshold": (
            '"training_or_fitting": False' in text and '"trade_threshold": None' in text
        ),
        "build69_no_order_calls": not ({"place_order", "create_order", "submit_order"} & calls),
        "build69_no_check_same_thread_override": "check_same_thread" not in text,
        "build69_plan_and_run_cli": "--run" in verifier_text and "--pages" in verifier_text,
        "build69_direct_import_bootstrap": "sys.path.insert" in verifier_text,
    }
    print("=== DEX FORWARD PIPELINE ORCHESTRATOR BUILD 69 CONTRACT ===")
    import json
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit("DEX_FORWARD_PIPELINE_ORCHESTRATOR_BUILD69=FAIL")
    print("DEX_FORWARD_PIPELINE_ORCHESTRATOR_BUILD69=PASS")


if __name__ == "__main__":
    main()
