from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Protocol

from .auto_demo_v2 import DB_PATH
from .dex_shadow_score_v2_preregistration import FORWARD_CUTOFF_TS, FORWARD_CUTOFF_UTC
from .historical_listing_backfill import BithumbHistoricalListingSource, UpbitHistoricalListingSource
from .listing_history_planner import is_krw_listing_notice
from .listing_history_store import ListingHistoryStore
from .market_notice import MarketNotice
from .market_notice_store import MarketNoticeStore
from .research_control import atomic_json


BUILD67_VERSION = 1
BUILD67_NAME = "dex_forward_sample_intake_v1"
STATE_PATH = Path("b3_trader/data/research-platform/forward-sample-intake-build67-state.json")
DEFAULT_PAGES_PER_EXCHANGE = 2
MAX_PAGES_PER_EXCHANGE = 3


class ForwardNoticeSource(Protocol):
    exchange: str
    source: str

    def fetch_page(self, page: int) -> list[MarketNotice]: ...


def _notice_row(notice: MarketNotice) -> dict[str, Any]:
    return {
        "exchange": notice.exchange,
        "notice_id": notice.notice_id,
        "title": notice.title,
        "url": notice.url,
        "published_at": notice.published_at,
        "event_kind": notice.event_kind,
        "symbols": list(notice.symbols),
        "source": notice.source,
        "announcement_at": notice.announcement_at,
        "trade_open_at": notice.trade_open_at,
    }


def _forward_basis(notice: MarketNotice) -> str:
    open_at = float(notice.trade_open_at or 0.0)
    announcement_at = float(notice.announcement_at or notice.published_at or 0.0)
    if open_at >= FORWARD_CUTOFF_TS:
        return "trade_open_at_gte_cutoff"
    if open_at <= 0 and announcement_at >= FORWARD_CUTOFF_TS:
        return "announcement_gte_cutoff_open_time_pending"
    return ""


