from __future__ import annotations

import json
import time
from pathlib import Path

from b3_trader.forward_pipeline_scheduler import ForwardPipelineScheduler
from b3_trader.research_work_lock import ResearchWorkLock


def _safe_pipeline(**overrides):
    payload = {
        "ok": True,
        "status": "waiting_no_forward_cases",
        "build69_version": 1,
        "build69_name": "dex_forward_pipeline_orchestrator_v1",
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_wired": False,
        "paper_ab_wired": False,
        "live_promotion_allowed": False,
        "forward_only": True,
        "network_fetches": True,
        "database_mutation": False,
        "forward_boundary": {"pre_cutoff_cases_selectable": False},
        "bounds": {
            "intake_runs_per_invocation": 1,
            "enrichment_runs_per_invocation": 1,
            "score_audits_per_invocation": 1,
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
        "steps": {
            "build66_score_audit": {"historical_rows_scored_as_v2": False},
        },
        "summary": {"processed_forward_cases": 0},
    }
    payload.update(overrides)
    return payload


class _FakeOrchestrator:
    def __init__(self, payload, calls, **kwargs) -> None:
        self.payload = payload
        self.calls = calls
        self.calls.append(kwargs)

    def run_once(self):
        return self.payload


def _factory(payload, calls):
    def create(**kwargs):
        return _FakeOrchestrator(payload, calls, **kwargs)

    return create


def _scheduler(tmp_path: Path, *, payload=None, calls=None) -> ForwardPipelineScheduler:
    call_rows = calls if calls is not None else []
    return ForwardPipelineScheduler(
        path=tmp_path / "db.sqlite3",
        status_path=tmp_path / "scheduler-status.json",
        research_status_path=tmp_path / "research-status.json",
        process_lock_path=tmp_path / "scheduler-process.lock",
        work_lock_path=tmp_path / "research-work.lock",
        interval_seconds=1,
        orchestrator_factory=_factory(payload or _safe_pipeline(), call_rows),
    )


def test_research_work_lock_is_nonblocking_and_releases(tmp_path: Path) -> None:
    path = tmp_path / "work.lock"
    first = ResearchWorkLock(path)
    second = ResearchWorkLock(path)
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()


def test_scheduler_runs_exactly_one_bounded_orchestrator(tmp_path: Path) -> None:
    calls = []
    scheduler = _scheduler(tmp_path, calls=calls)
    result = scheduler.run_once()
    assert result["ok"] is True
    assert result["status"] == "waiting_no_forward_cases"
    assert result["work_lock_acquired"] is True
    assert result["scheduled_pages_per_exchange"] == 2
    assert len(calls) == 1
    assert calls[0]["path"] == tmp_path / "db.sqlite3"
    assert calls[0]["pages_per_exchange"] == 2


def test_scheduler_defers_before_network_when_generic_research_is_running(tmp_path: Path) -> None:
    calls = []
    scheduler = _scheduler(tmp_path, calls=calls)
    scheduler.research_status_path.write_text(
        json.dumps(
            {
                "running": True,
                "updated_at": time.time(),
                "components": {
                    "listing-history-research": {
                        "enabled": True,
                        "status": "running",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    result = scheduler.run_once()
    assert result["status"] == "deferred_generic_research_busy"
    assert result["network_fetches"] is False
    assert result["database_mutation"] is False
    assert calls == []


def test_scheduler_defers_before_network_when_shared_lock_is_busy(tmp_path: Path) -> None:
    calls = []
    scheduler = _scheduler(tmp_path, calls=calls)
    owner = ResearchWorkLock(scheduler.work_lock_path)
    assert owner.acquire() is True
    try:
        result = scheduler.run_once()
    finally:
        owner.release()
    assert result["status"] == "deferred_research_work_lock_busy"
    assert result["network_fetches"] is False
    assert result["database_mutation"] is False
    assert calls == []


def test_scheduler_fails_closed_on_build69_safety_violation(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path, payload=_safe_pipeline(can_place_orders=True))
    result = scheduler.run_once()
    assert result["ok"] is False
    assert result["status"] == "safety_contract_blocked"
    assert result["can_place_orders"] is False
    assert "can_place_orders_not_false" in result["violations"]


def test_scheduler_process_writes_final_offline_status(tmp_path: Path) -> None:
    holder = {}

    class StopAfterOne:
        def __init__(self, **_kwargs) -> None:
            pass

        def run_once(self):
            holder["scheduler"].stop()
            return _safe_pipeline()

    scheduler = ForwardPipelineScheduler(
        path=tmp_path / "db.sqlite3",
        status_path=tmp_path / "scheduler-status.json",
        research_status_path=tmp_path / "research-status.json",
        process_lock_path=tmp_path / "scheduler-process.lock",
        work_lock_path=tmp_path / "research-work.lock",
        orchestrator_factory=StopAfterOne,
    )
    holder["scheduler"] = scheduler
    scheduler.run()
    status = json.loads(scheduler.status_path.read_text(encoding="utf-8"))
    assert status["running"] is False
    assert status["attempts"] == 1
    assert status["successes"] == 1
    assert status["last_result"]["status"] == "waiting_no_forward_cases"
    assert status["can_place_orders"] is False
    assert status["paper_ab_wired"] is False
