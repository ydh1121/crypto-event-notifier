from __future__ import annotations

import inspect

from b3_trader.research_supervisor import (
    FORWARD_PIPELINE_BLOCKED_COMPONENTS,
    ResearchSupervisor,
)


class _FakeIntelligenceCycle:
    def __init__(self) -> None:
        self.calls: list[bool] = []
        self.closed = False

    def run_once(self, *, network_enabled: bool = False):
        self.calls.append(bool(network_enabled))
        return {
            "status": "ok",
            "paper_only": True,
            "can_place_orders": False,
            "score_mutation": False,
        }

    def close(self) -> None:
        self.closed = True


def _supervisor_with_cycle(cycle: _FakeIntelligenceCycle) -> ResearchSupervisor:
    supervisor = ResearchSupervisor.__new__(ResearchSupervisor)
    supervisor.intelligence_ingest = cycle
    return supervisor


def test_phase5_supervisor_runner_enables_network_but_not_orders_or_scores() -> None:
    cycle = _FakeIntelligenceCycle()
    supervisor = _supervisor_with_cycle(cycle)
    result = supervisor._run_intelligence_ingest_once()
    assert cycle.calls == [True]
    assert result["paper_only"] is True
    assert result["can_place_orders"] is False
    assert result["score_mutation"] is False


def test_phase5_supervisor_closes_thread_affine_cycle() -> None:
    cycle = _FakeIntelligenceCycle()
    supervisor = _supervisor_with_cycle(cycle)
    supervisor._close_component_resources("phase5-intelligence-ingest")
    assert cycle.closed is True
    assert supervisor.intelligence_ingest is None


def test_phase5_does_not_change_dex_forward_pipeline_blocked_components() -> None:
    assert FORWARD_PIPELINE_BLOCKED_COMPONENTS == {
        "listing-history-research",
        "dex-launch-research",
    }
    assert "phase5-intelligence-ingest" not in FORWARD_PIPELINE_BLOCKED_COMPONENTS


def test_phase5_runner_does_not_take_research_work_lock() -> None:
    source = inspect.getsource(ResearchSupervisor._run_intelligence_ingest_once)
    assert "ResearchWorkLock" not in source
    assert "network_enabled=True" in source
