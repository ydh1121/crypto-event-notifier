from __future__ import annotations

import json
import math
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .dex_launch_features import FEATURE_VERSION, launch_window_features
from .dex_launch_quality import evaluate_dex_launch_quality
from .dex_launch_research_cycle import DEX_OHLCV_HISTORY_SECONDS, DexLaunchResearchCycle
from .dex_shadow_remediation_plan import plan_dex_shadow_remediation
from .historical_listing_backfill import HistoricalListingBackfill
from .research_control import STATUS_PATH, atomic_json


STATE_PATH = Path("b3_trader/data/research-platform/dex-shadow-remediation-build55-state.json")
DEFAULT_MAX_LAUNCH_RECOVERY_CASES = 2
MAX_LAUNCH_RECOVERY_CASES = 2
LAUNCH_RETRY_AFTER_SECONDS = 6 * 3600
HISTORICAL_PAGES_PER_EXCHANGE = 1


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


def _component_busy(path: Path, name: str) -> bool:
    payload = _read_json(path)
    components = payload.get("components") if isinstance(payload.get("components"), dict) else {}
    item = components.get(name) if isinstance(components.get(name), dict) else {}
    return bool(payload.get("running") and item.get("enabled") and str(item.get("status") or "") == "running")


def _launch_collected(feature: dict[str, Any]) -> bool:
    launch = feature.get("pool_launch_window") if isinstance(feature.get("pool_launch_window"), dict) else {}
    return str(launch.get("status") or "") == "collected"


def _source_key(candidate: dict[str, Any]) -> tuple[str, str, str, float]:
    return (
        str(candidate.get("network_id") or ""),
        str(candidate.get("token_address") or ""),
        str(candidate.get("pool_address") or ""),
        float(candidate.get("pool_created_at") or 0.0),
    )


