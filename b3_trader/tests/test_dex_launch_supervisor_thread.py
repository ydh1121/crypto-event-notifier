from __future__ import annotations

import threading

from b3_trader.research_supervisor import ResearchSupervisor


def test_dex_launch_cycle_is_created_run_and_closed_on_component_thread(monkeypatch) -> None:
    events: list[tuple[str, int]] = []

    class FakeCycle:
        def __init__(self) -> None:
            events.append(("init", threading.get_ident()))

        def run_once(self):
            events.append(("run", threading.get_ident()))
            return {"status": "researched", "paper_only": True, "can_place_orders": False}

        def close(self) -> None:
            events.append(("close", threading.get_ident()))

    monkeypatch.setattr("b3_trader.research_supervisor.DexLaunchResearchCycle", FakeCycle)

    supervisor = ResearchSupervisor.__new__(ResearchSupervisor)
    supervisor.dex_launch_research = None
    main_thread = threading.get_ident()
    result_holder: dict[str, object] = {}

    def worker() -> None:
        result_holder["result"] = supervisor._run_dex_launch_once()
        supervisor._close_component_resources("dex-launch-research")

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=5)

    assert thread.is_alive() is False
    assert result_holder["result"] == {
        "status": "researched",
        "paper_only": True,
        "can_place_orders": False,
    }
    assert [name for name, _ in events] == ["init", "run", "close"]
    owner_threads = {thread_id for _, thread_id in events}
    assert len(owner_threads) == 1
    assert main_thread not in owner_threads
    assert supervisor.dex_launch_research is None
