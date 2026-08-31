from __future__ import annotations

from pathlib import Path

import b3_trader.dex_shadow_score_v2_forward_validation as build71
from b3_trader.dex_shadow_score_v2_forward_validation import (
    audit_dex_shadow_score_v2_forward_validation,
)
from b3_trader.dex_shadow_score_v2_preregistration import (
    FORWARD_CUTOFF_TS,
    FORWARD_CUTOFF_UTC,
    V2_SCORE_NAME,
    V2_SCORE_VERSION,
)


def _row(index: int, *, inverted: bool = False) -> dict:
    asset_index = index if index < 20 else index - 10
    score = 20.0 + asset_index * 3.0
    outcome = (score - 50.0) * (-1.0 if inverted else 1.0)
    return {
        "score_version": V2_SCORE_VERSION,
        "score_name": V2_SCORE_NAME,
        "case_key": f"bithumb|KRW-T{index}|notice:{index}",
        "coingecko_id": f"asset-{asset_index}",
        "domestic_exchange": "bithumb" if index % 2 == 0 else "upbit",
        "domestic_market": f"KRW-T{index}",
        "domestic_open_at": FORWARD_CUTOFF_TS + index * 3600.0,
        "forward_eligible": True,
        "shadow_score": score,
        "confidence": 1.0 if index % 4 == 0 else 0.8,
        "evaluation_only_outcomes": {
            "excluded_from_score": True,
            "post_listing_returns_pct": {
                "p1h": outcome * 0.5,
                "p6h": outcome * 0.8,
                "p24h": outcome,
            },
        },
    }


def _score_payload(rows: list[dict]) -> dict:
    return {
        "ok": True,
        "status": "scored_forward_only" if rows else "forward_waiting_no_eligible_cases",
        "score_version": V2_SCORE_VERSION,
        "score_name": V2_SCORE_NAME,
        "forward_only": True,
        "all_forward_eligible_cases_scored": True,
        "historical_rows_scored_as_v2": False,
        "historical_rows_eligible_for_v2_validation": False,
        "score_wired": False,
        "paper_ab_wired": False,
        "can_place_orders": False,
        "case_score_count": len(rows),
        "forward_eligible_case_count": len(rows),
        "forward_boundary": {
            "cutoff_utc": FORWARD_CUTOFF_UTC,
            "cutoff_unix": FORWARD_CUTOFF_TS,
        },
        "case_scores": rows,
    }


def test_build71_refuses_statistics_before_build70_readiness(monkeypatch, tmp_path: Path) -> None:
    def forbidden(_: list[dict]) -> dict:
        raise AssertionError("statistics must not run before Build70 readiness")

    monkeypatch.setattr(build71, "_core_metrics", forbidden)
    result = audit_dex_shadow_score_v2_forward_validation(
        tmp_path / "unused.sqlite",
        score_audit_fn=lambda _: _score_payload([]),
    )
    assert result["ok"] is True
    assert result["status"] == "waiting_for_forward_sample"
    assert result["validation_statistics_calculated"] is False
    assert result["statistics"] is None
    assert result["sample_ledger"]["event_count"] == 0
    assert result["validation_gate"]["build72_parallel_paper_ab_allowed"] is False


def test_build71_passes_positive_preregistered_forward_signal(tmp_path: Path) -> None:
    rows = [_row(index) for index in range(30)]
    result = audit_dex_shadow_score_v2_forward_validation(
        tmp_path / "unused.sqlite",
        score_audit_fn=lambda _: _score_payload(rows),
    )
    assert result["ok"] is True
    assert result["status"] == "forward_validation_passed"
    assert result["build70_readiness_gate_passed"] is True
    assert result["validation_statistics_calculated"] is True
    assert result["sample_integrity"]["event_count"] == 30
    assert result["sample_integrity"]["unique_asset_count"] == 20
    assert result["validation_protocol"]["all_criteria_pass"] is True
    assert len(result["validation_protocol"]["observed"]["primary_asset_dedup_positive_rank_windows"]) == 3
    assert result["validation_gate"]["build72_parallel_paper_ab_allowed"] is True
    assert result["paper_ab_wired"] is False
    assert result["can_place_orders"] is False


def test_build71_rejects_inverted_forward_signal_without_fitting(tmp_path: Path) -> None:
    rows = [_row(index, inverted=True) for index in range(30)]
    result = audit_dex_shadow_score_v2_forward_validation(
        tmp_path / "unused.sqlite",
        score_audit_fn=lambda _: _score_payload(rows),
    )
    assert result["ok"] is True
    assert result["status"] == "forward_validation_failed"
    assert result["validation_statistics_calculated"] is True
    assert result["validation_protocol"]["all_criteria_pass"] is False
    assert result["validation_protocol"]["observed"]["strong_negative_core_windows"]
    assert result["validation_gate"]["build72_parallel_paper_ab_allowed"] is False
    assert result["training_or_fitting"] is False
    assert result["trade_threshold"] is None


def test_build71_blocks_pre_cutoff_contamination_before_statistics(monkeypatch, tmp_path: Path) -> None:
    rows = [_row(index) for index in range(30)]
    rows[0]["domestic_open_at"] = FORWARD_CUTOFF_TS - 1.0

    def forbidden(_: list[dict]) -> dict:
        raise AssertionError("statistics must not run on contaminated rows")

    monkeypatch.setattr(build71, "_core_metrics", forbidden)
    result = audit_dex_shadow_score_v2_forward_validation(
        tmp_path / "unused.sqlite",
        score_audit_fn=lambda _: _score_payload(rows),
    )
    assert result["ok"] is False
    assert result["status"] == "forward_sample_integrity_blocked"
    assert result["validation_statistics_calculated"] is False
    assert any(
        issue["reason"] == "pre_cutoff_or_missing_domestic_open"
        for issue in result["sample_integrity"]["issues_preview"]
    )


def test_build71_blocks_incomplete_identity_before_statistics(monkeypatch, tmp_path: Path) -> None:
    rows = [_row(index) for index in range(30)]
    rows[0]["coingecko_id"] = ""

    def forbidden(_: list[dict]) -> dict:
        raise AssertionError("statistics must not run without canonical identity")

    monkeypatch.setattr(build71, "_core_metrics", forbidden)
    result = audit_dex_shadow_score_v2_forward_validation(
        tmp_path / "unused.sqlite",
        score_audit_fn=lambda _: _score_payload(rows),
    )
    assert result["ok"] is False
    assert result["status"] == "forward_sample_integrity_blocked"
    assert result["validation_statistics_calculated"] is False
    assert any(
        issue["reason"] == "identity_incomplete"
        for issue in result["sample_integrity"]["issues_preview"]
    )


def test_build71_blocks_wrong_score_contract(tmp_path: Path) -> None:
    payload = _score_payload([])
    payload["score_version"] = 1
    result = audit_dex_shadow_score_v2_forward_validation(
        tmp_path / "unused.sqlite",
        score_audit_fn=lambda _: payload,
    )
    assert result["ok"] is False
    assert result["status"] == "build66_score_contract_blocked"
    assert result["validation_statistics_calculated"] is False
    assert result["review"]["build72_parallel_paper_ab_allowed"] is False
