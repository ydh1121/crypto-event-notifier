from __future__ import annotations

import threading

from b3_trader.research_supervisor import ResearchSupervisor


def test_listing_history_cycle_is_created_run_and_closed_on_component_thread(monkeypatch) -> None:
    events: list[tuple[str, int]] = []

    class FakeCycle:
        def __init__(self) -> None:
            events.append(("init", threading.get_ident()))

        def run_once(self):
            events.append(("run", threading.get_ident()))
            return {"status": "ok"}

        def close(self) -> None:
            events.append(("close", threading.get_ident()))

    monkeypatch.setattr("b3_trader.research_supervisor.ListingHistoryResearchCycle", FakeCycle)

    supervisor = ResearchSupervisor.__new__(ResearchSupervisor)
    supervisor.listing_history_research = None
    main_thread = threading.get_ident()
    result_holder: dict[str, object] = {}

    def worker() -> None:
        result_holder["result"] = supervisor._run_listing_history_once()
        supervisor._close_component_resources("listing-history-research")

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=5)

    assert thread.is_alive() is False
    assert result_holder["result"] == {"status": "ok"}
    assert [name for name, _ in events] == ["init", "run", "close"]
    owner_threads = {thread_id for _, thread_id in events}
    assert len(owner_threads) == 1
    assert main_thread not in owner_threads
    assert supervisor.listing_history_research is None
