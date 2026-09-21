from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def main() -> None:
    scheduler = _text("b3_trader/forward_pipeline_scheduler.py")
    lock = _text("b3_trader/research_work_lock.py")
    supervisor = _text("b3_trader/research_supervisor.py")
    notice_collector = _text("b3_trader/market_notice_collector.py")
    launcher = _text("scripts/run-local.ps1")
    cleanup = _text("scripts/cleanup-stale-runtime-supervisors.ps1")
    verifier = _text("scripts/verify-dex-forward-pipeline-scheduler-build69.py")
    tree = ast.parse(scheduler)
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    checks = {
        "build69_scheduler_dedicated_process_owner": (
            "class ForwardPipelineScheduler" in scheduler
            and "ForwardPipelineOrchestrator" in scheduler
            and 'if __name__ == "__main__"' in scheduler
        ),
        "build69_scheduler_fixed_bounded_cadence": (
            "DEFAULT_INTERVAL_SECONDS = 900.0" in scheduler
            and "MIN_INTERVAL_SECONDS = 300.0" in scheduler
            and "DEFAULT_PAGES_PER_EXCHANGE" in scheduler
            and '"max_enrichment_cases_per_invocation": 1' in scheduler
        ),
        "build69_scheduler_single_invocation_per_interval": (
            "self.run_once()" in scheduler
            and "self._wait_with_heartbeat()" in scheduler
            and "while not self.stop_event.is_set()" in scheduler
        ),
        "build69_scheduler_server_off_means_no_work": (
            "scheduler.run()" in scheduler
            and "b3_trader.forward_pipeline_scheduler" in launcher
            and "ForwardPipelineScheduler(" not in supervisor
        ),
        "build69_scheduler_generic_supervisors_disabled": (
            'FORWARD_PIPELINE_DEDICATED_MODE_ENV = "DEX_FORWARD_PIPELINE_DEDICATED_MODE"'
            in supervisor
            and '"listing-history-research"' in supervisor
            and '"dex-launch-research"' in supervisor
            and '$env:DEX_FORWARD_PIPELINE_DEDICATED_MODE = "true"' in launcher
            and "disabled_by_forward_pipeline_dedicated_mode" in supervisor
        ),
        "build69_scheduler_shared_process_lock": (
            "class ResearchWorkLock" in lock
            and "msvcrt.locking" in lock
            and "fcntl.flock" in lock
            and "with ResearchWorkLock() as work_lock" in supervisor
            and "with ResearchWorkLock() as work_lock" in notice_collector
            and "work_lock.acquire()" in scheduler
        ),
        "build69_scheduler_busy_fail_closed": (
            "deferred_generic_research_busy" in scheduler
            and "deferred_research_work_lock_busy" in scheduler
            and '"network_fetches": False' in scheduler
            and '"database_mutation": False' in scheduler
        ),
        "build69_scheduler_safety_reaudit": (
            "def _safety_violations" in scheduler
            and "safety_contract_blocked" in scheduler
            and "historical_rows_scored_as_v2" in scheduler
            and "processed_more_than_one_forward_case" in scheduler
        ),
        "build69_scheduler_no_build47_or_statistics": (
            "historical_listing_backfill" not in scheduler
            and "HistoricalListingBackfill" not in scheduler
            and "ForwardSampleLedger" not in scheduler
            and "ForwardValidation" not in scheduler
        ),
        "build69_scheduler_no_order_calls": not (
            {"place_order", "create_order", "submit_order"} & calls
        ),
        "build69_scheduler_launcher_lifecycle": (
            "function Start-ForwardPipelineScheduler" in launcher
            and "$forwardScheduler = Start-ForwardPipelineScheduler" in launcher
            and "Stop-Process -Id $forwardScheduler.Id" in launcher
            and "b3_trader.forward_pipeline_scheduler" in cleanup
        ),
        "build69_scheduler_status_heartbeat": (
            "HEARTBEAT_SECONDS = 5.0" in scheduler
            and "dex-forward-pipeline-scheduler-build69.json" in scheduler
            and "process_lock_acquired" in scheduler
        ),
        "build69_scheduler_runtime_verifier": (
            "--require-running" in verifier
            and "--import-check" in verifier
            and "server_offline_runtime_pending" in verifier
            and "sys.path.insert" in verifier
        ),
        "build69_scheduler_paper_ab_live_unwired": (
            '"paper_ab_wired": False' in scheduler
            and '"live_promotion_allowed": False' in scheduler
            and '"can_place_orders": False' in scheduler
        ),
        "build69_scheduler_no_check_same_thread_override": (
            "check_same_thread" not in scheduler and "check_same_thread" not in lock
        ),
    }
    print("=== DEX FORWARD PIPELINE SCHEDULER BUILD 69 CONTRACT ===")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        failed = [name for name, ok in checks.items() if not ok]
        raise SystemExit(
            "DEX_FORWARD_PIPELINE_SCHEDULER_BUILD69=FAIL: " + ", ".join(failed)
        )
    print("DEX_FORWARD_PIPELINE_SCHEDULER_BUILD69=PASS")


if __name__ == "__main__":
    main()
