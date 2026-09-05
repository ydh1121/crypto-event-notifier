from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .dex_launch_quality import evaluate_dex_launch_quality
from .dex_launch_research_cycle import DexLaunchResearchCycle
from .research_control import STATUS_PATH, atomic_json

STATE_PATH = Path("b3_trader/data/research-platform/dex-launch-backfill-state.json")
DEFAULT_MAX_CASES_PER_RUN = 1
MAX_CASES_PER_RUN = 2
BACKFILL_RETRY_AFTER_SECONDS = 6 * 3600


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _listing_case(path: Path, case_key: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "listing_history_cases" not in tables:
            return None
        row = conn.execute(
            """SELECT case_key,domestic_exchange,domestic_market,symbol,domestic_open_at,
                      identity_json,identity_verified,status AS listing_status
               FROM listing_history_cases WHERE case_key=? LIMIT 1""",
            (str(case_key),),
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            identity = json.loads(str(item.pop("identity_json") or "{}"))
        except json.JSONDecodeError:
            identity = {}
        item["identity"] = identity if isinstance(identity, dict) else {}
        return item
    finally:
        conn.close()


def _case_status(path: Path, case_key: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "dex_launch_case_status" not in tables:
            return None
        row = conn.execute(
            """SELECT case_key,coingecko_id,status,contract_count,accepted_pool_count,error,updated_at
               FROM dex_launch_case_status WHERE case_key=? LIMIT 1""",
            (str(case_key),),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def _supervisor_busy(path: Path = STATUS_PATH) -> bool:
    payload = _read_json(path)
    components = payload.get("components") if isinstance(payload.get("components"), dict) else {}
    dex = components.get("dex-launch-research") if isinstance(components.get("dex-launch-research"), dict) else {}
    return bool(payload.get("running") and dex.get("enabled") and str(dex.get("status") or "") == "running")


class DexLaunchBackfillRunner:
    """Bounded exact-case recovery for existing DEX research samples.

    The normal supervisor remains the primary owner. This runner only accelerates
    already-eligible cases and retries derived complete_partial cases that the
    normal stored-status selector would otherwise never revisit. It is never
    connected to score, PAPER decision, or order paths.
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

    def _recent_attempts(self) -> dict[str, float]:
        state = _read_json(self.state_path)
        raw = state.get("attempts") if isinstance(state.get("attempts"), dict) else {}
        result: dict[str, float] = {}
        for key, value in raw.items():
            try:
                result[str(key)] = float(value or 0.0)
            except (TypeError, ValueError):
                continue
        return result

    def plan(self, *, limit: int = 20, now: float | None = None) -> dict[str, Any]:
        current = float(now or time.time())
        cooldown_cutoff = current - BACKFILL_RETRY_AFTER_SECONDS
        attempts = self._recent_attempts()
        quality = evaluate_dex_launch_quality(self.path)
        quality_rows = quality.get("cases") if isinstance(quality.get("cases"), list) else []
        quality_by_key = {
            str(row.get("case_key")): row
            for row in quality_rows
            if isinstance(row, dict) and row.get("case_key")
        }

        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        # First use the exact same verified/retryable selector as the normal DEX
        # cycle. This is the only path that can increase usable case count.
        for row in self.cycle.store.listing_cases(limit=500):
            key = str(row.get("case_key") or "")
            if not key or key in seen or attempts.get(key, 0.0) > cooldown_cutoff:
                continue
            q = quality_by_key.get(key) or {}
            derived = str(q.get("derived_completion") or "unresearched")
            if derived == "complete":
                continue
            seen.add(key)
            candidates.append(
                {
                    "case_key": key,
                    "market": row.get("domestic_market"),
                    "coingecko_id": q.get("coingecko_id") or "",
                    "reason": "eligible_unresearched_or_retryable",
                    "derived_completion": derived,
                    "stored_status": q.get("stored_status") or row.get("dex_status") or "",
                }
            )

        # Stored complete cases are terminal to the normal selector, but Build45
        # may derive complete_partial when one of up to two exact contracts lacks
        # a usable primary-pool feature. Retry those only after standard backlog.
        for row in quality_rows:
            if not isinstance(row, dict) or row.get("derived_completion") != "complete_partial":
                continue
            key = str(row.get("case_key") or "")
            if not key or key in seen or attempts.get(key, 0.0) > cooldown_cutoff:
                continue
            listing = _listing_case(self.path, key)
            if not listing or not bool(listing.get("identity_verified")):
                continue
            seen.add(key)
            candidates.append(
                {
                    "case_key": key,
                    "market": listing.get("domestic_market"),
                    "coingecko_id": row.get("coingecko_id") or "",
                    "reason": "complete_partial_retry",
                    "derived_completion": "complete_partial",
                    "stored_status": row.get("stored_status") or "",
                    "expected_research_assets": int(row.get("expected_research_assets") or 0),
                    "usable_feature_asset_count": int(row.get("usable_feature_asset_count") or 0),
                }
            )

        return {
            "status": "planned",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "max_cases_per_run": MAX_CASES_PER_RUN,
            "retry_after_seconds": BACKFILL_RETRY_AFTER_SECONDS,
            "supervisor_busy": _supervisor_busy(self.status_path),
            "candidate_count": len(candidates),
            "candidates": candidates[: max(1, min(100, int(limit)))],
            "quality": {
                "usable_case_count": int(quality.get("usable_case_count") or 0),
                "exact_p5m_coverage": float(quality.get("exact_p5m_coverage") or 0.0),
                "complete_partial_case_count": int(quality.get("complete_partial_case_count") or 0),
                "sample_ready": bool(quality.get("sample_ready")),
            },
        }

    def _restore_complete(self, before: dict[str, Any] | None) -> None:
        if not before or str(before.get("status") or "") != "complete":
            return
        self.cycle.store.upsert_case_status(
            str(before.get("case_key") or ""),
            coingecko_id=str(before.get("coingecko_id") or ""),
            status="complete",
            contract_count=int(before.get("contract_count") or 0),
            accepted_pool_count=int(before.get("accepted_pool_count") or 0),
            error=str(before.get("error") or ""),
        )

    def run_once(self, *, max_cases: int = DEFAULT_MAX_CASES_PER_RUN) -> dict[str, Any]:
        started = time.time()
        before_quality = evaluate_dex_launch_quality(self.path)
        plan = self.plan(limit=100, now=started)
        if plan.get("supervisor_busy"):
            return {
                "status": "supervisor_busy",
                "paper_only": True,
                "shadow_only": True,
                "can_place_orders": False,
                "processed": 0,
                "candidate_count": int(plan.get("candidate_count") or 0),
                "before_usable_case_count": int(before_quality.get("usable_case_count") or 0),
                "elapsed_seconds": round(time.time() - started, 3),
            }

        limit = max(1, min(MAX_CASES_PER_RUN, int(max_cases)))
        picked = list(plan.get("candidates") or [])[:limit]
        results: list[dict[str, Any]] = []
        attempts = self._recent_attempts()

        for candidate in picked:
            key = str(candidate.get("case_key") or "")
            listing = _listing_case(self.path, key)
            if not listing:
                results.append({"case_key": key, "status": "listing_case_missing", "reason": candidate.get("reason")})
                attempts[key] = time.time()
                continue
            before_status = _case_status(self.path, key)
            result = self.cycle._research_case(listing, time.time())
            if (
                str(candidate.get("reason") or "") == "complete_partial_retry"
                and before_status
                and str(before_status.get("status") or "") == "complete"
                and str(result.get("status") or "") != "complete"
            ):
                self._restore_complete(before_status)
                result = {**result, "stored_complete_preserved": True}
            attempts[key] = time.time()
            results.append({**result, "backfill_reason": candidate.get("reason")})

        state = {
            "version": 1,
            "updated_at": time.time(),
            "attempts": attempts,
            "last_results": results,
        }
        atomic_json(self.state_path, state)
        after_quality = evaluate_dex_launch_quality(self.path)
        return {
            "status": "backfilled" if picked else "waiting_for_candidates",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "processed": len(picked),
            "candidate_count": int(plan.get("candidate_count") or 0),
            "before_usable_case_count": int(before_quality.get("usable_case_count") or 0),
            "after_usable_case_count": int(after_quality.get("usable_case_count") or 0),
            "before_complete_partial": int(before_quality.get("complete_partial_case_count") or 0),
            "after_complete_partial": int(after_quality.get("complete_partial_case_count") or 0),
            "after_exact_p5m_coverage": float(after_quality.get("exact_p5m_coverage") or 0.0),
            "sample_ready": bool(after_quality.get("sample_ready")),
            "results": results,
            "elapsed_seconds": round(time.time() - started, 3),
        }
