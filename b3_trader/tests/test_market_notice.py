from __future__ import annotations

from b3_trader.market_notice import (
    CAUTION_NOTICE,
    CAUTION_RELEASE,
    LISTING,
    OTHER,
    TERMINATION,
    classify_notice_title,
    extract_notice_symbols,
)
from b3_trader.market_notice_sources import _BithumbLinkParser, _upbit_rows


def test_notice_title_classification() -> None:
    assert classify_notice_title("프로미스(PROM) 원화 마켓 추가") == LISTING
    assert classify_notice_title("만트라(OM) 거래유의종목 지정") == CAUTION_NOTICE
    assert classify_notice_title("테스트(AAA) 유의 종목 지정 해제") == CAUTION_RELEASE
    assert classify_notice_title("테스트(AAA) 거래지원 종료 안내") == TERMINATION
    assert classify_notice_title("서비스 점검 안내") == OTHER


def test_notice_symbol_extraction_supports_multiple_assets() -> None:
    assert extract_notice_symbols("알파(AAA), 베타(BBB) 거래유의종목 지정") == ("AAA", "BBB")
    assert extract_notice_symbols("중복(AAA) 및 다시(AAA) 안내") == ("AAA",)


def test_bithumb_notice_link_parser_is_bounded_to_notice_links() -> None:
    parser = _BithumbLinkParser()
    parser.feed(
        """
        <div><a href="/notice/1649999"><span>프로미스(PROM)</span> 원화 마켓 추가</a></div>
        <a href="/event/123">이벤트</a>
        <a href="https://feed.bithumb.com/notice/1650000">만트라(OM) 거래유의종목 지정</a>
        """
    )
    assert parser.links == [
        ("/notice/1649999", "프로미스(PROM) 원화 마켓 추가"),
        ("https://feed.bithumb.com/notice/1650000", "만트라(OM) 거래유의종목 지정"),
    ]


def test_upbit_rows_accepts_current_and_legacy_shapes() -> None:
    current = {"data": {"list": [{"id": 1, "title": "A"}]}}
    legacy = {"data": [{"id": 2, "title": "B"}]}
    root = {"notices": [{"id": 3, "title": "C"}]}
    assert [row["id"] for row in _upbit_rows(current)] == [1]
    assert [row["id"] for row in _upbit_rows(legacy)] == [2]
    assert [row["id"] for row in _upbit_rows(root)] == [3]
