from __future__ import annotations

import json
import os
import signal
import threading
import time
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from .auto_demo_v2 import DB_PATH
from .forward_pipeline_orchestrator import ForwardPipelineOrchestrator
from .forward_sample_intake import DEFAULT_PAGES_PER_EXCHANGE
from .research_control import STATUS_PATH as RESEARCH_STATUS_PATH
from .research_control import atomic_json
from .research_work_lock import RESEARCH_WORK_LOCK_PATH, ResearchWorkLock


BUILD69_SCHEDULER_VERSION = 1
BUILD69_SCHEDULER_NAME = "dex_forward_pipeline_scheduler_v1"
STATUS_PATH = Path(
    "b3_trader/data/research-platform/dex-forward-pipeline-scheduler-build69.json"
)
PROCESS_LOCK_PATH = Path(
    "b3_trader/data/research-platform/dex-forward-pipeline-scheduler-build69-process.lock"
)
DEFAULT_INTERVAL_SECONDS = 900.0
MIN_INTERVAL_SECONDS = 300.0
HEARTBEAT_SECONDS = 5.0
RESEARCH_STATUS_FRESH_SECONDS = 30.0
GENERIC_RESEARCH_COMPONENTS = (
    "listing-history-research",
    "dex-launch-research",
)

OrchestratorFactory = Callable[..., ForwardPipelineOrchestrator]
LockFactory = Callable[[Path | str], ResearchWorkLock]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _generic_research_busy(
    path: Path,
    *,
    now: float | None = None,
) -> list[str]:
    payload = _read_json(path)
    current = float(now or time.time())
    updated_at = float(payload.get("updated_at") or 0.0)
    if (
        not payload.get("running")
        or updated_at <= 0
        or current - updated_at > RESEARCH_STATUS_FRESH_SECONDS
    ):
        return []
    components = (
        payload.get("components")
        if isinstance(payload.get("components"), dict)
        else {}
    )
    busy: list[str] = []
    for name in GENERIC_RESEARCH_COMPONENTS:
        item = components.get(name) if isinstance(components.get(name), dict) else {}
        if item.get("enabled") and str(item.get("status") or "") in {"starting", "running"}:
            busy.append(name)
    return busy


def _scheduler_base() -> dict[str, Any]:
    return {
        "build69_scheduler_version": BUILD69_SCHEDULER_VERSION,
        "build69_scheduler_name": BUILD69_SCHEDULER_NAME,
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_wired": False,
        "paper_ab_wired": False,
        "live_promotion_allowed": False,
        "forward_only": True,
        "network_fetches": False,
        "database_mutation": False,
        "schedule": {
            "default_interval_seconds": DEFAULT_INTERVAL_SECONDS,
            "minimum_interval_seconds": MIN_INTERVAL_SECONDS,
            "pages_per_exchange": DEFAULT_PAGES_PER_EXCHANGE,
            "max_enrichment_cases_per_invocation": 1,
        },
        "isolation": {
            "build47_historical_cursor_read": False,
            "build47_historical_cursor_mutation": False,
            "generic_listing_history_supervisor_enabled": False,
            "generic_dex_launch_supervisor_enabled": False,
        },
        "safety": {
            "strategy_signal_mutation": False,
            "position_sizing_mutation": False,
            "order_path_mutation": False,
            "cloudflare_publishing": False,
            "training_or_fitting": False,
            "trade_threshold": None,
        },
    }


