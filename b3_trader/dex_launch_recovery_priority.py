from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from pathlib import Path
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
    3. recover source-level attempt history from attempted asset keys so a sibling
       event case cannot make the same exact source look fresh after cooldown
       filtering removes the previously attempted asset from Build55 candidates;
    4. keep previously attempted sources available only after fresh sources.

    This prevents one known-unavailable shared source from consuming bounded
    launch-recovery slots repeatedly while remaining fully retryable later.
    """

    def _attempted_source_keys(
        self,
        attempts: dict[str, Any],
    ) -> set[tuple[str, str, str, float]]:
        """Map Build55 asset-key attempts back to exact selected-primary sources."""
        asset_keys = sorted({str(key) for key in attempts if str(key)})
        path_value = getattr(self, "path", None)
        if not asset_keys or path_value is None:
            return set()

        path = Path(path_value)
        if not path.exists():
            return set()

        source_keys: set[tuple[str, str, str, float]] = set()
        conn = sqlite3.connect(str(path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            for start in range(0, len(asset_keys), 500):
                chunk = asset_keys[start : start + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"""
                    SELECT a.asset_key,a.network_id,a.token_address,
                           p.pool_address,p.pool_created_at
                    FROM dex_launch_assets a
                    JOIN dex_launch_pools p ON p.asset_key=a.asset_key
                    WHERE p.selected_primary=1
                      AND a.asset_key IN ({placeholders})
                    """,
                    tuple(chunk),
                ).fetchall()
                for row in rows:
                    source_keys.add(_source_key(dict(row)))
        except sqlite3.Error:
            return set()
        finally:
            conn.close()
        return source_keys

    def _launch_candidates(self, *, now: float, limit: int = 100) -> list[dict[str, Any]]:
        raw = super()._launch_candidates(now=now, limit=100)
        if not raw:
            return []

        state = _read_json(self.state_path)
        attempts = state.get("launch_attempted_at") if isinstance(state.get("launch_attempted_at"), dict) else {}
        attempted_source_keys = self._attempted_source_keys(attempts)

        grouped: dict[tuple[str, str, str, float], list[dict[str, Any]]] = defaultdict(list)
        for item in raw:
            candidate = dict(item)
            asset_key = str(candidate.get("asset_key") or "")
            source_key = _source_key(candidate)
            previously_attempted = bool(asset_key and asset_key in attempts)
            source_previously_attempted = bool(
                previously_attempted or source_key in attempted_source_keys
            )
            candidate["previously_attempted"] = previously_attempted
            candidate["source_previously_attempted"] = source_previously_attempted
            candidate["source_attempted_via_sibling"] = bool(
                source_previously_attempted and not previously_attempted
            )
            grouped[source_key].append(candidate)

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
            source_previously_attempted = any(
                bool(row.get("source_previously_attempted")) for row in members
            )
            representative["source_group_case_count"] = len(members)
            representative["source_previously_attempted"] = source_previously_attempted
            representative["source_attempted_via_sibling"] = any(
                bool(row.get("source_attempted_via_sibling")) for row in members
            )
            representative["source_unattempted_case_count"] = (
                0
                if source_previously_attempted
                else sum(1 for row in members if not bool(row.get("previously_attempted")))
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
            "sibling_source_attempts_recovered": True,
            "fresh_source_count_in_preview": sum(
                1
                for row in preview
                if isinstance(row, dict) and not bool(row.get("source_previously_attempted"))
            ),
        }
        plan["launch_recovery"] = launch
        return plan
