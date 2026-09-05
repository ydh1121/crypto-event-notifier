from __future__ import annotations

from pathlib import Path

from b3_trader.dex_shadow_score_v2_preregistration import declare_dex_shadow_score_v2_preregistration


def _ready_diagnostic(_: Path | str) -> dict:
    return {
        "ok": True,
        "status": "diagnosed_read_only",
        "score_version": 1,
        "score_name": "dex_prelisting_shadow_hypothesis_v1",
        "diagnostic_protocol": {
            "v1_reject_advisory": True,
            "v1_sign_flip_is_not_validated_v2": True,
            "retrospective_contrarian_components": ["pre_medium_momentum", "pre_short_momentum"],
            "retrospective_continuation_components": ["pre_acceleration"],
        },
        "review": {"v2_design_allowed": True},
    }


def test_build65_preregisters_forward_only_v2_and_retires_v1(tmp_path: Path) -> None:
    result = declare_dex_shadow_score_v2_preregistration(tmp_path / "unused.sqlite", diagnostic_fn=_ready_diagnostic)
    assert result["ok"] is True
    assert result["status"] == "v2_preregistered_forward_only"
    assert result["v1"]["retired"] is True
    assert result["v2"]["score_version"] == 2
    assert result["v2"]["weights_sum"] == 1.0
    assert result["v2"]["components"]["pre_short_exhaustion"]["weight"] == 0.60
    assert result["v2"]["components"]["pre_medium_exhaustion"]["weight"] == 0.40
    assert "pre_acceleration" in result["v2"]["excluded_components"]
    assert "launch_continuity" in result["v2"]["excluded_components"]
    assert result["forward_boundary"]["cutoff_utc"] == "2026-08-31T00:00:00Z"
    assert result["forward_boundary"]["all_pre_cutoff_cases_validation_excluded"] is True
    assert result["historical_rows_scored_as_v2"] is False
    assert result["retrospective_validation_claimed"] is False
    assert result["mechanical_whole_score_inversion"] is False
    assert result["review"]["build66_forward_scorer_allowed"] is True
    assert result["paper_ab_wired"] is False
    assert result["can_place_orders"] is False


def test_build65_fails_closed_without_build64_reject_advisory(tmp_path: Path) -> None:
    def blocked(_: Path | str) -> dict:
        return {
            "ok": True,
            "status": "diagnosed_read_only",
            "score_version": 1,
            "score_name": "dex_prelisting_shadow_hypothesis_v1",
            "diagnostic_protocol": {"v1_reject_advisory": False},
            "review": {"v2_design_allowed": False},
        }

    result = declare_dex_shadow_score_v2_preregistration(tmp_path / "unused.sqlite", diagnostic_fn=blocked)
    assert result["ok"] is False
    assert result["status"] == "v1_retirement_blocked"
    assert result["v1"]["retired"] is False
    assert result["review"]["build66_forward_scorer_allowed"] is False
    assert result["v2_score_wired"] is False
