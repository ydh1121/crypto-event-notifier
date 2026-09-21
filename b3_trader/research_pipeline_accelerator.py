from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .dex_launch_backfill import DEFAULT_MAX_CASES_PER_RUN, MAX_CASES_PER_RUN, DexLaunchBackfillRunner
from .dex_launch_quality import evaluate_dex_launch_quality
from .listing_history_accelerator import ListingHistoryAccelerator
from .research_control import STATUS_PATH

DEFAULT_LISTING_CYCLES = 1
MAX_LISTING_CYCLES = 2
DEFAULT_DEX_CASES = DEFAULT_MAX_CASES_PER_RUN
MAX_DEX_CASES = MAX_CASES_PER_RUN
DEX_BACKLOG_SKIP_LISTING_THRESHOLD = 2


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _component_busy(path: Path, name: str) -> bool:
    payload = _read_json(path)
    components = payload.get("components") if isinstance(payload.get("components"), dict) else {}
    item = components.get(name) if isinstance(components.get(name), dict) else {}
    return bool(
        payload.get("running")
        and item.get("enabled")
        and str(item.get("status") or "") == "running"
    )


class ResearchPipelineAccelerator:
    """Backlog-aware manual bridge from listing-history research into DEX research.

    Existing supervisors remain the primary owners. This helper never changes
    their schedules or per-cycle limits. When enough exact DEX candidates already
    exist, it skips listing acceleration and spends the bounded budget on DEX
    research. Listing acceleration is only used to create more downstream
    candidates when the DEX backlog is small. It never wires score, PAPER
    decisions, or orders.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        status_path: Path = STATUS_PATH,
        listing: ListingHistoryAccelerator | None = None,
        dex: DexLaunchBackfillRunner | None = None,
    ) -> None:
        self.path = Path(path)
        self.status_path = Path(status_path)
        self.listing = listing or ListingHistoryAccelerator(self.path, status_path=self.status_path)
        self.dex = dex or DexLaunchBackfillRunner(self.path, status_path=self.status_path)
        self._owns_listing = listing is None
        self._owns_dex = dex is None

    def close(self) -> None:
        if self._owns_dex:
            self.dex.close()
        if self._owns_listing:
            self.listing.close()

    def _busy(self) -> dict[str, bool]:
        return {
            "listing_history_research": _component_busy(self.status_path, "listing-history-research"),
            "dex_launch_research": _component_busy(self.status_path, "dex-launch-research"),
        }

    def plan(self) -> dict[str, Any]:
        quality = evaluate_dex_launch_quality(self.path)
        listing_plan = self.listing.plan()
        dex_plan = self.dex.plan(limit=100)
        busy = self._busy()
        dex_candidates = int(dex_plan.get("candidate_count") or 0)
        listing_pending = int(listing_plan.get("pending_case_count") or 0)
        sample_ready = bool(quality.get("sample_ready"))

        if sample_ready:
            action = "sample_ready_stop"
        elif busy["listing_history_research"] or busy["dex_launch_research"]:
            action = "supervisor_busy"
        elif dex_candidates >= DEX_BACKLOG_SKIP_LISTING_THRESHOLD:
            action = "dex_backfill_only"
        elif listing_pending > 0:
            action = "listing_then_dex"
        elif dex_candidates > 0:
            action = "dex_backfill_only"
        else:
            action = "waiting_for_candidates"

        return {
            "status": "planned",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "action": action,
            "busy": busy,
            "quality": {
                "usable_case_count": int(quality.get("usable_case_count") or 0),
                "exact_p5m_case_count": int(quality.get("exact_p5m_case_count") or 0),
                "exact_p5m_coverage": float(quality.get("exact_p5m_coverage") or 0.0),
                "complete_partial_case_count": int(quality.get("complete_partial_case_count") or 0),
                "sample_ready": sample_ready,
                "blocking_reasons": list(quality.get("blocking_reasons") or []),
            },
            "listing": {
                "pending_case_count": listing_pending,
                "default_cycles": DEFAULT_LISTING_CYCLES,
                "max_cycles": MAX_LISTING_CYCLES,
            },
            "dex": {
                "candidate_count": dex_candidates,
                "default_cases": DEFAULT_DEX_CASES,
                "max_cases": MAX_DEX_CASES,
                "skip_listing_threshold": DEX_BACKLOG_SKIP_LISTING_THRESHOLD,
                "preview": list(dex_plan.get("candidates") or [])[:10],
            },
        }

    def run_once(
        self,
        *,
        listing_cycles: int = DEFAULT_LISTING_CYCLES,
        dex_cases: int = DEFAULT_DEX_CASES,
    ) -> dict[str, Any]:
        started = time.time()
        before = self.plan()
        action = str(before.get("action") or "waiting_for_candidates")
        listing_cycles = max(1, min(MAX_LISTING_CYCLES, int(listing_cycles)))
        dex_cases = max(1, min(MAX_DEX_CASES, int(dex_cases)))

        if action == "sample_ready_stop":
            return {
                "status": "sample_ready_stop",
                "paper_only": True,
                "shadow_only": True,
                "can_place_orders": False,
                "score_wired": False,
                "processed_listing": 0,
                "processed_dex": 0,
                "before": before,
                "after": before,
                "elapsed_seconds": round(time.time() - started, 3),
            }
        if action == "supervisor_busy":
            return {
                "status": "supervisor_busy",
                "paper_only": True,
                "shadow_only": True,
                "can_place_orders": False,
                "score_wired": False,
                "processed_listing": 0,
                "processed_dex": 0,
                "before": before,
                "after": before,
                "elapsed_seconds": round(time.time() - started, 3),
            }

        listing_result: dict[str, Any] | None = None
        dex_result: dict[str, Any] | None = None
        processed_listing = 0
        processed_dex = 0
        stop_reason = "budget_reached"

        if action == "listing_then_dex":
            listing_result = self.listing.run_once(cycles=listing_cycles)
            processed_listing = int(listing_result.get("processed") or 0)
            if str(listing_result.get("status") or "") == "supervisor_busy":
                stop_reason = "listing_supervisor_busy"
            elif self._busy()["dex_launch_research"] or self._busy()["listing_history_research"]:
                stop_reason = "supervisor_became_busy"
            else:
                refreshed_dex = self.dex.plan(limit=100)
                if int(refreshed_dex.get("candidate_count") or 0) > 0:
                    dex_result = self.dex.run_once(max_cases=dex_cases)
                    processed_dex = int(dex_result.get("processed") or 0)
                else:
                    stop_reason = "no_dex_candidates_after_listing"
        elif action == "dex_backfill_only":
            if self._busy()["dex_launch_research"] or self._busy()["listing_history_research"]:
                stop_reason = "supervisor_became_busy"
            else:
                dex_result = self.dex.run_once(max_cases=dex_cases)
                processed_dex = int(dex_result.get("processed") or 0)
        else:
            stop_reason = "waiting_for_candidates"

        after = self.plan()
        if bool(after.get("quality", {}).get("sample_ready")):
            stop_reason = "sample_ready"

        return {
            "status": "accelerated" if (processed_listing + processed_dex) > 0 else stop_reason,
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "selected_action": action,
            "listing_cycles_budget": listing_cycles,
            "dex_cases_budget": dex_cases,
            "processed_listing": processed_listing,
            "processed_dex": processed_dex,
            "stop_reason": stop_reason,
            "listing_result": listing_result,
            "dex_result": dex_result,
            "before": before,
            "after": after,
            "elapsed_seconds": round(time.time() - started, 3),
        }
