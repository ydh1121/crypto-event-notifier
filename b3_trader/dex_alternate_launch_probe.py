from __future__ import annotations

import json
import math
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from .auto_demo_v2 import DB_PATH
from .dex_launch_coverage_audit import audit_dex_launch_coverage
from .dex_launch_features import FEATURE_VERSION, launch_window_features
from .dex_launch_research_cycle import DexLaunchResearchCycle
from .dex_shadow_remediation_runner import _component_busy
from .research_control import STATUS_PATH, atomic_json


STATE_PATH = Path("b3_trader/data/research-platform/dex-alternate-launch-probe-build61-state.json")
DEFAULT_MAX_SOURCE_PROBES = 1
MAX_SOURCE_PROBES = 2
RETRY_AFTER_SECONDS = 6 * 3600
PRIORITY_POLICY = "shared_case_gain_then_pool_freshness"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _feature_json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _source_key(row: dict[str, Any]) -> tuple[str, str, str, float]:
    return (
        str(row.get("network_id") or ""),
        str(row.get("token_address") or ""),
        str(row.get("pool_address") or ""),
        float(row.get("pool_created_at") or 0.0),
    )


def _source_id(row: dict[str, Any]) -> str:
    network_id, token_address, pool_address, pool_created_at = _source_key(row)
    return "|".join((network_id, token_address, pool_address, f"{pool_created_at:.6f}"))