class DexShadowRemediationRunner:
    """Bounded local remediation after Build53/54; never wires score or orders.

    Launch recovery reuses already-selected exact-contract primary pools and only
    refreshes launch OHLCV/features. Historical expansion delegates to Build47's
    official-source cursor with exactly one page per exchange per invocation.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        status_path: Path = STATUS_PATH,
        state_path: Path = STATE_PATH,
        cycle: Any | None = None,
        historical: HistoricalListingBackfill | Any | None = None,
    ) -> None:
        self.path = Path(path)
        self.status_path = Path(status_path)
        self.state_path = Path(state_path)
        self.cycle = cycle or DexLaunchResearchCycle(self.path)
        self.historical = historical or HistoricalListingBackfill(
            self.path,
            pages_per_exchange=HISTORICAL_PAGES_PER_EXCHANGE,
        )
        self._owns_cycle = cycle is None

    def close(self) -> None:
        if self._owns_cycle:
            self.cycle.close()

    def _busy(self) -> dict[str, bool]:
        return {
            "listing_history_research": _component_busy(self.status_path, "listing-history-research"),
            "dex_launch_research": _component_busy(self.status_path, "dex-launch-research"),
        }

    def _launch_candidates(self, *, now: float, limit: int = 100) -> list[dict[str, Any]]:
        quality = evaluate_dex_launch_quality(self.path)
        usable_keys = {
            str(row.get("case_key"))
            for row in quality.get("cases") or []
            if isinstance(row, dict) and row.get("usable_for_shadow_analysis") and row.get("case_key")
        }
        if not usable_keys or not self.path.exists():
            return []

        state = _read_json(self.state_path)
        attempts = state.get("launch_attempted_at") if isinstance(state.get("launch_attempted_at"), dict) else {}
        cutoff = float(now) - LAUNCH_RETRY_AFTER_SECONDS

        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            placeholders = ",".join("?" for _ in usable_keys)
            rows = conn.execute(
                f"""
                SELECT a.asset_key,a.case_key,a.network_id,a.token_address,
                       p.pool_address,p.pool_created_at,
                       f.feature_version,f.feature_json,
                       c.domestic_open_at
                FROM dex_launch_assets a
                JOIN dex_launch_pools p ON p.asset_key=a.asset_key
                JOIN listing_history_cases c ON c.case_key=a.case_key
                LEFT JOIN dex_launch_features f
                  ON f.asset_key=p.asset_key AND f.pool_address=p.pool_address
                WHERE p.selected_primary=1
                  AND a.case_key IN ({placeholders})
                ORDER BY p.pool_created_at DESC,a.case_key,a.asset_key
                """,
                tuple(sorted(usable_keys)),
            ).fetchall()
        finally:
            conn.close()

        rows_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for raw in rows:
            row = dict(raw)
            case_key = str(row.get("case_key") or "")
            if case_key:
                rows_by_case[case_key].append(row)

        candidates: list[dict[str, Any]] = []
        for case_key, case_rows in rows_by_case.items():
            parsed_rows = [(row, _feature_json(row.get("feature_json"))) for row in case_rows]
            if any(_launch_collected(feature) for _, feature in parsed_rows):
                continue

            eligible: list[dict[str, Any]] = []
            for row, feature in parsed_rows:
                asset_key = str(row.get("asset_key") or "")
                created = float(row.get("pool_created_at") or 0.0)
                if not asset_key or created <= 0 or float(now) - created > DEX_OHLCV_HISTORY_SECONDS:
                    continue
                last_attempt = float(attempts.get(asset_key) or 0.0)
                if last_attempt > cutoff:
                    continue
                launch = feature.get("pool_launch_window") if isinstance(feature.get("pool_launch_window"), dict) else {}
                status = str(launch.get("status") or "")
                if status not in {"", "not_available", "launch_ohlcv_unavailable"}:
                    continue
                eligible.append(
                    {
                        "case_key": case_key,
                        "asset_key": asset_key,
                        "network_id": str(row.get("network_id") or ""),
                        "token_address": str(row.get("token_address") or ""),
                        "pool_address": str(row.get("pool_address") or ""),
                        "pool_created_at": created,
                        "domestic_open_at": float(row.get("domestic_open_at") or 0.0),
                        "feature_version": int(row.get("feature_version") or FEATURE_VERSION),
                        "launch_status": status or "missing",
                        "pool_age_days": round(max(0.0, float(now) - created) / 86400.0, 4),
                    }
                )
            if eligible:
                candidates.append(max(eligible, key=lambda row: float(row.get("pool_created_at") or 0.0)))

        candidates.sort(key=lambda row: (float(row.get("pool_age_days") or math.inf), str(row.get("case_key") or "")))
        source_groups: dict[tuple[str, str, str, float], int] = defaultdict(int)
        for candidate in candidates:
            source_groups[_source_key(candidate)] += 1
        for candidate in candidates:
            candidate["shared_source_case_count"] = source_groups[_source_key(candidate)]
        return candidates[: max(1, min(100, int(limit)))]

    def plan(self, *, now: float | None = None) -> dict[str, Any]:
        current_now = float(now if now is not None else time.time())
        remediation = plan_dex_shadow_remediation(self.path, now=current_now)
        busy = self._busy()
        candidates = self._launch_candidates(now=current_now, limit=100)
        historical_plan = self.historical.plan()
        blockers = list(remediation.get("readiness", {}).get("blocking_reasons") or [])
        temporal_blocked = any(str(reason).startswith("temporal_concentration_above_max:") for reason in blockers)
        launch_blocked = any(str(reason).startswith("launch_feature_coverage_below_min:") for reason in blockers)
        historical_needed = bool(
            remediation.get("temporal_remediation", {}).get("historical_expansion_likely_required")
        )

        if remediation.get("readiness", {}).get("shadow_readiness_advisory"):
            action = "readiness_reached_stop"
        elif busy["listing_history_research"] or busy["dex_launch_research"]:
            action = "supervisor_busy"
        elif temporal_blocked and historical_needed and launch_blocked and candidates:
            action = "launch_recovery_plus_historical_expansion"
        elif temporal_blocked and historical_needed:
            action = "historical_expansion_only"
        elif launch_blocked and candidates:
            action = "launch_recovery_only"
        else:
            action = "manual_review_needed"

        distinct_sources = len({_source_key(candidate) for candidate in candidates})
        return {
            "status": "planned",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "action": action,
            "busy": busy,
            "remediation": remediation,
            "launch_recovery": {
                "candidate_count": len(candidates),
                "distinct_source_count": distinct_sources,
                "case_level_missing_only": True,
                "shared_source_fetch_reuse": True,
                "default_max_cases": DEFAULT_MAX_LAUNCH_RECOVERY_CASES,
                "hard_max_cases": MAX_LAUNCH_RECOVERY_CASES,
                "retry_after_seconds": LAUNCH_RETRY_AFTER_SECONDS,
                "preview": candidates[:10],
            },
            "historical_expansion": {
                "enabled_by_plan": bool(temporal_blocked and historical_needed),
                "pages_per_exchange": HISTORICAL_PAGES_PER_EXCHANGE,
                "official_sources_only": True,
                "build47_plan": historical_plan,
            },
        }

    def _recover_launch(
        self,
        candidate: dict[str, Any],
        *,
        now: float,
        source_cache: dict[tuple[str, str, str, float], dict[str, Any]],
    ) -> dict[str, Any]:
        asset_key = str(candidate.get("asset_key") or "")
        pool_address = str(candidate.get("pool_address") or "")
        source_key = _source_key(candidate)
        source_reused = source_key in source_cache
        if not source_reused:
            try:
                hourly, minute = self.cycle._launch_candles(
                    network_id=str(candidate.get("network_id") or ""),
                    pool_address=pool_address,
                    token_address=str(candidate.get("token_address") or ""),
                    pool_created_at=float(candidate.get("pool_created_at") or 0.0),
                    now=float(now),
                )
                source_cache[source_key] = {"ok": True, "hourly": hourly, "minute": minute}
            except Exception as exc:
                source_cache[source_key] = {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}"[:400],
                }
        source_result = source_cache[source_key]
        if not source_result.get("ok"):
            return {
                "case_key": str(candidate.get("case_key") or ""),
                "asset_key": asset_key,
                "status": "source_waiting",
                "source_reused": source_reused,
                "error": str(source_result.get("error") or "source_error"),
            }

        hourly = list(source_result.get("hourly") or [])
        minute = list(source_result.get("minute") or [])
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

            conn = sqlite3.connect(str(self.path), timeout=10)
            try:
                row = conn.execute(
                    "SELECT feature_json FROM dex_launch_features WHERE asset_key=? AND pool_address=?",
                    (asset_key, pool_address),
                ).fetchone()
            finally:
                conn.close()
            feature = _feature_json(row[0] if row else "{}")
            launch = launch_window_features(
                pool_created_at=float(candidate.get("pool_created_at") or 0.0),
                hourly=hourly,
                minute=minute,
                domestic_open_at=float(candidate.get("domestic_open_at") or 0.0),
            )
            feature["pool_launch_window"] = launch
            feature.setdefault("paper_only", True)
            feature.setdefault("shadow_only", True)
            self.cycle.store.upsert_features(
                asset_key=asset_key,
                pool_address=pool_address,
                feature_version=int(candidate.get("feature_version") or FEATURE_VERSION),
                features=feature,
            )
            return {
                "case_key": str(candidate.get("case_key") or ""),
                "asset_key": asset_key,
                "status": str(launch.get("status") or "unavailable"),
                "source_reused": source_reused,
                "launch_hourly": len(hourly),
                "launch_minute": len(minute),
                "pool_age_days": candidate.get("pool_age_days"),
            }
        except Exception as exc:
            return {
                "case_key": str(candidate.get("case_key") or ""),
                "asset_key": asset_key,
                "status": "source_waiting",
                "source_reused": source_reused,
                "error": f"{type(exc).__name__}: {exc}"[:400],
            }

    def run_once(
        self,
        *,
        max_launch_cases: int = DEFAULT_MAX_LAUNCH_RECOVERY_CASES,
        now: float | None = None,
    ) -> dict[str, Any]:
        started = time.time()
        current_now = float(now if now is not None else time.time())
        before = self.plan(now=current_now)
        action = str(before.get("action") or "manual_review_needed")
        max_launch_cases = max(1, min(MAX_LAUNCH_RECOVERY_CASES, int(max_launch_cases)))

        if action in {"readiness_reached_stop", "supervisor_busy", "manual_review_needed"}:
            return {
                "status": action,
                "paper_only": True,
                "shadow_only": True,
                "can_place_orders": False,
                "score_wired": False,
                "processed_launch": 0,
                "historical_pages_per_exchange": 0,
                "before": before,
                "after": before,
                "elapsed_seconds": round(time.time() - started, 3),
            }

        launch_results: list[dict[str, Any]] = []
        attempted_at: dict[str, float] = {}
        source_cache: dict[tuple[str, str, str, float], dict[str, Any]] = {}
        if action in {"launch_recovery_plus_historical_expansion", "launch_recovery_only"}:
            candidates = list(before.get("launch_recovery", {}).get("preview") or [])[:max_launch_cases]
            for candidate in candidates:
                if self._busy()["dex_launch_research"] or self._busy()["listing_history_research"]:
                    break
                result = self._recover_launch(candidate, now=current_now, source_cache=source_cache)
                launch_results.append(result)
                attempted_at[str(candidate.get("asset_key") or "")] = current_now

        state = _read_json(self.state_path)
        previous_attempts = state.get("launch_attempted_at") if isinstance(state.get("launch_attempted_at"), dict) else {}
        previous_attempts.update({key: value for key, value in attempted_at.items() if key})
        atomic_json(
            self.state_path,
            {
                "version": 1,
                "launch_attempted_at": previous_attempts,
                "updated_at": time.time(),
            },
        )

        historical_result: dict[str, Any] | None = None
        if action in {"launch_recovery_plus_historical_expansion", "historical_expansion_only"}:
            if not (self._busy()["dex_launch_research"] or self._busy()["listing_history_research"]):
                historical_result = self.historical.run_once()

        after = self.plan(now=time.time())
        return {
            "status": "remediated",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "selected_action": action,
            "launch_case_budget": max_launch_cases,
            "processed_launch": len(launch_results),
            "distinct_launch_source_fetches": len(source_cache),
            "launch_results": launch_results,
            "historical_pages_per_exchange": HISTORICAL_PAGES_PER_EXCHANGE if historical_result else 0,
            "historical_result": historical_result,
            "before": before,
            "after": after,
            "elapsed_seconds": round(time.time() - started, 3),
        }
