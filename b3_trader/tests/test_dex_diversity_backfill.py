from __future__ import annotations

from pathlib import Path

from b3_trader import dex_diversity_backfill as module
from b3_trader.dex_launch_backfill import DexLaunchBackfillRunner


def test_diversity_priority_order() -> None:
    usable = {"already-usable"}
    assert module._candidate_priority(
        {"reason": "eligible_unresearched_or_retryable", "coingecko_id": "new-asset"},
        usable_asset_ids=usable,
    ) == (module.PRIORITY_NEW_UNIQUE, "new_unique_asset")
    assert module._candidate_priority(
        {"reason": "eligible_unresearched_or_retryable", "coingecko_id": ""},
        usable_asset_ids=usable,
    ) == (module.PRIORITY_UNKNOWN_IDENTITY, "identity_unknown_unique_potential")
    assert module._candidate_priority(
        {"reason": "eligible_unresearched_or_retryable", "coingecko_id": "already-usable"},
        usable_asset_ids=usable,
    ) == (module.PRIORITY_DUPLICATE_EVENT, "duplicate_asset_event")
    assert module._candidate_priority(
        {"reason": "complete_partial_retry", "coingecko_id": "new-asset"},
        usable_asset_ids=usable,
    ) == (module.PRIORITY_PARTIAL_RETRY, "partial_completion_retry")


def test_plan_prioritizes_new_unique_before_duplicate_and_partial(monkeypatch, tmp_path: Path) -> None:
    runner = module.DexDiversityBackfillRunner.__new__(module.DexDiversityBackfillRunner)
    runner.path = tmp_path / "db.sqlite3"

    base_plan = {
        "status": "planned",
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_wired": False,
        "candidate_count": 4,
        "candidates": [
            {
                "case_key": "dup",
                "coingecko_id": "already-usable",
                "reason": "eligible_unresearched_or_retryable",
            },
            {
                "case_key": "partial",
                "coingecko_id": "partial-asset",
                "reason": "complete_partial_retry",
            },
            {
                "case_key": "unknown",
                "coingecko_id": "",
                "reason": "eligible_unresearched_or_retryable",
            },
            {
                "case_key": "new",
                "coingecko_id": "new-asset",
                "reason": "eligible_unresearched_or_retryable",
            },
        ],
    }
    monkeypatch.setattr(DexLaunchBackfillRunner, "plan", lambda self, limit=100, now=None: base_plan)
    monkeypatch.setattr(
        module,
        "evaluate_dex_launch_quality",
        lambda path: {
            "cases": [
                {"coingecko_id": "already-usable", "usable_for_shadow_analysis": True},
            ]
        },
    )
    monkeypatch.setattr(
        module,
        "audit_dex_sample",
        lambda path: {
            "event_cases": {
                "usable": 16,
                "unique_assets": 12,
                "duplicate_event_cases": 4,
                "unique_asset_ratio": 0.75,
            },
            "coverage": {
                "complete_partial_ratio": 0.5,
                "exact_p5m_coverage": 0.875,
                "launch_feature_coverage": 0.1875,
            },
        },
    )
    monkeypatch.setattr(module, "_verified_listing_coingecko_id", lambda path, key: "")

    plan = runner.plan(limit=10)
    assert [row["case_key"] for row in plan["candidates"]] == ["new", "unknown", "dup", "partial"]
    assert plan["policy"]["changes_build45_thresholds"] is False
    assert plan["sample_composition"]["unique_assets"] == 12


def test_sample_ready_stops_without_network_work(monkeypatch, tmp_path: Path) -> None:
    runner = module.DexDiversityBackfillRunner.__new__(module.DexDiversityBackfillRunner)
    runner.path = tmp_path / "db.sqlite3"
    monkeypatch.setattr(
        module,
        "audit_dex_sample",
        lambda path: {
            "sample_ready_build45": True,
            "event_cases": {"usable": 20, "unique_assets": 16},
        },
    )
    result = runner.run_once(max_cases=2)
    assert result["status"] == "sample_ready_stop"
    assert result["processed"] == 0
    assert result["can_place_orders"] is False
