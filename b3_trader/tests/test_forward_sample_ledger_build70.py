from __future__ import annotations

from pathlib import Path

from b3_trader.forward_sample_ledger import audit_forward_sample_ledger


def _row(case_key, asset, *, p1h=1.0, p6h=2.0, p24h=3.0, confidence=1.0):
    return {
        "case_key": case_key,
        "coingecko_id": asset,
        "confidence": confidence,
        "evaluation_only_outcomes": {
            "post_listing_returns_pct": {
                "p1h": p1h,
                "p6h": p6h,
                "p24h": p24h,
            }
        },
    }


def test_empty_forward_sample_is_not_ready(tmp_path: Path):
    result = audit_forward_sample_ledger(
        tmp_path / "db.sqlite3",
        score_audit_fn=lambda path: {
            "ok": True,
            "score_version": 2,
            "score_name": "v2",
            "historical_rows_scored_as_v2": False,
            "case_scores": [],
        },
    )
    assert result["ok"] is True
    assert result["status"] == "accumulating_forward_sample"
    assert result["event_count"] == 0
    assert result["unique_asset_count"] == 0
    assert result["remaining"]["event_labels_per_core"]["p1h"] == 30
    assert result["remaining"]["asset_labels_per_core"]["p24h"] == 20
    assert result["review"]["build71_forward_validation_allowed"] is False


def test_duplicate_events_dedup_assets(tmp_path: Path):
    rows = [
        _row("bithumb|KRW-A|1", "asset-a"),
        _row("upbit|KRW-A|2", "asset-a"),
        _row("bithumb|KRW-B|3", "asset-b", p24h=None),
    ]
    result = audit_forward_sample_ledger(
        tmp_path / "db.sqlite3",
        score_audit_fn=lambda path: {
            "ok": True,
            "score_version": 2,
            "score_name": "v2",
            "historical_rows_scored_as_v2": False,
            "case_scores": rows,
        },
    )
    assert result["event_count"] == 3
    assert result["unique_asset_count"] == 2
    assert result["label_coverage"]["event"]["p24h"] == 2
    assert result["label_coverage"]["asset_dedup"]["p24h"] == 1


def test_ready_only_when_all_core_label_minimums_pass(tmp_path: Path):
    rows = []
    for idx in range(30):
        rows.append(_row(f"case-{idx}", f"asset-{idx % 20}"))
    result = audit_forward_sample_ledger(
        tmp_path / "db.sqlite3",
        score_audit_fn=lambda path: {
            "ok": True,
            "score_version": 2,
            "score_name": "v2",
            "historical_rows_scored_as_v2": False,
            "case_scores": rows,
        },
    )
    assert result["readiness"]["sample_size_ready"] is True
    assert result["status"] == "forward_sample_ready_for_validation"
    assert result["review"]["build71_forward_validation_allowed"] is True


def test_historical_contamination_fails_closed(tmp_path: Path):
    result = audit_forward_sample_ledger(
        tmp_path / "db.sqlite3",
        score_audit_fn=lambda path: {
            "ok": True,
            "historical_rows_scored_as_v2": True,
            "case_scores": [_row("old", "old")],
        },
    )
    assert result["ok"] is False
    assert result["status"] == "historical_contamination_blocked"
    assert result["review"]["build71_forward_validation_allowed"] is False
