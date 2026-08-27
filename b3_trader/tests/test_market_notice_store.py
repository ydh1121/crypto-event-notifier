from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from b3_trader.market_notice import normalize_notice
from b3_trader.market_notice_store import MarketNoticeStore

KST = timezone(timedelta(hours=9))


def _ts(year: int, month: int, day: int, hour: int, minute: int = 0) -> float:
    return datetime(year, month, day, hour, minute, tzinfo=KST).timestamp()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_store_upgrades_existing_notice_table_with_timing_columns() -> None:
    conn = _conn()
    conn.execute(
        """CREATE TABLE market_notices(
            exchange TEXT NOT NULL, notice_id TEXT NOT NULL, title TEXT NOT NULL,
            url TEXT NOT NULL, published_at REAL NOT NULL DEFAULT 0,
            event_kind TEXT NOT NULL, symbols_json TEXT NOT NULL DEFAULT '[]',
            source TEXT NOT NULL, first_seen_at REAL NOT NULL, updated_at REAL NOT NULL,
            PRIMARY KEY(exchange,notice_id)
        )"""
    )
    MarketNoticeStore(conn)
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(market_notices)").fetchall()}
    assert {"announcement_at", "deposit_at", "trade_open_at", "termination_at"} <= columns


def test_store_persists_and_projects_structured_listing_times() -> None:
    conn = _conn()
    store = MarketNoticeStore(conn)
    published = _ts(2026, 8, 27, 9)
    notice = normalize_notice(
        exchange="bithumb",
        notice_id="100",
        title="뉴코인(NEW) 원화 마켓 추가",
        url="https://feed.bithumb.com/notice/100",
        published_at=published,
        source="test",
        detail_text="입금 지원 개시: 2026.08.27 14:00\n거래지원 개시: 2026.08.27 17:00",
    )
    store.ingest([notice], seen_at=published + 1)
    recent = store.recent("bithumb", 1)[0]
    assert recent["announcement_at"] == published
    assert recent["deposit_at"] == _ts(2026, 8, 27, 14)
    assert recent["trade_open_at"] == _ts(2026, 8, 27, 17)

    state = store.state_snapshot("bithumb")
    detail = state["details"]["KRW-NEW"]
    assert detail["announcement_at"] == published
    assert detail["trade_open_at"] == _ts(2026, 8, 27, 17)
