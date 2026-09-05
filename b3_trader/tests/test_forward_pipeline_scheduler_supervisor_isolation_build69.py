from __future__ import annotations

from b3_trader.market_notice_collector import MarketNoticeCollector
from b3_trader.research_control import COMPONENT_DEFINITIONS, default_control
from b3_trader.research_supervisor import ResearchSupervisor


class _UnavailableLock:
    acquired = False

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


def test_generic_listing_and_dex_are_blocked_in_forward_dedicated_mode() -> None:
    supervisor = ResearchSupervisor.__new__(ResearchSupervisor)
    supervisor.forward_pipeline_dedicated_mode = True
    assert supervisor._component_blocked_by_forward_mode("listing-history-research") is True
    assert supervisor._component_blocked_by_forward_mode("dex-launch-research") is True
    assert supervisor._component_blocked_by_forward_mode("market-notice-watch") is False


def test_component_install_forces_generic_research_off_without_mutating_control() -> None:
    supervisor = ResearchSupervisor.__new__(ResearchSupervisor)
    supervisor.forward_pipeline_dedicated_mode = True
    supervisor.control = default_control()
    supervisor.states = {}
    supervisor.wake_events = {}
    supervisor.force_run = {}
    supervisor.last_run_nonce = {}
    supervisor.threads = {}
    supervisor.runners = {name: (lambda: {}) for name in COMPONENT_DEFINITIONS}
    supervisor._install_components()
    assert supervisor.control["components"]["listing-history-research"]["enabled"] is True
    assert supervisor.states["listing-history-research"].enabled is False
    assert supervisor.states["dex-launch-research"].enabled is False
    assert supervisor.states["market-notice-watch"].enabled is True
    assert (
        supervisor.states["listing-history-research"].last_result["status"]
        == "disabled_by_forward_pipeline_dedicated_mode"
    )


def test_generic_listing_returns_noop_when_forward_work_lock_is_busy(monkeypatch) -> None:
    monkeypatch.setattr(
        "b3_trader.research_supervisor.ResearchWorkLock",
        lambda: _UnavailableLock(),
    )
    supervisor = ResearchSupervisor.__new__(ResearchSupervisor)
    supervisor.listing_history_research = None
    result = supervisor._run_listing_history_once()
    assert result["status"] == "deferred_forward_research_work_lock_busy"
    assert result["network_fetches"] is False
    assert result["database_mutation"] is False
    assert supervisor.listing_history_research is None


def test_generic_dex_returns_noop_when_forward_work_lock_is_busy(monkeypatch) -> None:
    monkeypatch.setattr(
        "b3_trader.research_supervisor.ResearchWorkLock",
        lambda: _UnavailableLock(),
    )
    supervisor = ResearchSupervisor.__new__(ResearchSupervisor)
    supervisor.dex_launch_research = None
    result = supervisor._run_dex_launch_once()
    assert result["status"] == "deferred_forward_research_work_lock_busy"
    assert result["network_fetches"] is False
    assert result["database_mutation"] is False
    assert supervisor.dex_launch_research is None


def test_market_notice_watch_defers_without_source_calls_when_forward_lock_is_busy(
    monkeypatch,
    tmp_path,
) -> None:
    class Source:
        exchange = "test"
        source = "must_not_run"

        def fetch(self):
            raise AssertionError("network source must not run while forward lock is busy")

    monkeypatch.setattr(
        "b3_trader.market_notice_collector.ResearchWorkLock",
        lambda: _UnavailableLock(),
    )
    collector = MarketNoticeCollector(tmp_path / "db.sqlite3", sources=(Source(),))
    result = collector.run_once()
    assert result["status"] == "deferred_forward_research_work_lock_busy"
    assert result["network_fetches"] is False
    assert result["database_mutation"] is False
    assert not (tmp_path / "db.sqlite3").exists()
