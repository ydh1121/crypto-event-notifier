from __future__ import annotations

import sqlite3

from b3_trader.exchange_public import PublicMarket
from b3_trader.market_lifecycle import CAUTION, LISTING_ANNOUNCED, NEW_LISTING, NORMAL, TERMINATION_SCHEDULED
from b3_trader.market_lifecycle_service import MarketLifecycleService
from b3_trader.market_notice import normalize_notice


def _service() -> MarketLifecycleService:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return MarketLifecycleService(conn)


def _market(symbol: str, *, warning: bool = False) -> PublicMarket:
    return PublicMarket(
        exchange="bithumb",
        market=f"KRW-{symbol}",
        symbol=symbol,
        name=symbol,
        warning=warning,
    )


def _notice(notice_id: str, title: str, published_at: float):
    return normalize_notice(
        exchange="bithumb",
        notice_id=notice_id,
        title=title,
        url=f"https://feed.bithumb.com/notice/{notice_id}",
        published_at=published_at,
        source="test",
    )


def test_caution_notice_and_release_compose_with_market_state() -> None:
    service = _service()
    service.observe_markets("bithumb", [_market("AAA")], observed_at=1_000.0)
    service.notice_store.ingest([_notice("10", "알파(AAA) 거래유의종목 지정", 1_100.0)], seen_at=1_101.0)
    caution = service.observe_markets("bithumb", [_market("AAA")], observed_at=1_200.0)
    assert caution["states"]["KRW-AAA"] == CAUTION

    service.notice_store.ingest([_notice("11", "알파(AAA) 유의종목 지정 해제", 1_300.0)], seen_at=1_301.0)
    released = service.observe_markets("bithumb", [_market("AAA")], observed_at=1_400.0)
    assert released["states"]["KRW-AAA"] == NORMAL


def test_caution_release_cannot_suppress_current_exchange_warning() -> None:
    service = _service()
    service.observe_markets("bithumb", [_market("AAA")], observed_at=1_000.0)
    service.notice_store.ingest([_notice("11", "알파(AAA) 유의종목 지정 해제", 1_300.0)], seen_at=1_301.0)
    snapshot = service.observe_markets("bithumb", [_market("AAA", warning=True)], observed_at=1_400.0)
    assert snapshot["states"]["KRW-AAA"] == CAUTION


def test_termination_notice_overrides_active_market_until_market_disappears() -> None:
    service = _service()
    service.observe_markets("bithumb", [_market("AAA")], observed_at=1_000.0)
    service.notice_store.ingest([_notice("12", "알파(AAA) 거래지원 종료 안내", 1_500.0)], seen_at=1_501.0)
    snapshot = service.observe_markets("bithumb", [_market("AAA")], observed_at=1_600.0)
    assert snapshot["states"]["KRW-AAA"] == TERMINATION_SCHEDULED


def test_listing_announcement_is_notice_only_until_market_is_observed() -> None:
    service = _service()
    service.observe_markets("bithumb", [_market("AAA")], observed_at=1_000.0)
    service.notice_store.ingest([_notice("13", "뉴코인(NEW) 원화 마켓 추가", 1_700.0)], seen_at=1_701.0)

    announced = service.observe_markets("bithumb", [_market("AAA")], observed_at=1_800.0)
    assert announced["states"]["KRW-NEW"] == LISTING_ANNOUNCED
    assert any(row["market"] == "KRW-NEW" for row in announced["notice_only"])

    listed = service.observe_markets("bithumb", [_market("AAA"), _market("NEW")], observed_at=1_900.0)
    assert listed["states"]["KRW-NEW"] == NEW_LISTING


def test_notice_without_official_timestamp_is_audited_but_not_applied() -> None:
    service = _service()
    service.observe_markets("bithumb", [_market("AAA")], observed_at=1_000.0)
    result = service.notice_store.ingest([_notice("14", "알파(AAA) 거래지원 종료 안내", 0.0)], seen_at=2_000.0)
    snapshot = service.observe_markets("bithumb", [_market("AAA")], observed_at=2_100.0)
    assert result["received"] == 1
    assert result["state_updates"] == 0
    assert snapshot["states"]["KRW-AAA"] == NORMAL


def test_older_notice_cannot_replace_newer_notice_state() -> None:
    service = _service()
    service.observe_markets("bithumb", [_market("AAA")], observed_at=1_000.0)
    service.notice_store.ingest([_notice("20", "알파(AAA) 유의종목 지정 해제", 3_000.0)], seen_at=3_001.0)
    service.notice_store.ingest([_notice("19", "알파(AAA) 거래유의종목 지정", 2_000.0)], seen_at=3_100.0)
    snapshot = service.observe_markets("bithumb", [_market("AAA")], observed_at=3_200.0)
    assert snapshot["states"]["KRW-AAA"] == NORMAL
