from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from .dex_shadow_remediation_runner import (
    DexShadowRemediationRunner,
    _read_json,
    _source_key,
)


BUILD59_PRIORITY_POLICY = "unattempted_distinct_source_first"


class DexLaunchRecoveryPriorityRunner(DexShadowRemediationRunner):
    """Build59 launch-only prioritization over the bounded Build55 runner.

    The underlying Build55 safety limits, cooldown, selected-primary requirement,
    feature preservation, supervisor guard, and PAPER/shadow-only behavior remain
    unchanged. Build59 only changes candidate ordering/selection:

    1. collapse sibling event cases that point at the same exact launch source to
       one representative candidate per run plan;
    2. prefer exact sources that have never been attempted by Build55 state;
    3. keep previously attempted sources available only after fresh sources.

    This prevents one known-unavailable shared source from consuming both bounded
    launch-recovery slots while remaining fail-closed and fully retryable later.
    """

    def _launch_candidates(self, *, now: float, limit: int = 100) -> list[dict[str, Any]]:
        raw = super()._launch_candidates(now=now, limit=100)
        if not raw:
            return []

        state = _read_json(self.state_path)
        attempts = state.get("launch_attempted_at") if isinstance(state.get("launch_attempted_at"), dict) else {}

        grouped: dict[tuple[str, str, str, float], list[dict[str, Any]]] = defaultdict(list)
        for item in raw:
            candidate = dict(item)
            asset_key = str(candidate.get("asset_key") or "")
            candidate["previously_attempted"] = bool(asset_key and asset_key in attempts)
            grouped[_source_key(candidate)].append(candidate)

        representatives: list[dict[str, Any]] = []
        for members in grouped.values():
            members.sort(
                key=lambda row: (
                    bool(row.get("previously_attempted")),
                    float(row.get("pool_age_days") or math.inf),
                    str(row.get("case_key") or ""),
                )
            )
            representative = dict(members[0])
            representative["source_group_case_count"] = len(members)
            representative["source_previously_attempted"] = any(
                bool(row.get("previously_attempted")) for row in members
            )
            representative["source_unattempted_case_count"] = sum(
                1 for row in members if not bool(row.get("previously_attempted"))
            )
            representatives.append(representative)

        representatives.sort(
            key=lambda row: (
                bool(row.get("source_previously_attempted")),
                float(row.get("pool_age_days") or math.inf),
                str(row.get("case_key") or ""),
            )
        )
        for index, candidate in enumerate(representatives, start=1):
            candidate["build59_priority_rank"] = index
            candidate["build59_priority_policy"] = BUILD59_PRIORITY_POLICY

        return representatives[: max(1, min(100, int(limit)))]

    def plan(self, *, now: float | None = None) -> dict[str, Any]:
        plan = super().plan(now=now)
        launch = plan.get("launch_recovery") if isinstance(plan.get("launch_recovery"), dict) else {}
        preview = launch.get("preview") if isinstance(launch.get("preview"), list) else []
        launch["build59_priority"] = {
            "policy": BUILD59_PRIORITY_POLICY,
            "distinct_source_representatives_only": True,
            "previously_attempted_sources_deprioritized": True,
            "fresh_source_count_in_preview": sum(
                1
                for row in preview
                if isinstance(row, dict) and not bool(row.get("source_previously_attempted"))
            ),
        }
        plan["launch_recovery"] = launch
        return plan
