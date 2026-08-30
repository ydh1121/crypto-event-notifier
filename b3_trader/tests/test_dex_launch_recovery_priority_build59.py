from __future__ import annotations

import json
from pathlib import Path

from b3_trader.dex_launch_recovery_priority import (
    BUILD59_PRIORITY_POLICY,
    DexLaunchRecoveryPriorityRunner,
)
from b3_trader.dex_shadow_remediation_runner import DexShadowRemediationRunner


def _candidate(
    case_key: str,
    asset_key: str,
    *,
    token: str,
    pool: str,
    age: float,
) -> dict:
    return {
        "case_key": case_key,
        "asset_key": asset_key,
        "network_id": "base",
        "token_address": token,
        "pool_address": pool,
        "pool_created_at": 1_800_000_000.0 - age * 86400.0,
        "domestic_open_at": 1_800_000_000.0,
        "feature_version": 1,
        "launch_status": "launch_ohlcv_unavailable",
        "pool_age_days": age,
        "shared_source_case_count": 1,
    }


def test_build59_prefers_fresh_distinct_sources(monkeypatch, tmp_path: Path) -> None:
    attempted_a = "asset-a"
    attempted_a_sibling = "asset-a-sibling"
    fresh_b = "asset-b"
    fresh_c = "asset-c"
    raw = [
        _candidate("bithumb|KRW-QUID|notice:1", attempted_a, token="0x01", pool="0xaa", age=20),
        _candidate("upbit|KRW-QUID|notice:2", attempted_a_sibling, token="0x01", pool="0xaa", age=20),
        _candidate("bithumb|KRW-RLUSD|notice:3", fresh_b, token="0x02", pool="0xbb", age=30),
        _candidate("bithumb|KRW-GRVT|notice:4", fresh_c, token="0x03", pool="0xcc", age=32),
    ]
    monkeypatch.setattr(
        DexShadowRemediationRunner,
        "_launch_candidates",
        lambda self, now, limit=100: [dict(row) for row in raw],
    )

    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "launch_attempted_at": {
                    attempted_a: 1_799_900_000.0,
                    attempted_a_sibling: 1_799_900_000.0,
                }
            }
        ),
        encoding="utf-8",
    )

    runner = object.__new__(DexLaunchRecoveryPriorityRunner)
    runner.state_path = state_path
    result = runner._launch_candidates(now=1_800_000_000.0, limit=10)

    assert len(result) == 3
    assert [row["asset_key"] for row in result[:2]] == [fresh_b, fresh_c]
    assert result[0]["source_previously_attempted"] is False
    assert result[1]["source_previously_attempted"] is False
    assert result[2]["source_previously_attempted"] is True
    assert result[2]["source_group_case_count"] == 2
    assert result[2]["source_unattempted_case_count"] == 0
    assert all(row["build59_priority_policy"] == BUILD59_PRIORITY_POLICY for row in result)


def test_build59_plan_exposes_priority_policy(monkeypatch) -> None:
    monkeypatch.setattr(
        DexShadowRemediationRunner,
        "plan",
        lambda self, now=None: {
            "status": "planned",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "launch_recovery": {
                "candidate_count": 1,
                "distinct_source_count": 1,
                "preview": [
                    {
                        "case_key": "bithumb|KRW-X|notice:1",
                        "source_previously_attempted": False,
                    }
                ],
            },
            "historical_expansion": {"official_sources_only": True, "pages_per_exchange": 1},
        },
    )
    runner = object.__new__(DexLaunchRecoveryPriorityRunner)
    plan = runner.plan(now=1_800_000_000.0)
    policy = plan["launch_recovery"]["build59_priority"]

    assert policy["policy"] == BUILD59_PRIORITY_POLICY
    assert policy["distinct_source_representatives_only"] is True
    assert policy["previously_attempted_sources_deprioritized"] is True
    assert policy["fresh_source_count_in_preview"] == 1