def _safety_violations(payload: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    required_true = ("paper_only", "shadow_only", "forward_only")
    for key in required_true:
        if payload.get(key) is not True:
            violations.append(f"{key}_not_true")
    required_false = (
        "can_place_orders",
        "score_wired",
        "paper_ab_wired",
        "live_promotion_allowed",
    )
    for key in required_false:
        if payload.get(key) is not False:
            violations.append(f"{key}_not_false")

    boundary = payload.get("forward_boundary") if isinstance(payload.get("forward_boundary"), dict) else {}
    if boundary.get("pre_cutoff_cases_selectable") is not False:
        violations.append("pre_cutoff_selection_not_blocked")

    bounds = payload.get("bounds") if isinstance(payload.get("bounds"), dict) else {}
    for key in (
        "intake_runs_per_invocation",
        "enrichment_runs_per_invocation",
        "score_audits_per_invocation",
        "max_enrichment_cases_per_invocation",
    ):
        if int(bounds.get(key) or 0) != 1:
            violations.append(f"{key}_not_one")

    isolation = payload.get("isolation") if isinstance(payload.get("isolation"), dict) else {}
    for key in (
        "build47_historical_cursor_read",
        "build47_historical_cursor_mutation",
        "generic_listing_history_supervisor_enabled",
        "generic_dex_launch_supervisor_enabled",
    ):
        if isolation.get(key) is not False:
            violations.append(f"{key}_not_false")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in (
        "strategy_signal_mutation",
        "position_sizing_mutation",
        "order_path_mutation",
        "cloudflare_publishing",
        "training_or_fitting",
    ):
        if safety.get(key) is not False:
            violations.append(f"{key}_not_false")
    if safety.get("trade_threshold") is not None:
        violations.append("trade_threshold_not_none")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if int(summary.get("processed_forward_cases") or 0) > 1:
        violations.append("processed_more_than_one_forward_case")
    steps = payload.get("steps") if isinstance(payload.get("steps"), dict) else {}
    score = (
        steps.get("build66_score_audit")
        if isinstance(steps.get("build66_score_audit"), dict)
        else {}
    )
    if score.get("historical_rows_scored_as_v2"):
        violations.append("historical_rows_scored_as_v2")
    return violations


class ForwardPipelineScheduler:
    """Dedicated, bounded process owner for recurring Build69 forward intake.

    This process never runs Build70/71 statistics and never enables the generic
    historical listing or DEX supervisors. One interval contains at most one
    Build69 invocation, which itself remains bounded to one Build67 intake, one
    Build68 case and one Build66 audit.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        status_path: Path | str = STATUS_PATH,
        research_status_path: Path | str = RESEARCH_STATUS_PATH,
        process_lock_path: Path | str = PROCESS_LOCK_PATH,
        work_lock_path: Path | str = RESEARCH_WORK_LOCK_PATH,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        pages_per_exchange: int = DEFAULT_PAGES_PER_EXCHANGE,
        orchestrator_factory: OrchestratorFactory = ForwardPipelineOrchestrator,
        lock_factory: LockFactory = ResearchWorkLock,
    ) -> None:
        self.path = Path(path)
        self.status_path = Path(status_path)
        self.research_status_path = Path(research_status_path)
        self.process_lock_path = Path(process_lock_path)
        self.work_lock_path = Path(work_lock_path)
        self.interval_seconds = max(MIN_INTERVAL_SECONDS, float(interval_seconds))
        self.pages_per_exchange = max(1, min(DEFAULT_PAGES_PER_EXCHANGE, int(pages_per_exchange)))
        self.orchestrator_factory = orchestrator_factory
        self.lock_factory = lock_factory
        self.stop_event = threading.Event()
        self.started_at = time.time()
        self.attempts = 0
        self.successes = 0
        self.deferred = 0
        self.failures = 0
        self.last_started_at = 0.0
        self.last_finished_at = 0.0
        self.last_success_at = 0.0
        self.last_error_at = 0.0
        self.last_error = ""
        self.last_result: dict[str, Any] = {}
        self.process_lock_acquired = False
        self._status_lock = threading.RLock()
        self._heartbeat_stop = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def _status_payload(self, *, running: bool) -> dict[str, Any]:
        result_status = str(self.last_result.get("status") or "waiting_first_run")
        return {
            **_scheduler_base(),
            "ok": not bool(self.last_error),
            "status": result_status,
            "pid": os.getpid(),
            "running": bool(running) and not self.stop_event.is_set(),
            "started_at": self.started_at,
            "updated_at": time.time(),
            "interval_seconds": self.interval_seconds,
            "pages_per_exchange": self.pages_per_exchange,
            "process_lock_acquired": self.process_lock_acquired,
            "attempts": self.attempts,
            "successes": self.successes,
            "deferred": self.deferred,
            "failures": self.failures,
            "last_started_at": self.last_started_at,
            "last_finished_at": self.last_finished_at,
            "last_success_at": self.last_success_at,
            "last_error_at": self.last_error_at,
            "last_error": self.last_error,
            "last_result": self.last_result,
        }

    def _write_status(self, *, running: bool) -> None:
        with self._status_lock:
            atomic_json(self.status_path, self._status_payload(running=running))

    def run_once(self) -> dict[str, Any]:
        busy = _generic_research_busy(self.research_status_path)
        if busy:
            return {
                **_scheduler_base(),
                "ok": True,
                "status": "deferred_generic_research_busy",
                "deferred_components": busy,
                "work_lock_acquired": False,
                "review": {"next_action": "retry_next_bounded_interval"},
            }

        work_lock = self.lock_factory(self.work_lock_path)
        if not work_lock.acquire():
            return {
                **_scheduler_base(),
                "ok": True,
                "status": "deferred_research_work_lock_busy",
                "deferred_components": [],
                "work_lock_acquired": False,
                "review": {"next_action": "retry_next_bounded_interval"},
            }
        try:
            orchestrator = self.orchestrator_factory(
                path=self.path,
                pages_per_exchange=self.pages_per_exchange,
            )
            payload = orchestrator.run_once()
        finally:
            work_lock.release()

        violations = _safety_violations(payload)
        if violations:
            return {
                **_scheduler_base(),
                "ok": False,
                "status": "safety_contract_blocked",
                "network_fetches": bool(payload.get("network_fetches")),
                "database_mutation": bool(payload.get("database_mutation")),
                "work_lock_acquired": True,
                "violations": violations,
                "blocked_pipeline_status": str(payload.get("status") or ""),
                "review": {"next_action": "repair_build69_safety_contract_before_retry"},
            }
        return {
            **payload,
            "build69_scheduler_version": BUILD69_SCHEDULER_VERSION,
            "build69_scheduler_name": BUILD69_SCHEDULER_NAME,
            "work_lock_acquired": True,
            "scheduled_interval_seconds": self.interval_seconds,
            "scheduled_pages_per_exchange": self.pages_per_exchange,
        }

    def _record_result(self, result: dict[str, Any]) -> None:
        self.last_result = result
        self.last_finished_at = time.time()
        status = str(result.get("status") or "")
        if status.startswith("deferred_"):
            self.deferred += 1
            self.last_success_at = self.last_finished_at
            self.last_error = ""
        elif result.get("ok"):
            self.successes += 1
            self.last_success_at = self.last_finished_at
            self.last_error = ""
        else:
            self.failures += 1
            self.last_error_at = self.last_finished_at
            self.last_error = f"pipeline_status={status or 'unknown'}"

    def _wait_with_heartbeat(self) -> None:
        deadline = time.time() + self.interval_seconds
        while not self.stop_event.is_set():
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            if self.stop_event.wait(min(HEARTBEAT_SECONDS, remaining)):
                return
            self._write_status(running=True)

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(HEARTBEAT_SECONDS):
            self._write_status(running=True)

    def run(self) -> None:
        process_lock = self.lock_factory(self.process_lock_path)
        if not process_lock.acquire():
            return
        self.process_lock_acquired = True
        self._heartbeat_stop.clear()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            name="build69-forward-heartbeat",
            daemon=True,
        )
        heartbeat.start()
        self._write_status(running=True)
        try:
            while not self.stop_event.is_set():
                self.attempts += 1
                self.last_started_at = time.time()
                self._write_status(running=True)
                try:
                    self._record_result(self.run_once())
                except Exception as exc:
                    self.failures += 1
                    self.last_finished_at = time.time()
                    self.last_error_at = self.last_finished_at
                    self.last_error = f"{type(exc).__name__}: {exc}"[:600]
                    self.last_result = {
                        **_scheduler_base(),
                        "ok": False,
                        "status": "retryable_scheduler_error",
                        "error": self.last_error,
                        "review": {"next_action": "retry_next_bounded_interval"},
                    }
                self._write_status(running=True)
                if not self.stop_event.is_set():
                    self._wait_with_heartbeat()
        finally:
            self._heartbeat_stop.set()
            heartbeat.join(timeout=HEARTBEAT_SECONDS + 1.0)
            self.process_lock_acquired = False
            self._write_status(running=False)
            process_lock.release()


def main() -> None:
    load_dotenv()
    raw_interval = os.getenv("DEX_FORWARD_PIPELINE_INTERVAL_SECONDS", "").strip()
    try:
        interval = float(raw_interval) if raw_interval else DEFAULT_INTERVAL_SECONDS
    except ValueError:
        interval = DEFAULT_INTERVAL_SECONDS
    scheduler = ForwardPipelineScheduler(interval_seconds=interval)

    def _stop(_signum, _frame) -> None:
        scheduler.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _stop)
        except (ValueError, OSError):
            pass
    scheduler.run()


if __name__ == "__main__":
    main()
