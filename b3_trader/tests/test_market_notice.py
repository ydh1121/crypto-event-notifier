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
from b3_trader.market_notice_sources import (
    UpbitNoticeSource,
    _BithumbLinkParser,
    _upbit_detail_text,
    _upbit_detail_timestamp,
    _upbit_rows,
)


def test_notice_title_classification() -> None:
    assert classify_notice_title("프로미스(PROM) 원화 마켓 추가") == LISTING
    assert classify_notice_title("만트라(OM) 거래유의종목 지정") == CAUTION_NOTICE
    assert classify_notice_title("테스트(AAA) 유의 종목 지정 해제") == CAUTION_RELEASE
    assert classify_notice_title("테스트(AAA) 거래지원 종료 안내") == TERMINATION
    assert classify_notice_title("서비스 점검 안내") == OTHER


def test_promotional_listing_event_is_not_a_listing_notice() -> None:
    assert classify_notice_title("블록스트리트(BSB) 원화마켓 추가 기념 에어드랍 이벤트") == OTHER
    assert classify_notice_title("ABC(ABC) 신규 거래지원 기념 이벤트") == OTHER


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


def test_upbit_detail_extractors_are_shape_tolerant() -> None:
    payload = {
        "data": {
            "body": "<p>거래지원 개시: 2026-08-27 17:00</p>",
            "created_at": "2026-08-27T09:00:00+09:00",
        }
    }
    assert "거래지원 개시" in _upbit_detail_text(payload)
    assert _upbit_detail_timestamp(payload) > 0


def test_upbit_detail_falls_back_to_legacy_endpoint(monkeypatch) -> None:
    calls: list[str] = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, **kwargs):
        calls.append(url)
        if "/announcements/" in url:
            return FakeResponse({"data": {}}), 0
        return FakeResponse(
            {
                "data": {
                    "body": "<p>거래지원 개시: 2026-08-23 12:30</p>",
                    "created_at": "2026-08-23T10:14:11+09:00",
                }
            }
        ), 0

    monkeypatch.setattr("b3_trader.market_notice_sources.get_with_retry", fake_get)
    text, published = UpbitNoticeSource()._detail("6503")
    assert "12:30" in text
    assert published > 0
    assert calls == [
        "https://api-manager.upbit.com/api/v1/announcements/6503",
        "https://api-manager.upbit.com/api/v1/notices/6503",
    ]