class DexAlternateLaunchProbeRunner:
    """Bounded alternate accepted-pool launch probe after Build60.

    Build61 never changes selected_primary, never fetches a domestic listing
    window, and never wires score/orders. It only probes launch OHLCV for
    exact-contract non-primary pools that already passed the Build42 quality
    gate and were surfaced by the read-only Build60 audit.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        status_path: Path = STATUS_PATH,
        state_path: Path = STATE_PATH,
        cycle: Any | None = None,
        audit_fn: Callable[..., dict[str, Any]] = audit_dex_launch_coverage,
    ) -> None:
        self.path = Path(path)
        self.status_path = Path(status_path)
        self.state_path = Path(state_path)
        self.cycle = cycle or DexLaunchResearchCycle(self.path)
        self.audit_fn = audit_fn
        self._owns_cycle = cycle is None

    def close(self) -> None:
        if self._owns_cycle:
            self.cycle.close()

    def _busy(self) -> dict[str, bool]:
        return {
            "listing_history_research": _component_busy(self.status_path, "listing-history-research"),
            "dex_launch_research": _component_busy(self.status_path, "dex-launch-research"),
        }

    def _candidate_sources(self, *, now: float, limit: int = 100) -> list[dict[str, Any]]:
        audit = self.audit_fn(self.path, now=now)
        opportunities = (
            audit.get("alternate_pool_opportunities")
            if isinstance(audit.get("alternate_pool_opportunities"), list)
            else []
        )
        rows = [dict(row) for row in opportunities if isinstance(row, dict)]
        if not rows or not self.path.exists():
            return []

        case_keys = sorted({str(row.get("case_key") or "") for row in rows if row.get("case_key")})
        domestic_open_by_case: dict[str, float] = {}
        if case_keys:
            conn = sqlite3.connect(str(self.path), timeout=10)
            conn.row_factory = sqlite3.Row
            try:
                placeholders = ",".join("?" for _ in case_keys)
                for row in conn.execute(
                    f"SELECT case_key,domestic_open_at FROM listing_history_cases WHERE case_key IN ({placeholders})",
                    tuple(case_keys),
                ).fetchall():
                    domestic_open_by_case[str(row["case_key"])] = float(row["domestic_open_at"] or 0.0)
            finally:
                conn.close()

        state = _read_json(self.state_path)
        attempts = state.get("source_attempted_at") if isinstance(state.get("source_attempted_at"), dict) else {}
        cutoff = float(now) - RETRY_AFTER_SECONDS

        grouped: dict[tuple[str, str, str, float], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            case_key = str(row.get("case_key") or "")
            asset_key = str(row.get("asset_key") or "")
            if not case_key or not asset_key:
                continue
            row["domestic_open_at"] = domestic_open_by_case.get(case_key, 0.0)
            grouped[_source_key(row)].append(row)

        candidates: list[dict[str, Any]] = []
        for source_key, members in grouped.items():
            representative = max(
                members,
                key=lambda row: (
                    float(row.get("volume_h24_usd") or 0.0),
                    float(row.get("reserve_usd") or 0.0),
                    str(row.get("case_key") or ""),
                ),
            )
            source_id = _source_id(representative)
            last_attempt = float(attempts.get(source_id) or 0.0)
            if last_attempt > cutoff:
                continue

            unique_members: dict[str, dict[str, Any]] = {}
            for member in members:
                case_key = str(member.get("case_key") or "")
                if case_key and case_key not in unique_members:
                    unique_members[case_key] = dict(member)

            candidates.append(
                {
                    "source_id": source_id,
                    "network_id": source_key[0],
                    "token_address": source_key[1],
                    "pool_address": source_key[2],
                    "pool_created_at": source_key[3],
                    "dex_id": str(representative.get("dex_id") or ""),
                    "pool_age_days": float(representative.get("pool_age_days") or math.inf),
                    "reserve_usd": float(representative.get("reserve_usd") or 0.0),
                    "volume_h24_usd": float(representative.get("volume_h24_usd") or 0.0),
                    "potential_case_gain": len(unique_members),
                    "shared_event_case_count": len(unique_members),
                    "members": [unique_members[key] for key in sorted(unique_members)],
                    "previously_attempted_by_build61": bool(last_attempt > 0),
                    "build61_priority_policy": PRIORITY_POLICY,
                }
            )

        candidates.sort(
            key=lambda row: (
                -int(row.get("potential_case_gain") or 0),
                float(row.get("pool_age_days") or math.inf),
                -float(row.get("volume_h24_usd") or 0.0),
                str(row.get("source_id") or ""),
            )
        )
        return candidates[: max(1, min(100, int(limit)))]

    def plan(self, *, now: float | None = None) -> dict[str, Any]:
        current_now = float(now if now is not None else time.time())
        audit = self.audit_fn(self.path, now=current_now)
        summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
        busy = self._busy()
        candidates = self._candidate_sources(now=current_now, limit=100)
        additional_needed = int(summary.get("additional_launch_cases_needed") or 0)

        if additional_needed <= 0:
            action = "readiness_reached_stop"
        elif busy["listing_history_research"] or busy["dex_launch_research"]:
            action = "supervisor_busy"
        elif candidates:
            action = "alternate_pool_launch_probe"
        else:
            action = "no_alternate_candidate"

        return {
            "status": "planned",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "action": action,
            "busy": busy,
            "build60_summary": summary,
            "alternate_probe": {
                "accepted_non_primary_only": True,
                "selected_primary_mutation": False,
                "domestic_window_fetches": False,
                "shared_source_fetch_reuse": True,
                "priority_policy": PRIORITY_POLICY,
                "candidate_source_count": len(candidates),
                "candidate_case_gain_total": sum(int(row.get("potential_case_gain") or 0) for row in candidates),
                "default_max_source_probes": DEFAULT_MAX_SOURCE_PROBES,
                "hard_max_source_probes": MAX_SOURCE_PROBES,
                "retry_after_seconds": RETRY_AFTER_SECONDS,
                "preview": candidates[:10],
            },
        }

    def _validated_members(self, candidate: dict[str, Any]) -> list[dict[str, Any]]:
        members = [dict(row) for row in (candidate.get("members") or []) if isinstance(row, dict)]
        if not members or not self.path.exists():
            return []
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            valid: list[dict[str, Any]] = []
            for member in members:
                row = conn.execute(
                    """
                    SELECT gate_status,selected_primary,reserve_usd,volume_h24_usd,pool_created_at
                    FROM dex_launch_pools
                    WHERE asset_key=? AND pool_address=?
                    """,
                    (str(member.get("asset_key") or ""), str(candidate.get("pool_address") or "")),
                ).fetchone()
                if row is None:
                    continue
                if str(row["gate_status"] or "") != "accepted" or int(row["selected_primary"] or 0) != 0:
                    continue
                if float(row["pool_created_at"] or 0.0) != float(candidate.get("pool_created_at") or 0.0):
                    continue
                member["reserve_usd"] = float(row["reserve_usd"] or 0.0)
                member["volume_h24_usd"] = float(row["volume_h24_usd"] or 0.0)
                valid.append(member)
            return valid
        finally:
            conn.close()

    def _existing_feature(self, *, asset_key: str, pool_address: str) -> dict[str, Any]:
        conn = sqlite3.connect(str(self.path), timeout=10)
        try:
            row = conn.execute(
                "SELECT feature_json FROM dex_launch_features WHERE asset_key=? AND pool_address=?",
                (asset_key, pool_address),
            ).fetchone()
        finally:
            conn.close()
        return _feature_json(row[0] if row else "{}")

    def _probe_source(self, candidate: dict[str, Any], *, now: float) -> dict[str, Any]:
        members = self._validated_members(candidate)
        if not members:
            return {
                "source_id": str(candidate.get("source_id") or ""),
                "status": "stale_candidate",
                "source_fetch_performed": False,
                "potential_case_gain": int(candidate.get("potential_case_gain") or 0),
                "affected_event_cases": 0,
                "collected_case_gain": 0,
            }

        try:
            hourly, minute = self.cycle._launch_candles(
                network_id=str(candidate.get("network_id") or ""),
                pool_address=str(candidate.get("pool_address") or ""),
                token_address=str(candidate.get("token_address") or ""),
                pool_created_at=float(candidate.get("pool_created_at") or 0.0),
                now=float(now),
            )
        except Exception as exc:
            return {
                "source_id": str(candidate.get("source_id") or ""),
                "status": "source_waiting",
                "source_fetch_performed": True,
                "potential_case_gain": int(candidate.get("potential_case_gain") or 0),
                "affected_event_cases": 0,
                "collected_case_gain": 0,
                "error": f"{type(exc).__name__}: {exc}"[:400],
            }

        case_results: list[dict[str, Any]] = []
        collected_case_gain = 0
        pool_address = str(candidate.get("pool_address") or "")
        for member in members:
            asset_key = str(member.get("asset_key") or "")
            case_key = str(member.get("case_key") or "")
            try:
                self.cycle.store.upsert_candles(
                    asset_key=asset_key,
                    pool_address=pool_address,
                    series_kind="launch_hourly",
                    candles=hourly,
                )
                self.cycle.store.upsert_candles(
                    asset_key=asset_key,
                    pool_address=pool_address,
                    series_kind="launch_minute",
                    candles=minute,
                )
                launch = launch_window_features(
                    pool_created_at=float(candidate.get("pool_created_at") or 0.0),
                    hourly=list(hourly),
                    minute=list(minute),
                    domestic_open_at=float(member.get("domestic_open_at") or 0.0),
                )
                feature = self._existing_feature(asset_key=asset_key, pool_address=pool_address)
                feature["version"] = int(feature.get("version") or FEATURE_VERSION)
                feature["paper_only"] = True
                feature["shadow_only"] = True
                feature["alternate_pool_launch_probe"] = True
                feature["pool_quality"] = {
                    "reserve_usd": float(member.get("reserve_usd") or 0.0),
                    "volume_h24_usd": float(member.get("volume_h24_usd") or 0.0),
                    "min_liquidity_usd": float(self.cycle.min_liquidity_usd),
                    "min_volume_h24_usd": float(self.cycle.min_volume_h24_usd),
                    "passed": True,
                }
                feature.setdefault(
                    "domestic_listing_window",
                    {
                        "status": "alternate_pool_probe_not_used_for_domestic_listing_window",
                        "reference": None,
                        "pre": {},
                        "post": {},
                    },
                )
                feature["pool_launch_window"] = launch
                self.cycle.store.upsert_features(
                    asset_key=asset_key,
                    pool_address=pool_address,
                    feature_version=FEATURE_VERSION,
                    features=feature,
                )
                status = str(launch.get("status") or "unavailable")
                if status == "collected":
                    collected_case_gain += 1
                case_results.append({"case_key": case_key, "asset_key": asset_key, "status": status})
            except Exception as exc:
                case_results.append(
                    {
                        "case_key": case_key,
                        "asset_key": asset_key,
                        "status": "source_waiting",
                        "error": f"{type(exc).__name__}: {exc}"[:400],
                    }
                )

        statuses = {str(row.get("status") or "") for row in case_results}
        source_status = (
            "collected"
            if "collected" in statuses
            else ("source_waiting" if "source_waiting" in statuses else "launch_ohlcv_unavailable")
        )
        return {
            "source_id": str(candidate.get("source_id") or ""),
            "network_id": str(candidate.get("network_id") or ""),
            "pool_address": pool_address,
            "dex_id": str(candidate.get("dex_id") or ""),
            "status": source_status,
            "source_fetch_performed": True,
            "launch_hourly": len(hourly),
            "launch_minute": len(minute),
            "potential_case_gain": int(candidate.get("potential_case_gain") or 0),
            "affected_event_cases": len(case_results),
            "collected_case_gain": collected_case_gain,
            "case_results": case_results,
        }

    def run_once(
        self,
        *,
        max_sources: int = DEFAULT_MAX_SOURCE_PROBES,
        now: float | None = None,
    ) -> dict[str, Any]:
        started = time.time()
        current_now = float(now if now is not None else time.time())
        before = self.plan(now=current_now)
        action = str(before.get("action") or "no_alternate_candidate")
        source_budget = max(1, min(MAX_SOURCE_PROBES, int(max_sources)))

        if action != "alternate_pool_launch_probe":
            return {
                "status": action,
                "paper_only": True,
                "shadow_only": True,
                "can_place_orders": False,
                "score_wired": False,
                "source_probe_budget": source_budget,
                "processed_sources": 0,
                "distinct_source_fetches": 0,
                "results": [],
                "before": before,
                "after": before,
                "elapsed_seconds": round(time.time() - started, 3),
            }

        selected = list(before.get("alternate_probe", {}).get("preview") or [])[:source_budget]
        results: list[dict[str, Any]] = []
        attempted_at: dict[str, float] = {}
        for candidate in selected:
            if self._busy()["listing_history_research"] or self._busy()["dex_launch_research"]:
                break
            result = self._probe_source(candidate, now=current_now)
            results.append(result)
            if result.get("source_fetch_performed"):
                source_id = str(candidate.get("source_id") or "")
                if source_id:
                    attempted_at[source_id] = current_now

        state = _read_json(self.state_path)
        previous_attempts = (
            state.get("source_attempted_at") if isinstance(state.get("source_attempted_at"), dict) else {}
        )
        previous_attempts.update(attempted_at)
        atomic_json(
            self.state_path,
            {
                "version": 1,
                "source_attempted_at": previous_attempts,
                "updated_at": time.time(),
            },
        )

        after = self.plan(now=time.time())
        return {
            "status": "probed",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "selected_primary_mutation": False,
            "domestic_window_fetches": False,
            "source_probe_budget": source_budget,
            "processed_sources": len(results),
            "distinct_source_fetches": sum(1 for row in results if row.get("source_fetch_performed")),
            "total_collected_case_gain": sum(int(row.get("collected_case_gain") or 0) for row in results),
            "results": results,
            "before": before,
            "after": after,
            "elapsed_seconds": round(time.time() - started, 3),
        }
