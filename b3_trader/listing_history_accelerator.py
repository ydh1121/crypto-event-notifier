from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from .auto_demo_v2 import DB_PATH
from .listing_history_collector import FEATURE_VERSION
from .listing_history_research_cycle import MAX_CASES_PER_RUN, ListingHistoryResearchCycle
from .research_control import STATUS_PATH

DEFAULT_CYCLES_PER_RUN = 2
MAX_CYCLES_PER_RUN = 4
INTER_CYCLE_SECONDS = 15.0


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _supervisor_busy(path: Path = STATUS_PATH) -> bool:
    payload = _read_json(path)
    components = payload.get("components") if isinstance(payload.get("components"), dict) else {}
    item = components.get("listing-history-research") if isinstance(components.get("listing-history-research"), dict) else {}
    return bool(
        payload.get("running")
        and item.get("enabled")
        and str(item.get("status") or "") == "running"
    )


class ListingHistoryAccelerator:
    """Bounded manual accelerator for the existing listing-history research cycle.

    The normal ResearchSupervisor remains the primary owner. This helper does not
    change the existing 3-case cycle or its 900-second schedule; it only invokes
    that same cycle sequentially in a small bounded batch when the supervisor is
    idle. It is never connected to DEX score, PAPER decisions, or order paths.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        status_path: Path = STATUS_PATH,
        cycle: ListingHistoryResearchCycle | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.path = Path(path)
        self.status_path = Path(status_path)
        self.cycle = cycle or ListingHistoryResearchCycle(self.path)
        self.sleeper = sleeper
        self._owns_cycle = cycle is None

    def close(self) -> None:
        if self._owns_cycle:
            self.cycle.close()

    def _pending(self) -> list[dict[str, Any]]:
        return self.cycle.store.pending_cases(limit=500, required_feature_version=FEATURE_VERSION)

    def plan(self, *, preview_limit: int = 12) -> dict[str, Any]:
        pending = self._pending()
        preview = []
        for row in pending[: max(1, min(50, int(preview_limit)))]:
            preview.append(
                {
                    "case_key": str(row.get("case_key") or ""),
                    "market": str(row.get("domestic_market") or ""),
                    "exchange": str(row.get("domestic_exchange") or ""),
                    "status": str(row.get("status") or ""),
                    "identity_verified": bool(row.get("identity_verified")),
                }
            )
        return {
            "status": "planned",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "supervisor_busy": _supervisor_busy(self.status_path),
            "pending_case_count": len(pending),
            "feature_version": FEATURE_VERSION,
            "cases_per_existing_cycle": MAX_CASES_PER_RUN,
            "default_cycles_per_run": DEFAULT_CYCLES_PER_RUN,
            "max_cycles_per_run": MAX_CYCLES_PER_RUN,
            "default_case_budget": DEFAULT_CYCLES_PER_RUN * MAX_CASES_PER_RUN,
            "max_case_budget": MAX_CYCLES_PER_RUN * MAX_CASES_PER_RUN,
            "inter_cycle_seconds": INTER_CYCLE_SECONDS,
            "preview": preview,
        }

    def run_once(self, *, cycles: int = DEFAULT_CYCLES_PER_RUN) -> dict[str, Any]:
        started = time.time()
        requested_cycles = max(1, min(MAX_CYCLES_PER_RUN, int(cycles)))
        before_pending = len(self._pending())
        if _supervisor_busy(self.status_path):
            return {
                "status": "supervisor_busy",
                "paper_only": True,
                "shadow_only": True,
                "can_place_orders": False,
                "score_wired": False,
                "requested_cycles": requested_cycles,
                "completed_cycles": 0,
                "processed": 0,
                "pending_before": before_pending,
                "pending_after": before_pending,
                "elapsed_seconds": round(time.time() - started, 3),
            }

        cycle_results: list[dict[str, Any]] = []
        processed = 0
        collected = 0
        identity_waiting = 0
        source_errors = 0
        stop_reason = "cycle_budget_reached"

        for index in range(requested_cycles):
            if _supervisor_busy(self.status_path):
                stop_reason = "supervisor_became_busy"
                break

            result = self.cycle.run_once()
            cycle_processed = int(result.get("processed") or 0)
            cycle_collected = int(result.get("collected") or 0)
            cycle_identity_waiting = int(result.get("identity_waiting") or 0)
            cycle_source_errors = int(result.get("source_errors") or 0)
            processed += cycle_processed
            collected += cycle_collected
            identity_waiting += cycle_identity_waiting
            source_errors += cycle_source_errors
            cycle_results.append(
                {
                    "cycle": index + 1,
                    "status": str(result.get("status") or ""),
                    "pending_cases": int(result.get("pending_cases") or 0),
                    "processed": cycle_processed,
                    "collected": cycle_collected,
                    "identity_waiting": cycle_identity_waiting,
                    "source_errors": cycle_source_errors,
                    "elapsed_seconds": float(result.get("elapsed_seconds") or 0.0),
                    "cases": [
                        {
                            "case_key": str(row.get("case_key") or ""),
                            "market": str(row.get("market") or ""),
                            "status": str(row.get("status") or ""),
                        }
                        for row in (result.get("results") or [])
                        if isinstance(row, dict)
                    ],
                }
            )

            if cycle_processed <= 0 or str(result.get("status") or "") == "waiting_for_cases":
                stop_reason = "waiting_for_cases"
                break
            if cycle_source_errors >= cycle_processed:
                stop_reason = "source_error_guard"
                break
            if index + 1 < requested_cycles:
                self.sleeper(INTER_CYCLE_SECONDS)

        after_pending = len(self._pending())
        return {
            "status": "accelerated" if processed > 0 else "waiting_for_cases",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "requested_cycles": requested_cycles,
            "completed_cycles": len(cycle_results),
            "case_budget": requested_cycles * MAX_CASES_PER_RUN,
            "processed": processed,
            "collected": collected,
            "identity_waiting": identity_waiting,
            "source_errors": source_errors,
            "pending_before": before_pending,
            "pending_after": after_pending,
            "stop_reason": stop_reason,
            "cycles": cycle_results,
            "elapsed_seconds": round(time.time() - started, 3),
        }