def _count_existing_forward_cases(path: Path) -> dict[str, int]:
    if not path.exists():
        return {
            "confirmed_forward_open_cases": 0,
            "pending_open_time_forward_candidates": 0,
            "total_forward_intake_cases": 0,
        }
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='listing_history_cases'"
        ).fetchone()
        if not exists:
            return {
                "confirmed_forward_open_cases": 0,
                "pending_open_time_forward_candidates": 0,
                "total_forward_intake_cases": 0,
            }
        confirmed = int(
            conn.execute(
                "SELECT COUNT(*) FROM listing_history_cases WHERE domestic_open_at>=?",
                (FORWARD_CUTOFF_TS,),
            ).fetchone()[0]
        )
        pending = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM listing_history_cases
                WHERE domestic_open_at<=0 AND announcement_at>=?
                """,
                (FORWARD_CUTOFF_TS,),
            ).fetchone()[0]
        )
        return {
            "confirmed_forward_open_cases": confirmed,
            "pending_open_time_forward_candidates": pending,
            "total_forward_intake_cases": confirmed + pending,
        }
    finally:
        conn.close()


class ForwardSampleIntake:
    """Bounded latest-official-notice intake for Build65/66 forward validation.

    This is deliberately separate from Build47 historical pagination. It always
    reads the newest official Bithumb/Upbit pages starting at page 1 and never
    reads or mutates the historical backfill cursor. Run mode only persists
    normalized official notices and seeds pending listing-history cases. Identity,
    DEX research, scoring, PAPER decisions, and orders are out of scope.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        sources: tuple[ForwardNoticeSource, ...] | None = None,
        state_path: Path = STATE_PATH,
        pages_per_exchange: int = DEFAULT_PAGES_PER_EXCHANGE,
    ) -> None:
        self.path = Path(path)
        self.sources = sources or (BithumbHistoricalListingSource(), UpbitHistoricalListingSource())
        self.state_path = Path(state_path)
        self.pages_per_exchange = max(1, min(MAX_PAGES_PER_EXCHANGE, int(pages_per_exchange)))

    def plan(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "planned",
            "build67_version": BUILD67_VERSION,
            "build67_name": BUILD67_NAME,
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "read_only_plan": True,
            "network_fetches": False,
            "official_sources_only": True,
            "latest_pages_start_at": 1,
            "pages_per_exchange": self.pages_per_exchange,
            "hard_max_pages_per_exchange": MAX_PAGES_PER_EXCHANGE,
            "forward_boundary": {
                "cutoff_utc": FORWARD_CUTOFF_UTC,
                "cutoff_unix": FORWARD_CUTOFF_TS,
                "confirmed_rule": "trade_open_at_gte_cutoff",
                "pending_open_rule": "trade_open_at_missing_and_announcement_gte_cutoff",
                "build66_final_score_eligibility_unchanged": "domestic_open_at_gte_forward_cutoff",
            },
            "existing_forward_counts": _count_existing_forward_cases(self.path),
            "isolation": {
                "build47_historical_cursor_read": False,
                "build47_historical_cursor_mutation": False,
                "generic_listing_history_research_enabled": False,
                "generic_dex_launch_research_enabled": False,
            },
            "run_scope": {
                "persist_official_notices": True,
                "seed_pending_identity_cases": True,
                "resolve_identity": False,
                "fetch_dex": False,
                "calculate_v2_score": False,
                "paper_ab": False,
            },
            "review": {"next_action": "run_build67_bounded_latest_official_intake"},
        }

    def _seed_cases(self, notices: list[tuple[MarketNotice, str]]) -> dict[str, Any]:
        store = ListingHistoryStore(self.path)
        seeded = 0
        existing = 0
        pending_open = 0
        confirmed_open = 0
        preview: list[dict[str, Any]] = []
        try:
            for notice, basis in notices:
                announcement_at = float(notice.announcement_at or notice.published_at or 0.0)
                open_at = float(notice.trade_open_at or 0.0)
                for raw_symbol in notice.symbols:
                    symbol = str(raw_symbol or "").strip().upper()
                    if not symbol or not symbol.replace("-", "").isalnum():
                        continue
                    case_key = store.case_key(
                        notice.exchange,
                        f"KRW-{symbol}",
                        domestic_notice_id=notice.notice_id,
                    )
                    existed = store.conn.execute(
                        "SELECT 1 FROM listing_history_cases WHERE case_key=?", (case_key,)
                    ).fetchone()
                    store.upsert_case(
                        domestic_exchange=notice.exchange,
                        domestic_market=f"KRW-{symbol}",
                        domestic_notice_id=notice.notice_id,
                        symbol=symbol,
                        announcement_at=announcement_at,
                        domestic_open_at=open_at,
                        domestic_open_price=0.0,
                        identity=None,
                        identity_verified=False,
                        status="pending_identity",
                    )
                    if existed:
                        existing += 1
                    else:
                        seeded += 1
                    if open_at >= FORWARD_CUTOFF_TS:
                        confirmed_open += 1
                    else:
                        pending_open += 1
                    if len(preview) < 10:
                        preview.append(
                            {
                                "case_key": case_key,
                                "exchange": notice.exchange,
                                "market": f"KRW-{symbol}",
                                "notice_id": notice.notice_id,
                                "announcement_at": announcement_at,
                                "domestic_open_at": open_at,
                                "forward_basis": basis,
                                "new_case": not bool(existed),
                            }
                        )
        finally:
            store.close()
        return {
            "seeded_new_cases": seeded,
            "existing_cases_seen": existing,
            "confirmed_forward_open_case_rows": confirmed_open,
            "pending_open_time_case_rows": pending_open,
            "preview": preview,
        }

    def run_once(self) -> dict[str, Any]:
        started = time.time()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        before_counts = _count_existing_forward_cases(self.path)
        source_results: dict[str, dict[str, Any]] = {}
        eligible_by_key: dict[tuple[str, str], tuple[MarketNotice, str]] = {}
        page_failures = 0

        for source in self.sources:
            fetched_pages = 0
            fetched_notices = 0
            eligible_notices = 0
            errors: list[str] = []
            for page in range(1, self.pages_per_exchange + 1):
                try:
                    rows = source.fetch_page(page)
                except Exception as exc:
                    page_failures += 1
                    errors.append(f"page={page}:{type(exc).__name__}:{exc}"[:300])
                    break
                fetched_pages += 1
                fetched_notices += len(rows)
                for notice in rows:
                    row = _notice_row(notice)
                    if not is_krw_listing_notice(row):
                        continue
                    basis = _forward_basis(notice)
                    if not basis:
                        continue
                    key = (str(notice.exchange), str(notice.notice_id))
                    eligible_by_key[key] = (notice, basis)
                    eligible_notices += 1
            source_results[source.exchange] = {
                "source": source.source,
                "start_page": 1,
                "pages_fetched": fetched_pages,
                "notices_fetched": fetched_notices,
                "forward_eligible_notice_hits": eligible_notices,
                "errors": errors,
            }

        eligible = list(eligible_by_key.values())
        eligible.sort(
            key=lambda item: (
                -float(item[0].trade_open_at or item[0].announcement_at or item[0].published_at or 0.0),
                item[0].exchange,
                item[0].notice_id,
            )
        )

        inserted = 0
        if eligible:
            conn = sqlite3.connect(str(self.path), timeout=30)
            conn.row_factory = sqlite3.Row
            try:
                result = MarketNoticeStore(conn).ingest([notice for notice, _ in eligible], seen_at=time.time())
                inserted = int(result.get("inserted") or 0)
            finally:
                conn.close()
        seed = self._seed_cases(eligible) if eligible else {
            "seeded_new_cases": 0,
            "existing_cases_seen": 0,
            "confirmed_forward_open_case_rows": 0,
            "pending_open_time_case_rows": 0,
            "preview": [],
        }
        after_counts = _count_existing_forward_cases(self.path)
        payload = {
            "ok": page_failures == 0,
            "status": "intake_complete" if page_failures == 0 else "intake_partial",
            "build67_version": BUILD67_VERSION,
            "build67_name": BUILD67_NAME,
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "official_sources_only": True,
            "network_fetches": True,
            "latest_pages_start_at": 1,
            "pages_per_exchange": self.pages_per_exchange,
            "hard_max_pages_per_exchange": MAX_PAGES_PER_EXCHANGE,
            "forward_boundary": {
                "cutoff_utc": FORWARD_CUTOFF_UTC,
                "cutoff_unix": FORWARD_CUTOFF_TS,
                "build66_final_score_eligibility_unchanged": "domestic_open_at_gte_forward_cutoff",
            },
            "isolation": {
                "build47_historical_cursor_read": False,
                "build47_historical_cursor_mutation": False,
                "generic_listing_history_research_enabled": False,
                "generic_dex_launch_research_enabled": False,
            },
            "scope": {
                "identity_resolution_calls": 0,
                "dex_fetch_calls": 0,
                "score_calculations": 0,
                "paper_ab_wired": False,
                "strategy_signal_mutation": False,
                "position_sizing_mutation": False,
                "cloudflare_publishing": False,
            },
            "source_results": source_results,
            "unique_forward_notices": len(eligible),
            "market_notices_inserted": inserted,
            "seed": seed,
            "forward_counts_before": before_counts,
            "forward_counts_after": after_counts,
            "elapsed_seconds": round(time.time() - started, 3),
            "review": {
                "build68_forward_enrichment_allowed": bool(after_counts["total_forward_intake_cases"] > 0),
                "next_action": (
                    "design_build68_forward_only_identity_listing_dex_enrichment"
                    if after_counts["total_forward_intake_cases"] > 0
                    else "repeat_build67_when_new_official_listing_notices_exist"
                ),
            },
        }
        atomic_json(
            self.state_path,
            {
                "version": BUILD67_VERSION,
                "updated_at": time.time(),
                "last_result": payload,
            },
        )
        return payload
