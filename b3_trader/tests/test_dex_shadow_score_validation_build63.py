from __future__ import annotations

from pathlib import Path

from b3_trader.dex_shadow_score_validation import (
    CORE_WINDOWS,
    MIN_ASSET_LABELS_PER_CORE,
    MIN_EVENT_LABELS_PER_CORE,
    VALIDATION_NAME,
    VALIDATION_VERSION,
    audit_dex_shadow_score_validation,
)


def _score_payload(*, inverted: bool = False, ready: bool = True) -> dict:
    rows = []
    event_count = max(MIN_EVENT_LABELS_PER_CORE + 2, 32)
    asset_count = max(MIN_ASSET_LABELS_PER_CORE + 4, 24)
    for idx in range(event_count):
        score = 20.0 + idx * (60.0 / max(1, event_count - 1))
        direction = -1.0 if inverted else 1.0
        base_outcome = direction * (score - 50.0)
        outcomes = {
            "p5m": base_outcome * 0.15,
            "p1h": base_outcome * 0.50,
            "p6h": base_outcome * 0.80,
            "p24h": base_outcome * 1.00,
            "p3d": base_outcome * 0.70,
            "p7d": base_outcome * 0.40,
        }
        rows.append(
            {
                "case_key": f"exchange|KRW-T{idx}|notice:{idx}",
                "coingecko_id": f"asset-{idx % asset_count}",
                "domestic_exchange": "bithumb" if idx % 2 == 0 else "upbit",
                "domestic_open_at": 1_700_000_000.0 + idx * 3600.0,
                "shadow_score": score,
                "confidence": 1.0 if idx % 4 == 0 else 0.8,
                "components": {
                    "launch_continuity": {"available": idx % 3 == 0},
                },
                "evaluation_only_outcomes": {
                    "excluded_from_score": True,
                    "post_listing_returns_pct": outcomes,
                },
            }
        )
    return {
        "ok": ready,
        "status": "scored_read_only" if ready else "readiness_blocked",
        "score_version": 1,
        "score_name": "dex_prelisting_shadow_hypothesis_v1",
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_wired": False,
        "all_usable_cases_scored": ready,
        "retrospective_source_selection": True,
        "case_scores": rows if ready else [],
    }


def test_build63_positive_monotonic_signal_becomes_paper_ab_candidate() -> None:
    payload = audit_dex_shadow_score_validation(
        Path("unused.db"),
        score_audit_fn=lambda _: _score_payload(),
    )
    assert payload["ok"] is True
    assert payload["status"] == "validated_read_only"
    assert payload["validation_version"] == VALIDATION_VERSION
    assert payload["validation_name"] == VALIDATION_NAME
    assert payload["event_case_count"] >= MIN_EVENT_LABELS_PER_CORE
    assert payload["asset_count_dedup"] >= MIN_ASSET_LABELS_PER_CORE
    assert payload["duplicate_event_case_count"] > 0
    assert payload["validation_protocol"]["all_criteria_pass"] is True
    assert payload["validation_gate"]["paper_ab_candidate_advisory"] is True
    assert payload["validation_gate"]["live_promotion_allowed"] is False
    assert payload["forward_validation_required"] is True
    assert payload["promotion_to_live_blocked"] is True
    assert payload["paper_ab_wired"] is False
    assert payload["can_place_orders"] is False


def test_build63_inverted_signal_is_rejected() -> None:
    payload = audit_dex_shadow_score_validation(
        Path("unused.db"),
        score_audit_fn=lambda _: _score_payload(inverted=True),
    )
    assert payload["ok"] is True
    assert payload["validation_gate"]["paper_ab_candidate_advisory"] is False
    assert payload["validation_protocol"]["all_criteria_pass"] is False
    assert payload["validation_protocol"]["observed"]["strong_negative_core_windows"]
    for window in CORE_WINDOWS:
        assert payload["event_level"]["windows"][window]["spearman"] < 0.0
        assert payload["asset_level_dedup"]["windows"][window]["spearman"] < 0.0


def test_build63_asset_dedup_collapses_duplicate_event_cases() -> None:
    source = _score_payload()
    payload = audit_dex_shadow_score_validation(
        Path("unused.db"),
        score_audit_fn=lambda _: source,
    )
    unique_assets = len({row["coingecko_id"] for row in source["case_scores"]})
    assert payload["asset_count_dedup"] == unique_assets
    assert payload["duplicate_event_case_count"] == len(source["case_scores"]) - unique_assets


def test_build63_fails_closed_when_build62_is_not_ready() -> None:
    payload = audit_dex_shadow_score_validation(
        Path("unused.db"),
        score_audit_fn=lambda _: _score_payload(ready=False),
    )
    assert payload["ok"] is False
    assert payload["status"] == "build62_score_audit_blocked"
    assert payload["score_audit_ready"] is False
    assert payload["validation_gate"]["paper_ab_candidate_advisory"] is False
    assert payload["paper_ab_wired"] is False
    assert payload["can_place_orders"] is False
