from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.listing_history_planner import ListingHistoryPlanner, is_krw_listing_notice
from b3_trader.market_notice import MarketNotice
from b3_trader.market_notice_store import MarketNoticeStore


def test_krw_listing_notice_filter_is_fail_closed() -> None:
    assert is_krw_listing_notice({"event_kind": "LISTING", "title": "ABC 원화 마켓 추가"}) is True
    assert is_krw_listing_notice({"event_kind": "LISTING", "title": "ABC 신규 거래지원 안내 (KRW, BTC, USDT 마켓)"}) is True
    assert is_krw_listing_notice({"event_kind": "LISTING", "title": "ABC 신규 거래지원 안내 (USDT 마켓)"}) is False
    assert is_krw_listing_notice({"event_kind": "CAUTION", "title": "ABC 원화 마켓 추가"}) is False


def test_planner_seeds_only_krw_listing_cases(tmp_path: Path) -> None:
    path = tmp_path / "listing.sqlite3"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    notice_store = MarketNoticeStore(conn)
    notice_store.ingest(
        [
            MarketNotice(
                exchange="bithumb",
                notice_id="b1",
                title="ABC(ABC) 원화 마켓 추가",
                url="https://example.test/b1",
                published_at=100,
                event_kind="LISTING",
                symbols=("ABC",),
                source="test",
                announcement_at=100,
                trade_open_at=200,
            ),
            MarketNotice(
                exchange="upbit",
                notice_id="u1",
                title="NEXO 신규 거래지원 안내 (USDT 마켓)",
                url="https://example.test/u1",
                published_at=101,
                event_kind="LISTING",
                symbols=("NEXO",),
                source="test",
                announcement_at=101,
            ),
            MarketNotice(
                exchange="upbit",
                notice_id="u2",
                title="FOLD 신규 거래지원 안내 (KRW, BTC, USDT 마켓)",
                url="https://example.test/u2",
                published_at=102,
                event_kind="LISTING",
                symbols=("FOLD",),
                source="test",
                announcement_at=102,
                trade_open_at=220,
            ),
        ],
        seen_at=300,
    )
    conn.close()

    planner = ListingHistoryPlanner(path)
    try:
        result = planner.seed_once()
        assert result["seeded_cases"] == 2
        assert result["skipped_non_krw"] == 1
        pending = planner.history_store.pending_cases()
        keys = {row["case_key"] for row in pending}
        assert "bithumb|KRW-ABC|notice:b1" in keys
        assert "upbit|KRW-FOLD|notice:u2" in keys
        assert all("NEXO" not in key for key in keys)
    finally:
        planner.close()
