from __future__ import annotations

from pathlib import Path

import b3_trader.dex_launch_backfill as mod


class FakeStore:
    def __init__(self, pending=None) -> None:
        self.pending = list(pending or [])
        self.restored: list[dict] = []

    def listing_cases(self, limit=500):
        return list(self.pending)

    def upsert_case_status(self, case_key, **kwargs):
        self.restored.append({"case_key": case_key, **kwargs})


class FakeCycle:
    def __init__(self, pending=None, result=None) -> None:
        self.store = FakeStore(pending)
        self.result = dict(result or {"status": "complete"})
        self.calls: list[str] = []

    def _research_case(self, row, now):
        self.calls.append(str(row.get("case_key") or ""))
        return {"case_key": row.get("case_key"), **self.result}


def _quality() -> dict:
    return {
        "ok": True,
        "sample_ready": False,
        "usable_case_count": 5,
        "exact_p5m_coverage": 0.8,
        "complete_partial_case_count": 1,
        "cases": [
            {
                "case_key": "partial",
                "coingecko_id": "partial-coin",
                "stored_status": "complete",
                "derived_completion": "complete_partial",
                "expected_research_assets": 2,
                "usable_feature_asset_count": 1,
            },
            {
                "case_key": "retryable",
                "coingecko_id": "retry-coin",
                "stored_status": "source_waiting",
                "derived_completion": "not_usable",
            },
        ],
    }


def test_plan_prioritizes_normal_retryable_before_complete_partial(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mod, "evaluate_dex_launch_quality", lambda path: _quality())
    monkeypatch.setattr(mod, "_supervisor_busy", lambda path: False)
    monkeypatch.setattr(
        mod,
        "_listing_case",
        lambda path, key: {
            "case_key": key,
            "domestic_market": "KRW-PART",
            "identity_verified": 1,
            "identity": {"provider": "coingecko", "provider_id": "partial-coin"},
        },
    )
    cycle = FakeCycle(
        pending=[
            {
                "case_key": "retryable",
                "domestic_market": "KRW-RETRY",
                "dex_status": "source_waiting",
            }
        ]
    )
    runner = mod.DexLaunchBackfillRunner(
        tmp_path / "db.sqlite3",
        state_path=tmp_path / "state.json",
        status_path=tmp_path / "status.json",
        cycle=cycle,
    )
    plan = runner.plan(now=100000.0)
    assert [row["case_key"] for row in plan["candidates"]] == ["retryable", "partial"]
    assert plan["candidates"][0]["reason"] == "eligible_unresearched_or_retryable"
    assert plan["candidates"][1]["reason"] == "complete_partial_retry"
    assert plan["max_cases_per_run"] == 2
    assert plan["can_place_orders"] is False
    assert plan["score_wired"] is False


def test_partial_retry_preserves_stored_complete_on_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mod, "evaluate_dex_launch_quality", lambda path: _quality())
    monkeypatch.setattr(mod, "_supervisor_busy", lambda path: False)
    monkeypatch.setattr(
        mod,
        "_listing_case",
        lambda path, key: {
            "case_key": key,
            "domestic_exchange": "bithumb",
            "domestic_market": "KRW-PART",
            "symbol": "PART",
            "domestic_open_at": 1000.0,
            "identity_verified": 1,
            "identity": {"provider": "coingecko", "provider_id": "partial-coin"},
        },
    )
    monkeypatch.setattr(
        mod,
        "_case_status",
        lambda path, key: {
            "case_key": key,
            "coingecko_id": "partial-coin",
            "status": "complete",
            "contract_count": 2,
            "accepted_pool_count": 1,
            "error": "",
        },
    )
    cycle = FakeCycle(result={"status": "source_waiting", "error": "HTTP 429"})
    runner = mod.DexLaunchBackfillRunner(
        tmp_path / "db.sqlite3",
        state_path=tmp_path / "state.json",
        status_path=tmp_path / "status.json",
        cycle=cycle,
    )
    result = runner.run_once(max_cases=1)
    assert result["processed"] == 1
    assert cycle.calls == ["partial"]
    assert result["results"][0]["stored_complete_preserved"] is True
    assert cycle.store.restored[0]["case_key"] == "partial"
    assert cycle.store.restored[0]["status"] == "complete"
    assert cycle.store.restored[0]["contract_count"] == 2
    assert result["can_place_orders"] is False
    assert result["score_wired"] is False


def test_backfill_refuses_network_work_while_normal_supervisor_is_running(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mod, "evaluate_dex_launch_quality", lambda path: _quality())
    monkeypatch.setattr(mod, "_supervisor_busy", lambda path: True)
    monkeypatch.setattr(
        mod,
        "_listing_case",
        lambda path, key: {"case_key": key, "domestic_market": "KRW-PART", "identity_verified": 1},
    )
    cycle = FakeCycle(
        pending=[{"case_key": "retryable", "domestic_market": "KRW-RETRY", "dex_status": "source_waiting"}]
    )
    runner = mod.DexLaunchBackfillRunner(
        tmp_path / "db.sqlite3",
        state_path=tmp_path / "state.json",
        status_path=tmp_path / "status.json",
        cycle=cycle,
    )
    result = runner.run_once(max_cases=2)
    assert result["status"] == "supervisor_busy"
    assert result["processed"] == 0
    assert cycle.calls == []
