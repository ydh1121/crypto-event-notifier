from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .listing_history_store import ListingHistoryStore
from .market_notice_store import MarketNoticeStore


_KRW_PATTERNS = (
    re.compile(r"(?:원화|KRW)\s*(?:마켓|market)", re.IGNORECASE),
    re.compile(r"\(\s*KRW(?:\s*[,/)]|\s*$)", re.IGNORECASE),
    re.compile(r"\bKRW\s*,", re.IGNORECASE),
)


def is_krw_listing_notice(row: dict[str, Any]) -> bool:
    if str(row.get("event_kind") or "").upper() != "LISTING":
        return False
    title = str(row.get("title") or "")
    if not title:
        return False
    compact = re.sub(r"\s+", "", title)
    # Old normalized rows may still have event_kind=LISTING even after the
    # classifier is tightened. A promotional event is never a listing case.
    if "이벤트" in compact:
        return False
    return any(pattern.search(title) for pattern in _KRW_PATTERNS)


class ListingHistoryPlanner:
    """Create pending listing-history cases from normalized official notices.

    Planning does not resolve identity and does not call foreign exchanges. It
    only creates stable notice-id-backed cases that later research can enrich.
    """

    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.notice_store = MarketNoticeStore(self.conn)
        self.history_store = ListingHistoryStore(self.path)

    def close(self) -> None:
        self.history_store.close()
        self.conn.close()

    def _reject_existing_notice_cases(self, exchange: str, notice: dict[str, Any]) -> int:
        notice_id = str(notice.get("notice_id") or "").strip()
        symbols = notice.get("symbols") if isinstance(notice.get("symbols"), list) else []
        rejected = 0
        if not notice_id:
            return rejected
        for raw_symbol in symbols:
            symbol = str(raw_symbol or "").strip().upper()
            if not symbol or not symbol.replace("-", "").isalnum():
                continue
            key = self.history_store.case_key(
                exchange,
                f"KRW-{symbol}",
                domestic_notice_id=notice_id,
            )
            cursor = self.history_store.conn.execute(
                "SELECT status FROM listing_history_cases WHERE case_key=?",
                (key,),
            ).fetchone()
            if cursor is None or str(cursor["status"] or "") == "rejected_notice":
                continue
            self.history_store.update_case_status(key, "rejected_notice")
            rejected += 1
        return rejected

    def seed_once(self, *, per_exchange_limit: int = 120) -> dict[str, Any]:
        seeded = 0
        considered = 0
        skipped_non_krw = 0
        rejected_cases = 0
        by_exchange: dict[str, int] = {}
        for exchange in ("bithumb", "upbit"):
            count = 0
            for notice in self.notice_store.recent(exchange, limit=per_exchange_limit):
                if str(notice.get("event_kind") or "").upper() != "LISTING":
                    continue
                considered += 1
                if not is_krw_listing_notice(notice):
                    skipped_non_krw += 1
                    rejected_cases += self._reject_existing_notice_cases(exchange, notice)
                    continue
                notice_id = str(notice.get("notice_id") or "")
                announcement_at = float(notice.get("announcement_at") or notice.get("published_at") or 0.0)
                open_at = float(notice.get("trade_open_at") or 0.0)
                symbols = notice.get("symbols") if isinstance(notice.get("symbols"), list) else []
                for raw_symbol in symbols:
                    symbol = str(raw_symbol or "").strip().upper()
                    if not symbol or not symbol.replace("-", "").isalnum():
                        continue
                    self.history_store.upsert_case(
                        domestic_exchange=exchange,
                        domestic_market=f"KRW-{symbol}",
                        domestic_notice_id=notice_id,
                        symbol=symbol,
                        announcement_at=announcement_at,
                        domestic_open_at=open_at,
                        domestic_open_price=0.0,
                        identity=None,
                        identity_verified=False,
                        status="pending_identity",
                    )
                    seeded += 1
                    count += 1
            by_exchange[exchange] = count
        return {
            "status": "seeded",
            "considered_listing_notices": considered,
            "seeded_cases": seeded,
            "skipped_non_krw": skipped_non_krw,
            "rejected_cases": rejected_cases,
            "by_exchange": by_exchange,
            "paper_only": True,
            "can_place_orders": False,
        }
