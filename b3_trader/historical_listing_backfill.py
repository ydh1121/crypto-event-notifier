from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin

import requests

from .auto_demo_v2 import DB_PATH
from .dex_launch_quality import evaluate_dex_launch_quality
from .http_retry import get_with_retry
from .listing_history_planner import is_krw_listing_notice
from .listing_history_store import ListingHistoryStore
from .market_notice import LISTING, MarketNotice, normalize_notice
from .market_notice_sources import (
    USER_AGENT,
    _BithumbLinkParser,
    _bithumb_detail_timestamp,
    _timestamp,
    _upbit_detail_text,
    _upbit_detail_timestamp,
    _upbit_public_notice_id,
    _upbit_rows,
)
from .market_notice_store import MarketNoticeStore
from .research_control import atomic_json

STATE_PATH = Path("b3_trader/data/research-platform/historical-listing-backfill-state.json")
DEFAULT_PAGES_PER_EXCHANGE = 4
MAX_PAGES_PER_EXCHANGE = 8
BITHUMB_ROWS_PER_PAGE_ESTIMATE = 20
UPBIT_ROWS_PER_PAGE = 30


class HistoricalListingSource(Protocol):
    exchange: str
    source: str

    def fetch_page(self, page: int) -> list[MarketNotice]: ...


class BithumbHistoricalListingSource:
    exchange = "bithumb"
    source = "bithumb_official_feed_historical"
    base_url = "https://feed.bithumb.com"

    def fetch_page(self, page: int) -> list[MarketNotice]:
        page = max(1, int(page))
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        response, _ = get_with_retry(
            f"{self.base_url}/notice",
            params={"category": "", "page": page},
            headers=headers,
            timeout=12,
            attempts=3,
        )
        parser = _BithumbLinkParser()
        parser.feed(response.text)
        output: list[MarketNotice] = []
        seen: set[str] = set()
        for href, title in parser.links:
            import re

            match = re.search(r"/notice/(\d+)", href)
            if not match or not title:
                continue
            notice_id = match.group(1)
            if notice_id in seen:
                continue
            seen.add(notice_id)
            preliminary = normalize_notice(
                exchange=self.exchange,
                notice_id=notice_id,
                title=title,
                url=urljoin(self.base_url, href),
                source=self.source,
            )
            if preliminary.event_kind != LISTING:
                continue
            published = 0.0
            detail_text = ""
            try:
                detail, _ = get_with_retry(
                    preliminary.url,
                    headers=headers,
                    timeout=10,
                    attempts=2,
                )
                detail_text = detail.text or ""
                published = _bithumb_detail_timestamp(detail_text)
            except requests.RequestException:
                pass
            output.append(
                normalize_notice(
                    exchange=self.exchange,
                    notice_id=notice_id,
                    title=title,
                    url=preliminary.url,
                    published_at=published,
                    source=self.source,
                    detail_text=detail_text,
                )
            )
        return output


class UpbitHistoricalListingSource:
    exchange = "upbit"
    source = "upbit_official_web_feed_historical"
    current_url = "https://api-manager.upbit.com/api/v1/announcements"
    legacy_url = "https://api-manager.upbit.com/api/v1/notices"

    def __init__(self, per_page: int = UPBIT_ROWS_PER_PAGE) -> None:
        self.per_page = max(10, min(50, int(per_page)))

    def _rows(self, page: int) -> list[dict[str, Any]]:
        page = max(1, int(page))
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        try:
            response, _ = get_with_retry(
                self.current_url,
                params={"os": "web", "page": page, "per_page": self.per_page, "category": "all"},
                headers=headers,
                timeout=12,
                attempts=3,
            )
            return _upbit_rows(response.json())
        except (requests.RequestException, ValueError):
            response, _ = get_with_retry(
                self.legacy_url,
                params={"page": page, "per_page": self.per_page, "thread_name": "general"},
                headers=headers,
                timeout=12,
                attempts=2,
            )
            return _upbit_rows(response.json())

    def _detail(self, *notice_ids: str) -> tuple[str, float]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        seen: set[str] = set()
        for notice_id in notice_ids:
            clean = str(notice_id or "").strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            for url, params in (
                (f"{self.current_url}/{clean}", {"os": "web"}),
                (f"{self.legacy_url}/{clean}", None),
            ):
                try:
                    response, _ = get_with_retry(
                        url,
                        params=params,
                        headers=headers,
                        timeout=10,
                        attempts=2,
                    )
                    payload = response.json()
                    text = _upbit_detail_text(payload)
                    published = _upbit_detail_timestamp(payload)
                    if text or published > 0:
                        return text, published
                except (requests.RequestException, ValueError):
                    continue
        return "", 0.0

    def fetch_page(self, page: int) -> list[MarketNotice]:
        output: list[MarketNotice] = []
        for row in self._rows(page):
            stable_id = str(row.get("id") or row.get("announcement_id") or row.get("notice_id") or "").strip()
            public_id = _upbit_public_notice_id(row) or stable_id
            title = str(row.get("title") or row.get("subject") or "").strip()
            if not stable_id or not title:
                continue
            published = _timestamp(
                row.get("created_at") or row.get("createdAt") or row.get("published_at") or row.get("date")
            )
            preliminary = normalize_notice(
                exchange=self.exchange,
                notice_id=stable_id,
                title=title,
                url=f"https://upbit.com/service_center/notice?id={public_id}",
                published_at=published,
                source=self.source,
            )
            if preliminary.event_kind != LISTING:
                continue
            detail_text, detail_published = self._detail(public_id, stable_id)
            output.append(
                normalize_notice(
                    exchange=self.exchange,
                    notice_id=stable_id,
                    title=title,
                    url=preliminary.url,
                    published_at=published or detail_published,
                    source=self.source,
                    detail_text=detail_text,
                )
            )
        return output


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


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


