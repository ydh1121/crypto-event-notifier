from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .dex_launch_quality import evaluate_dex_launch_quality
from .dex_launch_research_cycle import DexLaunchResearchCycle
from .dex_shadow_remediation_plan import plan_dex_shadow_remediation
from .research_control import STATUS_PATH, atomic_json

STATE_PATH = Path("b3_trader/data/research-platform/dex-temporal-backfill-build56-state.json")
DEFAULT_MAX_CASES_PER_RUN = 2
MAX_CASES_PER_RUN = 2
RETRY_AFTER_SECONDS = 6 * 3600


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _month_bucket(ts: Any) -> str:
    try:
        value = float(ts or 0.0)
    except (TypeError, ValueError):
        return "unknown"
    if value <= 0:
        return "unknown"
    return time.strftime("%Y-%m", time.gmtime(value))


def _component_busy(path: Path, name: str) -> bool:
    payload = _read_json(path)
    components = payload.get("components") if isinstance(payload.get("components"), dict) else {}
    item = components.get(name) if isinstance(components.get(name), dict) else {}
    return bool(payload.get("running") and item.get("enabled") and str(item.get("status") or "") == "running")


class DexTemporalBackfillRunner:
    """Bounded DEX research for verified non-dominant historical listing cases.

    This runner exists only to remediate Build53 temporal concentration. It uses
    exact verified listing identities, never ticker-only matching, and delegates
    actual DEX research to the existing Build42 research cycle. It does not wire
    score, PAPER decisions, or orders.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        state_path: Path = STATE_PATH,
        status_path: Path = STATUS_PATH,
        cycle: DexLaunchResearchCycle | None = None,
    ) -> None:
        self.path = Path(path)
        self.state_path = Path(state_path)
        self.status_path = Path(status_path)
        self.cycle = cycle or DexLaunchResearchCycle(self.path)
        self._owns_cycle = cycle is None

    def close(self) -> None:
        if self._owns_cycle:
            self.cycle.close()

    def _busy(self) -> dict[str, bool]:
        return {
            "listing_history_research": _component_busy(self.status_path, "listing-history-research"),
            "dex_launch_research": _component_busy(self.status_path, "dex-launch-research"),
        }

    def _attempts(self) -> dict[str, float]:
        state = _read_json(self.state_path)
        raw = state.get("attempts") if isinstance(state.get("attempts"), dict) else {}
        result: dict[str, float] = {}
        for key, value in raw.items():
            try:
                result[str(key)] = float(value or 0.0)
            except (TypeError, ValueError):
                continue
        return result

    def _listing_rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            tables = {str(row["name"]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "listing_history_cases" not in tables:
                return []
            has_dex = "dex_launch_case_status" in tables
            join = "LEFT JOIN dex_launch_case_status d ON d.case_key=c.case_key" if has_dex else ""
            no_dex = "AND d.case_key IS NULL" if has_dex else ""
            rows = conn.execute(
                f"""
                SELECT c.case_key,c.domestic_exchange,c.domestic_market,c.symbol,c.domestic_open_at,
                       c.identity_json,c.identity_verified,c.status AS listing_status
                FROM listing_history_cases c
                {join}
                WHERE c.identity_verified=1
                  AND c.status NOT IN ('rejected_identity','rejected_notice')
                  {no_dex}
                ORDER BY c.domestic_open_at ASC,c.case_key ASC
                """
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                try:
                    identity = json.loads(str(item.pop("identity_json") or "{}"))
                except json.JSONDecodeError:
                    identity = {}
                item["identity"] = identity if isinstance(identity, dict) else {}
                result.append(item)
            return result
        finally:
            conn.close()

    def plan(self, *, now: float | None = None, limit: int = 20) -> dict[str, Any]:
        current_now = float(now if now is not None else time.time())
        remediation = plan_dex_shadow_remediation(self.path, now=current_now)
        temporal = remediation.get("temporal_remediation") if isinstance(remediation.get("temporal_remediation"), dict) else {}
        dominant_month = str(temporal.get("dominant_month") or "unknown")
        month_counts = {str(k): int(v) for k, v in (temporal.get("listing_month_counts") or {}).items()}
        month_capacity = {str(k): int(v) for k, v in (temporal.get("existing_month_additional_capacity_at_target") or {}).items()}
        per_month_cap = int(temporal.get("per_month_case_cap_at_target") or 0)
        attempts = self._attempts()
        cutoff = current_now - RETRY_AFTER_SECONDS

        candidates: list[dict[str, Any]] = []
        for row in self._listing_rows():
            case_key = str(row.get("case_key") or "")
            month = _month_bucket(row.get("domestic_open_at"))
            if not case_key or month in {"unknown", dominant_month}:
                continue
            current_count = int(month_counts.get(month) or 0)
            capacity = int(month_capacity.get(month, max(0, per_month_cap - current_count)))
            if capacity <= 0 or attempts.get(case_key, 0.0) > cutoff:
                continue
            identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
            if not identity or not str(identity.get("provider_id") or ""):
                continue
            candidates.append(
                {
                    **row,
                    "listing_month": month,
                    "current_month_usable_count": current_count,
                    "remaining_month_capacity": capacity,
                    "priority": "non_dominant_verified_no_dex",
                }
            )

        candidates.sort(
            key=lambda row: (
                int(row.get("current_month_usable_count") or 0),
                float(row.get("domestic_open_at") or 0.0),
                str(row.get("case_key") or ""),
            )
        )
        busy = self._busy()
        blockers = list(remediation.get("readiness", {}).get("blocking_reasons") or [])
        temporal_blocked = any(str(reason).startswith("temporal_concentration_above_max:") for reason in blockers)
        if remediation.get("readiness", {}).get("shadow_readiness_advisory"):
            action = "readiness_reached_stop"
        elif busy["listing_history_research"] or busy["dex_launch_research"]:
            action = "supervisor_busy"
        elif temporal_blocked and candidates:
            action = "temporal_dex_backfill"
        elif temporal_blocked:
            action = "historical_expansion_needed"
        else:
            action = "temporal_gate_clear"

        return {
            "status": "planned",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "action": action,
            "busy": busy,
            "dominant_month": dominant_month,
            "per_month_cap_at_target": per_month_cap,
            "month_usable_counts": month_counts,
            "max_cases_per_run": MAX_CASES_PER_RUN,
            "retry_after_seconds": RETRY_AFTER_SECONDS,
            "candidate_count": len(candidates),
            "candidates": candidates[: max(1, min(100, int(limit)))],
            "remediation": remediation,
        }

    def run_once(self, *, max_cases: int = DEFAULT_MAX_CASES_PER_RUN) -> dict[str, Any]:
        started = time.time()
        before_quality = evaluate_dex_launch_quality(self.path)
        before = self.plan(now=started, limit=100)
        action = str(before.get("action") or "historical_expansion_needed")
        if action != "temporal_dex_backfill":
            return {
                "status": action,
                "paper_only": True,
                "shadow_only": True,
                "can_place_orders": False,
                "score_wired": False,
                "processed": 0,
                "before": before,
                "after": before,
                "elapsed_seconds": round(time.time() - started, 3),
            }

        limit = max(1, min(MAX_CASES_PER_RUN, int(max_cases)))
        picked = list(before.get("candidates") or [])[:limit]
        attempts = self._attempts()
        results: list[dict[str, Any]] = []
        for candidate in picked:
            if self._busy()["listing_history_research"] or self._busy()["dex_launch_research"]:
                break
            result = self.cycle._research_case(candidate, time.time())
            case_key = str(candidate.get("case_key") or "")
            attempts[case_key] = time.time()
            results.append({**result, "listing_month": candidate.get("listing_month"), "temporal_priority": True})

        atomic_json(
            self.state_path,
            {"version": 1, "updated_at": time.time(), "attempts": attempts, "last_results": results},
        )
        after_quality = evaluate_dex_launch_quality(self.path)
        after = self.plan(now=time.time(), limit=100)
        return {
            "status": "backfilled" if results else "supervisor_became_busy",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "processed": len(results),
            "before_usable_case_count": int(before_quality.get("usable_case_count") or 0),
            "after_usable_case_count": int(after_quality.get("usable_case_count") or 0),
            "after_exact_p5m_coverage": float(after_quality.get("exact_p5m_coverage") or 0.0),
            "results": results,
            "before": before,
            "after": after,
            "elapsed_seconds": round(time.time() - started, 3),
        }
