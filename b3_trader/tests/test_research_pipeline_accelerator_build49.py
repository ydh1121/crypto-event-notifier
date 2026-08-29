from __future__ import annotations

from pathlib import Path

import b3_trader.research_pipeline_accelerator as mod


class FakeListing:
    def __init__(self, pending: int = 5) -> None:
        self.pending = pending
        self.run_calls = 0

    def plan(self):
        return {"pending_case_count": self.pending}

    def run_once(self, *, cycles: int):
        self.run_calls += 1
        return {"status": "accelerated", "processed": cycles * 3}


class FakeDex:
    def __init__(self, candidates: int = 3) -> None:
        self.candidates = candidates
        self.run_calls = 0

    def plan(self, *, limit: int = 100):
        return {"candidate_count": self.candidates, "candidates": [{"case_key": "x"}] * min(self.candidates, 2)}

    def run_once(self, *, max_cases: int):
        self.run_calls += 1
        return {"status": "backfilled", "processed": min(max_cases, self.candidates)}


def _quality(*_args, **_kwargs):
    return {
        "usable_case_count": 10,
        "exact_p5m_case_count": 8,
        "exact_p5m_coverage": 0.8,
        "complete_partial_case_count": 6,
        "sample_ready": False,
        "blocking_reasons": ["usable_cases_below_min:10/20"],
    }


def test_dex_backlog_skips_listing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mod, "evaluate_dex_launch_quality", _quality)
    monkeypatch.setattr(mod, "_component_busy", lambda *_args, **_kwargs: False)
    listing = FakeListing(pending=18)
    dex = FakeDex(candidates=23)
    runner = mod.ResearchPipelineAccelerator(tmp_path / "db.sqlite3", listing=listing, dex=dex)
    plan = runner.plan()
    assert plan["action"] == "dex_backfill_only"
    result = runner.run_once(dex_cases=2)
    assert result["processed_listing"] == 0
    assert result["processed_dex"] == 2
    assert listing.run_calls == 0
    assert dex.run_calls == 1


def test_listing_runs_only_when_dex_backlog_small(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mod, "evaluate_dex_launch_quality", _quality)
    monkeypatch.setattr(mod, "_component_busy", lambda *_args, **_kwargs: False)
    listing = FakeListing(pending=6)
    dex = FakeDex(candidates=0)

    def listing_run(*, cycles: int):
        listing.run_calls += 1
        dex.candidates = 2
        return {"status": "accelerated", "processed": cycles * 3}

    listing.run_once = listing_run
    runner = mod.ResearchPipelineAccelerator(tmp_path / "db.sqlite3", listing=listing, dex=dex)
    assert runner.plan()["action"] == "listing_then_dex"
    result = runner.run_once(listing_cycles=1, dex_cases=2)
    assert result["processed_listing"] == 3
    assert result["processed_dex"] == 2
    assert listing.run_calls == 1
    assert dex.run_calls == 1


def test_busy_supervisor_blocks_all_work(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mod, "evaluate_dex_launch_quality", _quality)
    monkeypatch.setattr(mod, "_component_busy", lambda _path, name: name == "dex-launch-research")
    listing = FakeListing(pending=18)
    dex = FakeDex(candidates=23)
    runner = mod.ResearchPipelineAccelerator(tmp_path / "db.sqlite3", listing=listing, dex=dex)
    assert runner.plan()["action"] == "supervisor_busy"
    result = runner.run_once()
    assert result["status"] == "supervisor_busy"
    assert result["processed_listing"] == 0
    assert result["processed_dex"] == 0
