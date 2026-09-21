from __future__ import annotations

import json
from pathlib import Path

from b3_trader.listing_history_accelerator import (
    DEFAULT_CYCLES_PER_RUN,
    INTER_CYCLE_SECONDS,
    MAX_CYCLES_PER_RUN,
    ListingHistoryAccelerator,
)


class FakeStore:
    def __init__(self, pending: list[dict]) -> None:
        self.pending = list(pending)

    def pending_cases(self, limit: int = 500, *, required_feature_version: int = 0) -> list[dict]:
        del required_feature_version
        return list(self.pending[:limit])


class FakeCycle:
    def __init__(self, pending: list[dict], results: list[dict]) -> None:
        self.store = FakeStore(pending)
        self.results = list(results)
        self.calls = 0

    def run_once(self) -> dict:
        self.calls += 1
        result = self.results.pop(0)
        processed = int(result.get("processed") or 0)
        if processed > 0:
            self.store.pending = self.store.pending[processed:]
        return result


def _pending(count: int) -> list[dict]:
    return [
        {
            "case_key": f"case-{index}",
            "domestic_market": f"KRW-T{index}",
            "domestic_exchange": "bithumb",
            "status": "pending_identity",
            "identity_verified": 0,
        }
        for index in range(count)
    ]


def test_build48_plan_is_bounded_and_read_only(tmp_path: Path) -> None:
    cycle = FakeCycle(_pending(9), [])
    runner = ListingHistoryAccelerator(
        tmp_path / "db.sqlite3",
        cycle=cycle,
        status_path=tmp_path / "status.json",
        sleeper=lambda _: None,
    )
    plan = runner.plan()
    assert plan["paper_only"] is True
    assert plan["shadow_only"] is True
    assert plan["can_place_orders"] is False
    assert plan["score_wired"] is False
    assert plan["pending_case_count"] == 9
    assert plan["default_cycles_per_run"] == DEFAULT_CYCLES_PER_RUN == 2
    assert plan["max_cycles_per_run"] == MAX_CYCLES_PER_RUN == 4
    assert plan["default_case_budget"] == 6
    assert plan["max_case_budget"] == 12
    assert plan["inter_cycle_seconds"] == INTER_CYCLE_SECONDS == 15.0
    assert cycle.calls == 0


def test_build48_blocks_when_normal_supervisor_is_running(tmp_path: Path) -> None:
    status_path = tmp_path / "status.json"
    status_path.write_text(
        json.dumps(
            {
                "running": True,
                "components": {
                    "listing-history-research": {"enabled": True, "status": "running"}
                },
            }
        ),
        encoding="utf-8",
    )
    cycle = FakeCycle(_pending(6), [])
    runner = ListingHistoryAccelerator(
        tmp_path / "db.sqlite3",
        cycle=cycle,
        status_path=status_path,
        sleeper=lambda _: None,
    )
    result = runner.run_once(cycles=2)
    assert result["status"] == "supervisor_busy"
    assert result["processed"] == 0
    assert cycle.calls == 0


def test_build48_runs_existing_three_case_cycles_sequentially(tmp_path: Path) -> None:
    sleeps: list[float] = []
    cycle = FakeCycle(
        _pending(8),
        [
            {
                "status": "researched",
                "pending_cases": 8,
                "processed": 3,
                "collected": 2,
                "identity_waiting": 1,
                "source_errors": 0,
                "elapsed_seconds": 1.0,
                "results": [
                    {"case_key": "case-0", "market": "KRW-T0", "status": "complete"},
                    {"case_key": "case-1", "market": "KRW-T1", "status": "pending_identity"},
                    {"case_key": "case-2", "market": "KRW-T2", "status": "complete"},
                ],
            },
            {
                "status": "researched",
                "pending_cases": 5,
                "processed": 3,
                "collected": 3,
                "identity_waiting": 0,
                "source_errors": 0,
                "elapsed_seconds": 1.5,
                "results": [
                    {"case_key": "case-3", "market": "KRW-T3", "status": "complete"},
                    {"case_key": "case-4", "market": "KRW-T4", "status": "complete"},
                    {"case_key": "case-5", "market": "KRW-T5", "status": "complete"},
                ],
            },
        ],
    )
    runner = ListingHistoryAccelerator(
        tmp_path / "db.sqlite3",
        cycle=cycle,
        status_path=tmp_path / "status.json",
        sleeper=sleeps.append,
    )
    result = runner.run_once(cycles=2)
    assert result["status"] == "accelerated"
    assert result["completed_cycles"] == 2
    assert result["processed"] == 6
    assert result["collected"] == 5
    assert result["identity_waiting"] == 1
    assert result["pending_before"] == 8
    assert result["pending_after"] == 2
    assert result["case_budget"] == 6
    assert sleeps == [INTER_CYCLE_SECONDS]
    assert cycle.calls == 2


def test_build48_stops_on_all_source_errors(tmp_path: Path) -> None:
    cycle = FakeCycle(
        _pending(8),
        [
            {
                "status": "researched",
                "pending_cases": 8,
                "processed": 3,
                "collected": 0,
                "identity_waiting": 0,
                "source_errors": 3,
                "elapsed_seconds": 1.0,
                "results": [],
            },
            {
                "status": "researched",
                "pending_cases": 5,
                "processed": 3,
                "collected": 3,
                "identity_waiting": 0,
                "source_errors": 0,
                "elapsed_seconds": 1.0,
                "results": [],
            },
        ],
    )
    runner = ListingHistoryAccelerator(
        tmp_path / "db.sqlite3",
        cycle=cycle,
        status_path=tmp_path / "status.json",
        sleeper=lambda _: None,
    )
    result = runner.run_once(cycles=4)
    assert result["processed"] == 3
    assert result["stop_reason"] == "source_error_guard"
    assert cycle.calls == 1
