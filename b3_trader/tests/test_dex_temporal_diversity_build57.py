from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from b3_trader.dex_temporal_diversity_backfill import DexTemporalDiversityBackfillRunner


class FakeCycle:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _research_case(self, row: dict, _now: float) -> dict:
        self.calls.append(str(row.get("case_key") or ""))
        return {
            "case_key": row.get("case_key"),
            "status": "complete",
            "coingecko_id": row.get("coingecko_id"),
        }


def _identity(provider_id: str, provider: str = "coingecko") -> str:
    return json.dumps({"provider": provider, "provider_id": provider_id})


def _seed(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE listing_history_cases (
          case_key TEXT PRIMARY KEY,
          domestic_exchange TEXT NOT NULL,
          domestic_market TEXT NOT NULL,
          symbol TEXT NOT NULL,
          domestic_open_at REAL NOT NULL,
          identity_json TEXT NOT NULL DEFAULT '{}',
          identity_verified INTEGER NOT NULL,
          status TEXT NOT NULL,
          updated_at REAL NOT NULL
        );
        CREATE TABLE dex_launch_case_status (
          case_key TEXT PRIMARY KEY,
          coingecko_id TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          contract_count INTEGER NOT NULL DEFAULT 0,
          accepted_pool_count INTEGER NOT NULL DEFAULT 0,
          error TEXT NOT NULL DEFAULT '',
          updated_at REAL NOT NULL
        );
        """
    )
    rows = [
        ("bithumb|KRW-OLD1|notice:1", "bithumb", "KRW-OLD1", "OLD1", 1781000000.0, _identity("new-1"), 1, "complete", 1.0),
        ("upbit|KRW-OLD2|notice:2", "upbit", "KRW-OLD2", "OLD2", 1781100000.0, _identity("new-2"), 1, "complete", 1.0),
        ("upbit|KRW-OLD1|notice:3", "upbit", "KRW-OLD1", "OLD1", 1781200000.0, _identity("new-1"), 1, "complete", 1.0),
        ("bithumb|KRW-DUP|notice:4", "bithumb", "KRW-DUP", "DUP", 1781300000.0, _identity("already-usable"), 1, "complete", 1.0),
        ("upbit|KRW-JUL|notice:5", "upbit", "KRW-JUL", "JUL", 1783300000.0, _identity("july-new"), 1, "complete", 1.0),
        ("bithumb|KRW-AUG|notice:6", "bithumb", "KRW-AUG", "AUG", 1785900000.0, _identity("aug-new"), 1, "complete", 1.0),
        ("bithumb|KRW-OTHER|notice:7", "bithumb", "KRW-OTHER", "OTHER", 1781400000.0, _identity("other-id", "other"), 1, "complete", 1.0),
        ("upbit|KRW-USEDCASE|notice:8", "upbit", "KRW-USEDCASE", "USEDCASE", 1781500000.0, _identity("unused-id"), 1, "complete", 1.0),
    ]
    conn.executemany("INSERT INTO listing_history_cases VALUES(?,?,?,?,?,?,?,?,?)", rows)
    conn.execute(
        "INSERT INTO dex_launch_case_status VALUES(?,?,?,?,?,?,?)",
        ("upbit|KRW-USEDCASE|notice:8", "unused-id", "complete", 1, 1, "", 1.0),
    )
    conn.commit()
    conn.close()


def test_build57_selects_only_old_new_unique_assets(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / "sample.sqlite3"
    _seed(db)
    fake = FakeCycle()
    remediation = {
        "ok": True,
        "readiness": {
            "shadow_readiness_advisory": False,
            "blocking_reasons": [
                "unique_asset_ratio_below_min:0.650000/0.75",
                "duplicate_event_share_above_max:0.350000/0.25",
                "temporal_concentration_above_max:0.540000/0.40",
            ],
        },
        "temporal_remediation": {
            "dominant_month": "2026-08",
            "listing_month_counts": {"2026-07": 12, "2026-08": 14},
            "per_month_case_cap_at_target": 14,
            "existing_month_additional_capacity_at_target": {"2026-07": 2, "2026-08": 0},
        },
    }
    quality = {
        "usable_case_count": 26,
        "exact_p5m_coverage": 0.9,
        "cases": [
            {"usable_for_shadow_analysis": True, "coingecko_id": "already-usable"},
        ],
    }
    audit = {
        "event_cases": {
            "usable": 26,
            "unique_assets": 17,
            "duplicate_event_cases": 9,
            "unique_asset_ratio": 17 / 26,
        }
    }
    monkeypatch.setattr("b3_trader.dex_temporal_diversity_backfill.plan_dex_shadow_remediation", lambda *_args, **_kwargs: remediation)
    monkeypatch.setattr("b3_trader.dex_temporal_diversity_backfill.evaluate_dex_launch_quality", lambda _path: quality)
    monkeypatch.setattr("b3_trader.dex_temporal_diversity_backfill.audit_dex_sample", lambda _path: audit)

    runner = DexTemporalDiversityBackfillRunner(
        db,
        state_path=tmp_path / "state.json",
        status_path=tmp_path / "status.json",
        cycle=fake,
    )
    try:
        plan = runner.plan(now=1_800_000_000.0)
        assert plan["action"] == "temporal_diversity_backfill"
        assert plan["candidate_count"] == 2
        assert [row["coingecko_id"] for row in plan["candidates"]] == ["new-1", "new-2"]
        assert all(row["listing_month"] < "2026-07" for row in plan["candidates"])
        assert plan["july_fallback_count"] == 1
        assert plan["july_fallback"][0]["coingecko_id"] == "july-new"
        assert plan["skipped_duplicate_provider_ids"] == 1
        assert plan["policy"]["july_fallback_execution_enabled"] is False

        result = runner.run_once(max_cases=2)
        assert result["processed"] == 2
        assert len(fake.calls) == 2
        assert all("JUL" not in key for key in fake.calls)
        assert all("AUG" not in key for key in fake.calls)
        assert all("DUP" not in key for key in fake.calls)
    finally:
        runner.close()


def test_build57_requests_history_when_only_july_fallback_exists(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / "sample.sqlite3"
    _seed(db)
    conn = sqlite3.connect(str(db))
    conn.execute("DELETE FROM listing_history_cases WHERE domestic_open_at < ?", (1782864000.0,))
    conn.commit()
    conn.close()

    remediation = {
        "ok": True,
        "readiness": {
            "shadow_readiness_advisory": False,
            "blocking_reasons": ["temporal_concentration_above_max:0.540000/0.40"],
        },
        "temporal_remediation": {
            "dominant_month": "2026-08",
            "listing_month_counts": {"2026-07": 12, "2026-08": 14},
            "per_month_case_cap_at_target": 14,
            "existing_month_additional_capacity_at_target": {"2026-07": 2, "2026-08": 0},
        },
    }
    monkeypatch.setattr("b3_trader.dex_temporal_diversity_backfill.plan_dex_shadow_remediation", lambda *_args, **_kwargs: remediation)
    monkeypatch.setattr(
        "b3_trader.dex_temporal_diversity_backfill.evaluate_dex_launch_quality",
        lambda _path: {"usable_case_count": 26, "exact_p5m_coverage": 0.9, "cases": []},
    )
    monkeypatch.setattr(
        "b3_trader.dex_temporal_diversity_backfill.audit_dex_sample",
        lambda _path: {"event_cases": {"usable": 26, "unique_assets": 17, "duplicate_event_cases": 9, "unique_asset_ratio": 17 / 26}},
    )
    runner = DexTemporalDiversityBackfillRunner(
        db,
        state_path=tmp_path / "state.json",
        status_path=tmp_path / "status.json",
        cycle=FakeCycle(),
    )
    try:
        plan = runner.plan(now=1_800_000_000.0)
        assert plan["candidate_count"] == 0
        assert plan["july_fallback_count"] == 1
        assert plan["action"] == "historical_expansion_needed"
    finally:
        runner.close()
