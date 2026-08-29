from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .dex_launch_backfill import (
    DEFAULT_MAX_CASES_PER_RUN,
    MAX_CASES_PER_RUN,
    DexLaunchBackfillRunner,
)
from .dex_launch_quality import evaluate_dex_launch_quality
from .dex_sample_audit import audit_dex_sample
from .research_control import STATUS_PATH


PRIORITY_NEW_UNIQUE = 0
PRIORITY_UNKNOWN_IDENTITY = 1
PRIORITY_DUPLICATE_EVENT = 2
PRIORITY_PARTIAL_RETRY = 3


def _verified_listing_coingecko_id(path: Path, case_key: str) -> str:
    if not path.exists():
        return ""
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "listing_history_cases" not in tables:
            return ""
        row = conn.execute(
            "SELECT identity_json,identity_verified FROM listing_history_cases WHERE case_key=? LIMIT 1",
            (str(case_key),),
        ).fetchone()
        if row is None or not bool(row["identity_verified"]):
            return ""
        try:
            identity = json.loads(str(row["identity_json"] or "{}"))
        except json.JSONDecodeError:
            return ""
        if not isinstance(identity, dict):
            return ""
        provider = str(identity.get("provider") or "").strip().lower()
        provider_id = str(identity.get("provider_id") or "").strip()
        return provider_id if provider == "coingecko" and provider_id else ""
    finally:
        conn.close()


def _usable_asset_ids(quality: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for row in quality.get("cases") or []:
        if not isinstance(row, dict) or not bool(row.get("usable_for_shadow_analysis")):
            continue
        coin_id = str(row.get("coingecko_id") or "").strip()
        if coin_id:
            result.add(coin_id)
    return result


def _candidate_priority(candidate: dict[str, Any], *, usable_asset_ids: set[str]) -> tuple[int, str]:
    reason = str(candidate.get("reason") or "")
    coin_id = str(candidate.get("coingecko_id") or "").strip()
    if reason == "complete_partial_retry":
        return PRIORITY_PARTIAL_RETRY, "partial_completion_retry"
    if coin_id and coin_id not in usable_asset_ids:
        return PRIORITY_NEW_UNIQUE, "new_unique_asset"
    if not coin_id:
        return PRIORITY_UNKNOWN_IDENTITY, "identity_unknown_unique_potential"
    return PRIORITY_DUPLICATE_EVENT, "duplicate_asset_event"


class DexDiversityBackfillRunner(DexLaunchBackfillRunner):
    """Build51 diversity-aware ordering for the existing bounded DEX backfill.

    The Build46 execution path remains the owner of network work, cooldowns,
    stored-complete preservation, and the hard two-case cap. Build51 only sorts
    candidates so new CoinGecko assets are researched before duplicate exchange
    events and before complete_partial retries. It never changes Build45 quality
    thresholds and never wires DEX data into score, PAPER decisions, or orders.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        status_path: Path = STATUS_PATH,
        **kwargs: Any,
    ) -> None:
        super().__init__(path, status_path=status_path, **kwargs)

    def plan(self, *, limit: int = 20, now: float | None = None) -> dict[str, Any]:
        base = super().plan(limit=100, now=now)
        quality = evaluate_dex_launch_quality(self.path)
        audit = audit_dex_sample(self.path)
        usable_ids = _usable_asset_ids(quality)

        ranked: list[dict[str, Any]] = []
        for index, source in enumerate(base.get("candidates") or []):
            if not isinstance(source, dict):
                continue
            candidate = dict(source)
            if not str(candidate.get("coingecko_id") or "").strip():
                candidate["coingecko_id"] = _verified_listing_coingecko_id(
                    self.path,
                    str(candidate.get("case_key") or ""),
                )
            priority, diversity_reason = _candidate_priority(candidate, usable_asset_ids=usable_ids)
            candidate["diversity_priority"] = priority
            candidate["diversity_reason"] = diversity_reason
            candidate["original_order"] = index
            ranked.append(candidate)

        ranked.sort(
            key=lambda row: (
                int(row.get("diversity_priority") or 0),
                int(row.get("original_order") or 0),
            )
        )
        preview_limit = max(1, min(100, int(limit)))
        event_cases = audit.get("event_cases") if isinstance(audit.get("event_cases"), dict) else {}
        coverage = audit.get("coverage") if isinstance(audit.get("coverage"), dict) else {}
        counts: dict[str, int] = {}
        for row in ranked:
            key = str(row.get("diversity_reason") or "unknown")
            counts[key] = counts.get(key, 0) + 1

        return {
            **base,
            "mode": "diversity_aware",
            "candidate_count": len(ranked),
            "candidates": ranked[:preview_limit],
            "priority_counts": dict(sorted(counts.items())),
            "sample_composition": {
                "usable_event_cases": int(event_cases.get("usable") or 0),
                "unique_assets": int(event_cases.get("unique_assets") or 0),
                "duplicate_event_cases": int(event_cases.get("duplicate_event_cases") or 0),
                "unique_asset_ratio": float(event_cases.get("unique_asset_ratio") or 0.0),
                "complete_partial_ratio": float(coverage.get("complete_partial_ratio") or 0.0),
                "exact_p5m_coverage": float(coverage.get("exact_p5m_coverage") or 0.0),
                "launch_feature_coverage": float(coverage.get("launch_feature_coverage") or 0.0),
            },
            "policy": {
                "new_unique_asset_first": True,
                "unknown_identity_second": True,
                "duplicate_event_after_unique": True,
                "partial_retry_last": True,
                "changes_build45_thresholds": False,
            },
        }

    def run_once(self, *, max_cases: int = DEFAULT_MAX_CASES_PER_RUN) -> dict[str, Any]:
        before_audit = audit_dex_sample(self.path)
        if bool(before_audit.get("sample_ready_build45")):
            return {
                "status": "sample_ready_stop",
                "paper_only": True,
                "shadow_only": True,
                "can_place_orders": False,
                "score_wired": False,
                "processed": 0,
                "max_cases_per_run": MAX_CASES_PER_RUN,
                "before_audit": before_audit,
                "after_audit": before_audit,
            }

        plan = self.plan(limit=100)
        selected = list(plan.get("candidates") or [])[: max(1, min(MAX_CASES_PER_RUN, int(max_cases)))]
        result = super().run_once(max_cases=max_cases)
        after_audit = audit_dex_sample(self.path)
        before_events = before_audit.get("event_cases") if isinstance(before_audit.get("event_cases"), dict) else {}
        after_events = after_audit.get("event_cases") if isinstance(after_audit.get("event_cases"), dict) else {}
        return {
            **result,
            "diversity_mode": True,
            "selected_candidates": selected,
            "before_unique_assets": int(before_events.get("unique_assets") or 0),
            "after_unique_assets": int(after_events.get("unique_assets") or 0),
            "before_usable_event_cases": int(before_events.get("usable") or 0),
            "after_usable_event_cases": int(after_events.get("usable") or 0),
            "before_audit": before_audit,
            "after_audit": after_audit,
        }
