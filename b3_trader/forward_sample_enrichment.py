from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

from .auto_demo_v2 import DB_PATH
from .dex_launch_quality import evaluate_dex_launch_quality
from .dex_launch_research_cycle import DexLaunchResearchCycle
from .dex_shadow_score_v2_preregistration import FORWARD_CUTOFF_TS, FORWARD_CUTOFF_UTC
from .listing_history_collector import DomesticListingCase
from .listing_history_research_cycle import ListingHistoryResearchCycle
from .listing_identity import ListingIdentity
from .research_control import atomic_json


BUILD68_VERSION = 1
BUILD68_NAME = "dex_forward_sample_enrichment_v1"
STATE_PATH = Path("b3_trader/data/research-platform/forward-sample-enrichment-build68-state.json")
DEFAULT_MAX_CASES_PER_RUN = 1
HARD_MAX_CASES_PER_RUN = 1
RETRY_AFTER_SECONDS = 6 * 3600

QualityFn = Callable[[Path | str], dict[str, Any]]


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _identity_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw or "{}"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _forward_candidates(path: Path, *, now: float, state: dict[str, Any]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "listing_history_cases" not in tables:
            return []
        rows = conn.execute(
            """
            SELECT
              case_key,domestic_exchange,domestic_market,domestic_notice_id,symbol,
              announcement_at,domestic_open_at,domestic_open_price,identity_json,
              identity_verified,status,updated_at
            FROM listing_history_cases
            WHERE status NOT IN ('rejected_identity','rejected_notice')
              AND (
                domestic_open_at>=?
                OR (domestic_open_at<=0 AND announcement_at>=?)
              )
            ORDER BY
              CASE WHEN domestic_open_at>=? THEN 0 ELSE 1 END,
              CASE WHEN domestic_open_at>0 THEN domestic_open_at ELSE announcement_at END DESC,
              case_key
            """,
            (FORWARD_CUTOFF_TS, FORWARD_CUTOFF_TS, FORWARD_CUTOFF_TS),
        ).fetchall()
    finally:
        conn.close()

    attempts = state.get("attempted_at") if isinstance(state.get("attempted_at"), dict) else {}
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        key = str(item.get("case_key") or "")
        attempted_at = float(attempts.get(key) or 0.0)
        cooldown = attempted_at > 0 and now - attempted_at < RETRY_AFTER_SECONDS
        item["identity"] = _identity_payload(item.pop("identity_json", "{}"))
        item["forward_basis"] = (
            "confirmed_open"
            if float(item.get("domestic_open_at") or 0.0) >= FORWARD_CUTOFF_TS
            else "announcement_only_open_pending"
        )
        item["build68_last_attempted_at"] = attempted_at
        item["build68_cooldown_active"] = cooldown
        if not cooldown:
            result.append(item)
    return result


def _quality_case(path: Path, case_key: str, quality_fn: QualityFn) -> dict[str, Any]:
    quality = quality_fn(path)
    for row in quality.get("cases") or []:
        if isinstance(row, dict) and str(row.get("case_key") or "") == case_key:
            return row
    return {}


class ForwardSampleEnrichment:
    """Bounded post-cutoff enrichment without re-enabling generic supervisors.

    Build68 only selects Build65-forward cases, then reuses existing listing and
    DEX owners for that exact selected case. It never calls their generic
    run_once selectors, never scores v2, never changes PAPER decisions, and
    processes at most one case per invocation.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        state_path: Path = STATE_PATH,
        max_cases_per_run: int = DEFAULT_MAX_CASES_PER_RUN,
        quality_fn: QualityFn = evaluate_dex_launch_quality,
        listing_cycle_factory: Callable[..., ListingHistoryResearchCycle] = ListingHistoryResearchCycle,
        dex_cycle_factory: Callable[..., DexLaunchResearchCycle] = DexLaunchResearchCycle,
    ) -> None:
        self.path = Path(path)
        self.state_path = Path(state_path)
        self.max_cases_per_run = max(1, min(HARD_MAX_CASES_PER_RUN, int(max_cases_per_run)))
        self.quality_fn = quality_fn
        self.listing_cycle_factory = listing_cycle_factory
        self.dex_cycle_factory = dex_cycle_factory

    def plan(self) -> dict[str, Any]:
        now = time.time()
        state = _read_state(self.state_path)
        candidates = _forward_candidates(self.path, now=now, state=state)
        preview = [
            {
                "case_key": str(row.get("case_key") or ""),
                "exchange": str(row.get("domestic_exchange") or ""),
                "market": str(row.get("domestic_market") or ""),
                "announcement_at": float(row.get("announcement_at") or 0.0),
                "domestic_open_at": float(row.get("domestic_open_at") or 0.0),
                "identity_verified": bool(row.get("identity_verified")),
                "listing_status": str(row.get("status") or ""),
                "forward_basis": str(row.get("forward_basis") or ""),
            }
            for row in candidates[:5]
        ]
        return {
            "ok": True,
            "status": "planned",
            "build68_version": BUILD68_VERSION,
            "build68_name": BUILD68_NAME,
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "network_fetches": False,
            "database_mutation": False,
            "forward_only": True,
            "forward_boundary": {
                "cutoff_utc": FORWARD_CUTOFF_UTC,
                "cutoff_unix": FORWARD_CUTOFF_TS,
                "candidate_rule": "confirmed_open_or_post_cutoff_announcement_with_open_pending",
                "build66_final_score_eligibility_unchanged": "domestic_open_at_gte_forward_cutoff",
            },
            "bounds": {
                "default_max_cases_per_run": DEFAULT_MAX_CASES_PER_RUN,
                "hard_max_cases_per_run": HARD_MAX_CASES_PER_RUN,
                "retry_after_seconds": RETRY_AFTER_SECONDS,
            },
            "candidate_count": len(candidates),
            "preview": preview,
            "isolation": {
                "generic_listing_history_run_once_called": False,
                "generic_dex_launch_run_once_called": False,
                "build47_historical_cursor_read": False,
                "build47_historical_cursor_mutation": False,
                "pre_cutoff_cases_selectable": False,
            },
            "run_scope": {
                "resolve_identity_for_selected_forward_case": True,
                "collect_listing_history_for_selected_forward_case": True,
                "research_dex_for_selected_forward_case": True,
                "calculate_v2_score": False,
                "paper_ab": False,
                "cloudflare_publish": False,
            },
            "review": {
                "run_allowed": bool(candidates),
                "next_action": (
                    "run_build68_one_forward_case"
                    if candidates
                    else "repeat_build67_when_new_official_listing_notices_exist"
                ),
            },
        }

    def _persist_case(
        self,
        cycle: ListingHistoryResearchCycle,
        row: dict[str, Any],
        *,
        identity: ListingIdentity,
        open_at: float,
        open_price: float,
    ) -> None:
        cycle.store.upsert_case(
            domestic_exchange=str(row.get("domestic_exchange") or ""),
            domestic_market=str(row.get("domestic_market") or ""),
            domestic_notice_id=str(row.get("domestic_notice_id") or ""),
            symbol=str(row.get("symbol") or ""),
            announcement_at=float(row.get("announcement_at") or 0.0),
            domestic_open_at=float(open_at or 0.0),
            domestic_open_price=float(open_price or 0.0),
            identity=identity,
            identity_verified=True,
            status=str(row.get("status") or "pending_identity"),
        )

    def _reload_case_for_dex(self, case_key: str) -> dict[str, Any]:
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT
                  case_key,domestic_exchange,domestic_market,symbol,domestic_open_at,
                  identity_json,identity_verified,status AS listing_status
                FROM listing_history_cases
                WHERE case_key=?
                """,
                (case_key,),
            ).fetchone()
            if row is None:
                return {}
            item = dict(row)
            item["identity"] = _identity_payload(item.pop("identity_json", "{}"))
            return item
        finally:
            conn.close()

    def run_once(self) -> dict[str, Any]:
        started = time.time()
        now = time.time()
        state = _read_state(self.state_path)
        candidates = _forward_candidates(self.path, now=now, state=state)
        if not candidates:
            return {
                **self.plan(),
                "status": "waiting_no_forward_cases",
                "network_fetches": False,
                "database_mutation": False,
                "processed": 0,
                "results": [],
            }

        picked = candidates[: self.max_cases_per_run]
        attempts = state.get("attempted_at") if isinstance(state.get("attempted_at"), dict) else {}
        results: list[dict[str, Any]] = []

        listing_cycle = self.listing_cycle_factory(path=self.path)
        dex_cycle = self.dex_cycle_factory(path=self.path)
        try:
            for row in picked:
                case_key = str(row.get("case_key") or "")
                attempts[case_key] = now

                identity, identity_result = listing_cycle._resolve_identity(row)
                if identity is None:
                    results.append(
                        {
                            "case_key": case_key,
                            "status": "identity_waiting",
                            "identity": identity_result,
                            "listing": None,
                            "dex": None,
                            "usable_for_shadow_analysis": False,
                        }
                    )
                    continue

                open_at, open_price, price_result = listing_cycle._resolve_domestic_open(row, now)
                self._persist_case(
                    listing_cycle,
                    row,
                    identity=identity,
                    open_at=open_at,
                    open_price=open_price,
                )

                if open_at < FORWARD_CUTOFF_TS:
                    results.append(
                        {
                            "case_key": case_key,
                            "status": "open_time_pending",
                            "identity": {"status": identity_result.get("status"), "verified": True},
                            "domestic_price": price_result,
                            "listing": None,
                            "dex": None,
                            "usable_for_shadow_analysis": False,
                        }
                    )
                    continue

                case = DomesticListingCase(
                    exchange=str(row.get("domestic_exchange") or ""),
                    market=str(row.get("domestic_market") or ""),
                    symbol=str(row.get("symbol") or ""),
                    announcement_at=float(row.get("announcement_at") or 0.0),
                    open_at=open_at,
                    open_price=open_price,
                    identity=identity,
                    notice_id=str(row.get("domestic_notice_id") or ""),
                )
                try:
                    listing_result = listing_cycle.collector.collect_case(case)
                except Exception as exc:
                    listing_result = {
                        "status": "collector_error",
                        "error": f"{type(exc).__name__}: {exc}"[:300],
                    }

                dex_row = self._reload_case_for_dex(case_key)
                dex_result: dict[str, Any] | None = None
                if dex_row and bool(dex_row.get("identity_verified")):
                    try:
                        dex_result = dex_cycle._research_case(dex_row, now)
                    except Exception as exc:
                        dex_result = {
                            "case_key": case_key,
                            "status": "source_waiting",
                            "error": f"{type(exc).__name__}: {exc}"[:300],
                        }

                quality_case = _quality_case(self.path, case_key, self.quality_fn)
                results.append(
                    {
                        "case_key": case_key,
                        "status": (
                            "usable"
                            if quality_case.get("usable_for_shadow_analysis")
                            else "enriched_not_yet_usable"
                        ),
                        "identity": {"status": identity_result.get("status"), "verified": True},
                        "domestic_price": price_result,
                        "listing": {
                            "status": listing_result.get("status"),
                            "sources_ok": int(listing_result.get("sources_ok") or 0),
                            "error": listing_result.get("error") or "",
                        },
                        "dex": dex_result,
                        "usable_for_shadow_analysis": bool(
                            quality_case.get("usable_for_shadow_analysis")
                        ),
                    }
                )
        finally:
            dex_cycle.close()
            listing_cycle.close()

        atomic_json(
            self.state_path,
            {
                "version": BUILD68_VERSION,
                "updated_at": time.time(),
                "attempted_at": attempts,
                "last_results": results,
            },
        )
        usable_gain = sum(1 for row in results if row.get("usable_for_shadow_analysis"))
        return {
            "ok": True,
            "status": "enriched" if results else "waiting_no_forward_cases",
            "build68_version": BUILD68_VERSION,
            "build68_name": BUILD68_NAME,
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "network_fetches": bool(results),
            "database_mutation": bool(results),
            "forward_only": True,
            "forward_boundary": {
                "cutoff_utc": FORWARD_CUTOFF_UTC,
                "cutoff_unix": FORWARD_CUTOFF_TS,
                "pre_cutoff_cases_processed": 0,
                "build66_final_score_eligibility_unchanged": "domestic_open_at_gte_forward_cutoff",
            },
            "bounds": {
                "processed_max": HARD_MAX_CASES_PER_RUN,
                "retry_after_seconds": RETRY_AFTER_SECONDS,
            },
            "processed": len(results),
            "usable_gain": usable_gain,
            "results": results,
            "isolation": {
                "generic_listing_history_run_once_called": False,
                "generic_dex_launch_run_once_called": False,
                "build47_historical_cursor_read": False,
                "build47_historical_cursor_mutation": False,
            },
            "scope": {
                "score_calculations": 0,
                "paper_ab_wired": False,
                "strategy_signal_mutation": False,
                "position_sizing_mutation": False,
                "cloudflare_publishing": False,
            },
            "elapsed_seconds": round(time.time() - started, 3),
            "review": {
                "build66_reaudit_allowed": bool(usable_gain),
                "next_action": (
                    "reaudit_build66_forward_v2_score"
                    if usable_gain
                    else "repeat_build67_then_build68_for_new_forward_cases"
                ),
            },
        }
