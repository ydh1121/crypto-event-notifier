from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from b3_trader.dex_temporal_backfill import DexTemporalBackfillRunner


class FakeCycle:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _research_case(self, row: dict, _now: float) -> dict:
        self.calls.append(str(row.get("case_key") or ""))
        return {
            "case_key": row.get("case_key"),
            "status": "complete",
            "coingecko_id": row.get("identity", {}).get("provider_id"),
        }


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
    verified = json.dumps({"provider": "coingecko", "provider_id": "coin-id"})
    rows = [
        ("bithumb|KRW-JUL1|notice:1", "bithumb", "KRW-JUL1", "JUL1", 1783000000.0, verified, 1, "pending_identity", 1.0),
        ("upbit|KRW-JUL2|notice:2", "upbit", "KRW-JUL2", "JUL2", 1783100000.0, verified, 1, "pending_identity", 1.0),
        ("bithumb|KRW-AUG|notice:3", "bithumb", "KRW-AUG", "AUG", 1785700000.0, verified, 1, "pending_identity", 1.0),
        ("upbit|KRW-USED|notice:4", "upbit", "KRW-USED", "USED", 1783200000.0, verified, 1, "pending_identity", 1.0),
        ("upbit|KRW-NOID|notice:5", "upbit", "KRW-NOID", "NOID", 1783300000.0, "{}", 0, "pending_identity", 1.0),
    ]
    conn.executemany("INSERT INTO listing_history_cases VALUES(?,?,?,?,?,?,?,?,?)", rows)
    conn.execute(
        "INSERT INTO dex_launch_case_status VALUES(?,?,?,?,?,?,?)",
        ("upbit|KRW-USED|notice:4", "used", "complete", 1, 1, "", 1.0),
    )
    conn.commit()
    conn.close()


def test_build56_prioritizes_verified_non_dominant_no_dex(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / "sample.sqlite3"
    _seed(db)
    fake = FakeCycle()
    remediation = {
        "ok": True,
        "readiness": {
            "shadow_readiness_advisory": False,
            "blocking_reasons": ["temporal_concentration_above_max:0.600000/0.40"],
        },
        "temporal_remediation": {
            "dominant_month": "2026-08",
            "listing_month_counts": {"2026-07": 8, "2026-08": 12},
            "per_month_case_cap_at_target": 12,
            "existing_month_additional_capacity_at_target": {"2026-07": 4, "2026-08": 0},
        },
    }
    monkeypatch.setattr("b3_trader.dex_temporal_backfill.plan_dex_shadow_remediation", lambda *_args, **_kwargs: remediation)
    monkeypatch.setattr(
        "b3_trader.dex_temporal_backfill.evaluate_dex_launch_quality",
        lambda _path: {"usable_case_count": 20, "exact_p5m_coverage": 0.9},
    )
    runner = DexTemporalBackfillRunner(
        db,
        state_path=tmp_path / "state.json",
        status_path=tmp_path / "status.json",
        cycle=fake,
    )
    try:
        plan = runner.plan(now=1_800_000_000.0)
        assert plan["action"] == "temporal_dex_backfill"
        assert plan["candidate_count"] == 2
        assert [row["listing_month"] for row in plan["candidates"]] == ["2026-07", "2026-07"]
        assert all(row["remaining_month_capacity"] == 4 for row in plan["candidates"])
        assert all(row["priority"] == "non_dominant_verified_no_dex" for row in plan["candidates"])

        result = runner.run_once(max_cases=2)
        assert result["processed"] == 2
        assert len(fake.calls) == 2
        assert all("AUG" not in key for key in fake.calls)
        assert all("USED" not in key for key in fake.calls)
    finally:
        runner.close()
