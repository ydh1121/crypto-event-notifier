from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .dex_launch_quality import evaluate_dex_launch_quality
from .listing_history_store import ListingHistoryStore
from .listing_identity import ListingIdentity, listing_identity_gate
from .listing_identity_resolver import ListingIdentityResolver
from .research_control import STATUS_PATH, atomic_json

STATE_PATH = Path("b3_trader/data/research-platform/temporal-identity-preparation-build58-state.json")
PRIMARY_MONTH_BEFORE = "2026-07"
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


def _usable_asset_ids(path: Path) -> set[str]:
    quality = evaluate_dex_launch_quality(path)
    result: set[str] = set()
    for row in quality.get("cases") or []:
        if not isinstance(row, dict) or not bool(row.get("usable_for_shadow_analysis")):
            continue
        coin_id = str(row.get("coingecko_id") or "").strip()
        if coin_id:
            result.add(coin_id)
    return result


class TemporalIdentityPreparationRunner:
    """Prepare exact CoinGecko identity for pre-July historical listing cases.

    Build58 performs identity preparation only. It never performs DEX research,
    score calculation, PAPER decisions, or order placement. Candidates are
    historical listing cases before 2026-07 with no existing DEX status and no
    verified identity. Resolution delegates to the existing fail-closed
    ListingIdentityResolver; only verified CoinGecko identities with provider_id
    are persisted.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        state_path: Path = STATE_PATH,
        status_path: Path = STATUS_PATH,
        resolver: ListingIdentityResolver | None = None,
    ) -> None:
        self.path = Path(path)
        self.state_path = Path(state_path)
        self.status_path = Path(status_path)
        self.resolver = resolver or ListingIdentityResolver()

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
                SELECT c.case_key,c.domestic_exchange,c.domestic_market,c.domestic_notice_id,c.symbol,
                       c.announcement_at,c.domestic_open_at,c.domestic_open_price,c.identity_json,
                       c.identity_verified,c.status AS listing_status
                FROM listing_history_cases c
                {join}
                WHERE c.identity_verified=0
                  AND c.status NOT IN ('rejected_identity','rejected_notice')
                  {no_dex}
                ORDER BY COALESCE(NULLIF(c.domestic_open_at,0),NULLIF(c.announcement_at,0),0) ASC,
                         c.case_key ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def plan(self, *, now: float | None = None, limit: int = 20) -> dict[str, Any]:
        current_now = float(now if now is not None else time.time())
        cutoff = current_now - RETRY_AFTER_SECONDS
        attempts = self._attempts()
        usable_ids = _usable_asset_ids(self.path)
        candidates: list[dict[str, Any]] = []
        later_pending: list[dict[str, Any]] = []

        for row in self._listing_rows():
            case_key = str(row.get("case_key") or "")
            reference_ts = float(row.get("domestic_open_at") or row.get("announcement_at") or 0.0)
            month = _month_bucket(reference_ts)
            if not case_key or month == "unknown" or attempts.get(case_key, 0.0) > cutoff:
                continue
            item = {
                "case_key": case_key,
                "domestic_exchange": str(row.get("domestic_exchange") or ""),
                "domestic_market": str(row.get("domestic_market") or ""),
                "symbol": str(row.get("symbol") or ""),
                "listing_month": month,
                "domestic_open_at": float(row.get("domestic_open_at") or 0.0),
                "announcement_at": float(row.get("announcement_at") or 0.0),
                "listing_status": str(row.get("listing_status") or "pending_identity"),
                "identity_verified": False,
                "priority": "pre_july_pending_exact_identity" if month < PRIMARY_MONTH_BEFORE else "later_pending_not_selected",
            }
            if month < PRIMARY_MONTH_BEFORE:
                candidates.append(item)
            else:
                later_pending.append(item)

        candidates.sort(key=lambda row: (str(row.get("listing_month") or ""), float(row.get("domestic_open_at") or row.get("announcement_at") or 0.0), str(row.get("case_key") or "")))
        later_pending.sort(key=lambda row: (str(row.get("listing_month") or ""), str(row.get("case_key") or "")))
        busy = self._busy()
        if busy["listing_history_research"] or busy["dex_launch_research"]:
            action = "supervisor_busy"
        elif candidates:
            action = "temporal_identity_prepare"
        else:
            action = "historical_expansion_needed"

        return {
            "status": "planned",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "action": action,
            "busy": busy,
            "policy": {
                "pre_july_only": True,
                "verified_coingecko_only_on_write": True,
                "no_existing_dex_status": True,
                "ticker_only_forbidden": True,
                "dex_research": False,
            },
            "primary_month_before": PRIMARY_MONTH_BEFORE,
            "usable_asset_id_count": len(usable_ids),
            "max_cases_per_run": MAX_CASES_PER_RUN,
            "retry_after_seconds": RETRY_AFTER_SECONDS,
            "candidate_count": len(candidates),
            "candidates": candidates[: max(1, min(100, int(limit)))],
            "later_pending_count": len(later_pending),
            "later_pending_preview": later_pending[:10],
        }

    def run_once(self, *, max_cases: int = DEFAULT_MAX_CASES_PER_RUN) -> dict[str, Any]:
        started = time.time()
        before = self.plan(now=started, limit=100)
        action = str(before.get("action") or "historical_expansion_needed")
        if action != "temporal_identity_prepare":
            return {
                "status": action,
                "paper_only": True,
                "shadow_only": True,
                "can_place_orders": False,
                "score_wired": False,
                "processed": 0,
                "prepared_exact_coingecko": 0,
                "before": before,
                "after": before,
                "elapsed_seconds": round(time.time() - started, 3),
            }

        limit = max(1, min(MAX_CASES_PER_RUN, int(max_cases)))
        picked = list(before.get("candidates") or [])[:limit]
        attempts = self._attempts()
        usable_ids = _usable_asset_ids(self.path)
        results: list[dict[str, Any]] = []
        prepared = 0
        store = ListingHistoryStore(self.path)
        try:
            conn = store.conn
            for candidate in picked:
                if self._busy()["listing_history_research"] or self._busy()["dex_launch_research"]:
                    break
                case_key = str(candidate.get("case_key") or "")
                exchange = str(candidate.get("domestic_exchange") or "")
                market = str(candidate.get("domestic_market") or "")
                try:
                    resolved = self.resolver.resolve(exchange, market)
                except Exception as exc:
                    resolved = {
                        "status": "identity_error",
                        "verified": False,
                        "identity": None,
                        "error": f"{type(exc).__name__}: {exc}"[:300],
                    }
                attempts[case_key] = time.time()
                identity = resolved.get("identity") if isinstance(resolved, dict) else None
                exact = bool(
                    isinstance(identity, ListingIdentity)
                    and resolved.get("verified")
                    and identity.provider == "coingecko"
                    and bool(identity.provider_id)
                    and listing_identity_gate(identity).get("verified")
                )
                if exact:
                    row = conn.execute("SELECT * FROM listing_history_cases WHERE case_key=? LIMIT 1", (case_key,)).fetchone()
                    if row is not None:
                        current = dict(row)
                        store.upsert_case(
                            domestic_exchange=str(current.get("domestic_exchange") or ""),
                            domestic_market=str(current.get("domestic_market") or ""),
                            domestic_notice_id=str(current.get("domestic_notice_id") or ""),
                            symbol=str(current.get("symbol") or ""),
                            announcement_at=float(current.get("announcement_at") or 0.0),
                            domestic_open_at=float(current.get("domestic_open_at") or 0.0),
                            domestic_open_price=float(current.get("domestic_open_price") or 0.0),
                            identity=identity,
                            identity_verified=True,
                            status=str(current.get("status") or "pending_identity"),
                        )
                        prepared += 1
                provider_id = identity.provider_id if isinstance(identity, ListingIdentity) else ""
                results.append(
                    {
                        "case_key": case_key,
                        "market": market,
                        "listing_month": candidate.get("listing_month"),
                        "status": str(resolved.get("status") or "identity_unverified") if isinstance(resolved, dict) else "identity_unverified",
                        "verified": bool(exact),
                        "provider": identity.provider if isinstance(identity, ListingIdentity) else "",
                        "provider_id": provider_id,
                        "new_unique_candidate": bool(exact and provider_id not in usable_ids),
                        "error": str(resolved.get("error") or "") if isinstance(resolved, dict) else "",
                    }
                )
        finally:
            store.close()

        atomic_json(
            self.state_path,
            {"version": 1, "updated_at": time.time(), "attempts": attempts, "last_results": results},
        )
        after = self.plan(now=time.time(), limit=100)
        return {
            "status": "identity_prepared" if results else "supervisor_became_busy",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "processed": len(results),
            "prepared_exact_coingecko": prepared,
            "results": results,
            "before": before,
            "after": after,
            "elapsed_seconds": round(time.time() - started, 3),
        }