def _count_table(path: Path, table: str) -> int:
    if not path.exists():
        return 0
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) if exists else 0
    finally:
        conn.close()


class HistoricalListingBackfill:
    """Bounded official-notice history expansion for local listing/DEX research.

    This component only fetches public Bithumb/Upbit notices, persists normalized
    listing notices and creates pending listing-history cases. It does not resolve
    identity, fetch DEX pools, score markets, modify PAPER strategy, or place orders.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        sources: tuple[HistoricalListingSource, ...] | None = None,
        state_path: Path = STATE_PATH,
        pages_per_exchange: int = DEFAULT_PAGES_PER_EXCHANGE,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.sources = sources or (BithumbHistoricalListingSource(), UpbitHistoricalListingSource())
        self.state_path = Path(state_path)
        self.pages_per_exchange = max(1, min(MAX_PAGES_PER_EXCHANGE, int(pages_per_exchange)))

    def plan(self) -> dict[str, Any]:
        state = _read_state(self.state_path)
        cursors = state.get("next_page") if isinstance(state.get("next_page"), dict) else {}
        quality = evaluate_dex_launch_quality(self.path)
        return {
            "status": "planned",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "official_sources_only": True,
            "pages_per_exchange": self.pages_per_exchange,
            "max_pages_per_exchange": MAX_PAGES_PER_EXCHANGE,
            "next_page": {
                source.exchange: max(1, int(cursors.get(source.exchange) or 1))
                for source in self.sources
            },
            "listing_case_count": _count_table(self.path, "listing_history_cases"),
            "dex_case_count": _count_table(self.path, "dex_launch_case_status"),
            "quality": {
                "usable_case_count": int(quality.get("usable_case_count") or 0),
                "sample_ready": bool(quality.get("sample_ready")),
                "blocking_reasons": quality.get("blocking_reasons") or [],
            },
        }

    def _seed_cases(self, notices: list[MarketNotice]) -> int:
        if not notices:
            return 0
        store = ListingHistoryStore(self.path)
        seeded = 0
        try:
            for notice in notices:
                row = _notice_row(notice)
                if not is_krw_listing_notice(row):
                    continue
                announcement_at = float(notice.announcement_at or notice.published_at or 0.0)
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
                        domestic_open_at=float(notice.trade_open_at or 0.0),
                        domestic_open_price=0.0,
                        identity=None,
                        identity_verified=False,
                        status="pending_identity",
                    )
                    if not existed:
                        seeded += 1
        finally:
            store.close()
        return seeded

    def run_once(self) -> dict[str, Any]:
        started = time.time()
        before_cases = _count_table(self.path, "listing_history_cases")
        before_quality = evaluate_dex_launch_quality(self.path)
        state = _read_state(self.state_path)
        cursors = state.get("next_page") if isinstance(state.get("next_page"), dict) else {}
        next_page: dict[str, int] = {}
        source_results: dict[str, dict[str, Any]] = {}
        all_notices: list[MarketNotice] = []
        page_failures = 0

        for source in self.sources:
            start_page = max(1, int(cursors.get(source.exchange) or 1))
            fetched_pages = 0
            notices: list[MarketNotice] = []
            errors: list[str] = []
            for offset in range(self.pages_per_exchange):
                page = start_page + offset
                try:
                    rows = source.fetch_page(page)
                except Exception as exc:
                    page_failures += 1
                    errors.append(f"page={page}:{type(exc).__name__}:{exc}"[:300])
                    break
                notices.extend(rows)
                fetched_pages += 1
            next_page[source.exchange] = start_page + fetched_pages
            all_notices.extend(notices)
            source_results[source.exchange] = {
                "source": source.source,
                "start_page": start_page,
                "pages_fetched": fetched_pages,
                "next_page": next_page[source.exchange],
                "listing_notices": len(notices),
                "errors": errors,
            }

        inserted = 0
        if all_notices:
            conn = sqlite3.connect(str(self.path), timeout=30)
            conn.row_factory = sqlite3.Row
            try:
                result = MarketNoticeStore(conn).ingest(all_notices, seen_at=time.time())
                inserted = int(result.get("inserted") or 0)
            finally:
                conn.close()
        seeded = self._seed_cases(all_notices)
        after_cases = _count_table(self.path, "listing_history_cases")
        after_quality = evaluate_dex_launch_quality(self.path)
        payload = {
            "status": "partial" if page_failures else "backfilled",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_wired": False,
            "official_sources_only": True,
            "pages_per_exchange": self.pages_per_exchange,
            "source_results": source_results,
            "listing_notices_fetched": len(all_notices),
            "market_notices_inserted": inserted,
            "listing_cases_seeded": seeded,
            "listing_case_count_before": before_cases,
            "listing_case_count_after": after_cases,
            "dex_case_count": _count_table(self.path, "dex_launch_case_status"),
            "quality_before": {
                "usable_case_count": int(before_quality.get("usable_case_count") or 0),
                "sample_ready": bool(before_quality.get("sample_ready")),
            },
            "quality_after": {
                "usable_case_count": int(after_quality.get("usable_case_count") or 0),
                "sample_ready": bool(after_quality.get("sample_ready")),
            },
            "elapsed_seconds": round(time.time() - started, 3),
        }
        atomic_json(
            self.state_path,
            {
                "version": 1,
                "next_page": next_page,
                "updated_at": time.time(),
                "last_result": payload,
            },
        )
        return payload
