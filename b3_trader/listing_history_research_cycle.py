from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .domestic_listing_price import DomesticListingPriceResolver
from .listing_history_collector import DomesticListingCase, ListingHistoryCollector
from .listing_history_planner import ListingHistoryPlanner
from .listing_history_store import ListingHistoryStore
from .listing_identity import ListingIdentity, listing_identity_gate
from .listing_identity_resolver import ListingIdentityResolver
from .research_control import atomic_json


STATE_PATH = Path("b3_trader/data/research-platform/listing-history-cycle-state.json")
MAX_CASES_PER_RUN = 3
SEED_NOTICE_LIMIT_PER_EXCHANGE = 60


def _read_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _num(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _stored_identity(row: dict[str, Any]) -> ListingIdentity | None:
    source = row.get("identity") if isinstance(row.get("identity"), dict) else {}
    if not source or not bool(row.get("identity_verified")):
        return None
    identity = ListingIdentity.from_dict(source)
    return identity if listing_identity_gate(identity)["verified"] else None


def _venue_capable_identity(identity: ListingIdentity) -> bool:
    return identity.provider == "coingecko" and bool(identity.provider_id)


def _rotate_cases(rows: list[dict[str, Any]], cursor: int, limit: int) -> tuple[list[dict[str, Any]], int]:
    if not rows:
        return [], 0
    total = len(rows)
    start = max(0, int(cursor)) % total
    picked: list[dict[str, Any]] = []
    for offset in range(min(max(1, int(limit)), total)):
        picked.append(rows[(start + offset) % total])
    return picked, (start + len(picked)) % total


class ListingHistoryResearchCycle:
    """Bounded sidecar cycle for KRW listing-history research.

    It only coordinates existing owners: notice planner, verified profile identity,
    domestic public opening candle, public foreign CEX adapters and local store.
    It never changes PAPER scores or places orders.
    """

    def __init__(
        self,
        path: Path = DB_PATH,
        *,
        planner: ListingHistoryPlanner | None = None,
        store: ListingHistoryStore | None = None,
        identity_resolver: ListingIdentityResolver | None = None,
        price_resolver: DomesticListingPriceResolver | None = None,
        collector: ListingHistoryCollector | None = None,
        state_path: Path = STATE_PATH,
    ) -> None:
        self.path = Path(path)
        self.planner = planner or ListingHistoryPlanner(self.path)
        self.store = store or ListingHistoryStore(self.path)
        self.identity_resolver = identity_resolver or ListingIdentityResolver()
        self.price_resolver = price_resolver or DomesticListingPriceResolver()
        self.collector = collector or ListingHistoryCollector()
        self.state_path = Path(state_path)
        self._owns_planner = planner is None
        self._owns_store = store is None
        self._owns_collector = collector is None

    def close(self) -> None:
        if self._owns_collector:
            self.collector.close()
        if self._owns_store:
            self.store.close()
        if self._owns_planner:
            self.planner.close()

    def _resolve_identity(self, row: dict[str, Any]) -> tuple[ListingIdentity | None, dict[str, Any]]:
        stored = _stored_identity(row)
        if stored is not None and _venue_capable_identity(stored):
            return stored, {"status": "stored_verified", "verified": True}

        try:
            result = self.identity_resolver.resolve(
                str(row.get("domestic_exchange") or ""),
                str(row.get("domestic_market") or ""),
            )
        except Exception as exc:
            if stored is not None:
                return stored, {
                    "status": "stored_verified_legacy",
                    "verified": True,
                    "refresh_error": f"{type(exc).__name__}: {exc}"[:300],
                }
            return None, {"status": "identity_error", "verified": False, "error": f"{type(exc).__name__}: {exc}"[:300]}

        identity = result.get("identity") if isinstance(result, dict) else None
        if isinstance(identity, ListingIdentity) and result.get("verified"):
            if stored is not None:
                return identity, {
                    **result,
                    "status": "stored_refreshed",
                    "verified": True,
                    "previous_provider": stored.provider,
                    "previous_provider_id": stored.provider_id,
                }
            return identity, result

        if stored is not None:
            return stored, {
                "status": "stored_verified_legacy",
                "verified": True,
                "refresh_status": result.get("status") if isinstance(result, dict) else "invalid_response",
            }
        return None, result if isinstance(result, dict) else {"status": "invalid_response", "verified": False}

    def _resolve_open_price(self, row: dict[str, Any], now: float) -> tuple[float, dict[str, Any]]:
        current = _num(row.get("domestic_open_price"))
        if current > 0:
            return current, {"status": "stored", "found": True, "price": current}
        open_at = _num(row.get("domestic_open_at"))
        if open_at <= 0:
            return 0.0, {"status": "open_time_missing", "found": False, "price": 0.0}
        if now + 60 < open_at:
            return 0.0, {"status": "waiting_for_open", "found": False, "price": 0.0}
        result = self.price_resolver.resolve(
            str(row.get("domestic_exchange") or ""),
            str(row.get("domestic_market") or ""),
            open_at,
        )
        return (_num(result.get("price")) if result.get("found") else 0.0), result

    def run_once(self) -> dict[str, Any]:
        started = time.time()
        now = time.time()
        seed = self.planner.seed_once(per_exchange_limit=SEED_NOTICE_LIMIT_PER_EXCHANGE)
        pending = self.store.pending_cases(limit=500)
        state = _read_state(self.state_path)
        picked, next_cursor = _rotate_cases(
            pending,
            int(state.get("cursor") or 0),
            MAX_CASES_PER_RUN,
        )
        results: list[dict[str, Any]] = []
        identity_waiting = 0
        collected = 0
        source_errors = 0

        for row in picked:
            key = str(row.get("case_key") or "")
            identity, identity_result = self._resolve_identity(row)
            if identity is None:
                identity_waiting += 1
                results.append({
                    "case_key": key,
                    "market": row.get("domestic_market"),
                    "status": str(identity_result.get("status") or "pending_identity"),
                    "identity": identity_result,
                })
                continue

            open_price, price_result = self._resolve_open_price(row, now)
            open_at = _num(row.get("domestic_open_at"))
            # Persist verified identity immediately so future cycles do not need
            # another profile-cache read once a venue-capable identity is stored.
            self.store.upsert_case(
                domestic_exchange=str(row.get("domestic_exchange") or ""),
                domestic_market=str(row.get("domestic_market") or ""),
                domestic_notice_id=str(row.get("domestic_notice_id") or ""),
                symbol=str(row.get("symbol") or ""),
                announcement_at=_num(row.get("announcement_at")),
                domestic_open_at=open_at,
                domestic_open_price=open_price,
                identity=identity,
                identity_verified=True,
                status=str(row.get("status") or "pending_identity"),
            )
            case = DomesticListingCase(
                exchange=str(row.get("domestic_exchange") or ""),
                market=str(row.get("domestic_market") or ""),
                symbol=str(row.get("symbol") or ""),
                announcement_at=_num(row.get("announcement_at")),
                open_at=open_at,
                open_price=open_price,
                identity=identity,
                notice_id=str(row.get("domestic_notice_id") or ""),
            )
            try:
                outcome = self.collector.collect_case(case)
            except Exception as exc:
                source_errors += 1
                outcome = {
                    "status": "collector_error",
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                    "case_key": key,
                }
            if str(outcome.get("status") or "") in {
                "complete", "tracking_postlisting", "waiting_for_domestic_open_price"
            }:
                collected += 1
            results.append({
                "case_key": key,
                "market": row.get("domestic_market"),
                "status": outcome.get("status"),
                "identity": {"status": identity_result.get("status"), "verified": True},
                "domestic_price": price_result,
                "sources_ok": int(outcome.get("sources_ok") or 0),
                "sources": outcome.get("sources") if isinstance(outcome.get("sources"), dict) else {},
                "error": outcome.get("error") or "",
            })

        summary = {
            "status": "researched" if picked else "waiting_for_cases",
            "paper_only": True,
            "can_place_orders": False,
            "seed": seed,
            "pending_cases": len(pending),
            "processed": len(picked),
            "identity_waiting": identity_waiting,
            "collected": collected,
            "source_errors": source_errors,
            "cursor": next_cursor,
            "results": results,
            "elapsed_seconds": round(time.time() - started, 3),
        }
        atomic_json(self.state_path, {**summary, "updated_at": time.time()})
        return summary


def main() -> None:
    cycle = ListingHistoryResearchCycle()
    try:
        print(json.dumps(cycle.run_once(), ensure_ascii=False, indent=2))
    finally:
        cycle.close()


if __name__ == "__main__":
    main()
