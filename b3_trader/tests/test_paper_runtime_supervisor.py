from __future__ import annotations

import json
from pathlib import Path

from b3_trader.paper_runtime_supervisor import PaperRuntimeSupervisor


class _ReturnImmediately:
    def run(self, stop_event=None) -> None:
        return


class _FailOnceThenStop:
    calls = 0

    def run(self, stop_event=None) -> None:
        type(self).calls += 1
        if type(self).calls == 1:
            raise RuntimeError("boom")
        assert stop_event is not None
        stop_event.set()


def test_unexpected_clean_return_is_restarted(tmp_path: Path) -> None:
    calls = {"count": 0}
    holder: dict[str, PaperRuntimeSupervisor] = {}

    class Runner:
        def run(self, stop_event=None) -> None:
            calls["count"] += 1
            if calls["count"] >= 2:
                holder["supervisor"].stop()

    status_path = tmp_path / "status.json"
    supervisor = PaperRuntimeSupervisor(
        Runner,
        restart_delay_seconds=0.001,
        status_path=status_path,
    )
    holder["supervisor"] = supervisor
    supervisor.run()

    assert calls["count"] == 2
    assert supervisor.restarts == 1
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["running"] is False
    assert payload["paper_only"] is True
    assert payload["can_place_real_orders"] is False


def test_constructor_or_run_exception_is_retried(tmp_path: Path) -> None:
    _FailOnceThenStop.calls = 0
    status_path = tmp_path / "status.json"
    supervisor = PaperRuntimeSupervisor(
        _FailOnceThenStop,
        restart_delay_seconds=0.001,
        status_path=status_path,
    )
    supervisor.run()

    assert _FailOnceThenStop.calls == 2
    assert supervisor.restarts == 1
    assert "RuntimeError: boom" in supervisor.last_error


def test_factory_exception_is_retried(tmp_path: Path) -> None:
    calls = {"count": 0}
    holder: dict[str, PaperRuntimeSupervisor] = {}

    def factory():
        calls["count"] += 1
        if calls["count"] == 1:
            raise ValueError("construct")

        class Runner:
            def run(self, stop_event=None) -> None:
                holder["supervisor"].stop()

        return Runner()

    supervisor = PaperRuntimeSupervisor(
        factory,
        restart_delay_seconds=0.001,
        status_path=tmp_path / "status.json",
    )
    holder["supervisor"] = supervisor
    supervisor.run()

    assert calls["count"] == 2
    assert supervisor.restarts == 1
    assert "ValueError: construct" in supervisor.last_error
