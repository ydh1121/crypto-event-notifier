from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from b3_trader.historical_listing_backfill import HistoricalListingBackfill, MAX_PAGES_PER_EXCHANGE
from b3_trader.market_notice import normalize_notice


class FakeSource:
    def __init__(self, exchange: str, symbol_prefix: str) -> None:
        self.exchange = exchange
        self.source = f"{exchange}_official_fake"
        self.symbol_prefix = symbol_prefix
        self.pages: list[int] = []

    def fetch_page(self, page: int):
        self.pages.append(page)
        symbol = f"{self.symbol_prefix}{page}"
        if self.exchange == "bithumb":
            title = f"테스트코인({symbol}) 원화 마켓 추가"
        else:
            title = f"테스트코인({symbol}) 신규 거래지원 (KRW 마켓)"
        return [
            normalize_notice(
                exchange=self.exchange,
                notice_id=f"{self.exchange}-{page}",
                title=title,
                url=f"https://example.test/{self.exchange}/{page}",
                published_at=1_700_000_000 + page,
                source=self.source,
            )
        ]


def _case_count(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM listing_history_cases").fetchone()[0])
    finally:
        conn.close()


def test_historical_backfill_is_bounded_and_advances_page_cursors(tmp_path) -> None:
    path = tmp_path / "research.sqlite3"
    state = tmp_path / "state.json"
    bithumb = FakeSource("bithumb", "B")
    upbit = FakeSource("upbit", "U")
    runner = HistoricalListingBackfill(
        path,
        sources=(bithumb, upbit),
        state_path=state,
        pages_per_exchange=2,
    )

    plan = runner.plan()
    assert plan["next_page"] == {"bithumb": 1, "upbit": 1}
    assert plan["pages_per_exchange"] == 2
    first = runner.run_once()
    assert first["status"] == "backfilled"
    assert first["listing_notices_fetched"] == 4
    assert first["listing_cases_seeded"] == 4
    assert first["listing_case_count_before"] == 0
    assert first["listing_case_count_after"] == 4
    assert first["paper_only"] is True
    assert first["shadow_only"] is True
    assert first["can_place_orders"] is False
    assert first["score_wired"] is False
    assert bithumb.pages == [1, 2]
    assert upbit.pages == [1, 2]

    stored = json.loads(state.read_text(encoding="utf-8"))
    assert stored["next_page"] == {"bithumb": 3, "upbit": 3}

    second = runner.run_once()
    assert second["listing_cases_seeded"] == 4
    assert second["listing_case_count_after"] == 8
    assert bithumb.pages == [1, 2, 3, 4]
    assert upbit.pages == [1, 2, 3, 4]
    assert _case_count(path) == 8


def test_historical_backfill_uses_final_krw_gate(tmp_path) -> None:
    class NonKrwSource:
        exchange = "bithumb"
        source = "bithumb_official_fake"

        def fetch_page(self, page: int):
            return [
                normalize_notice(
                    exchange="bithumb",
                    notice_id=str(page),
                    title="테스트코인(TEST) 신규 거래지원",
                    url="https://example.test/non-krw",
                    published_at=1_700_000_000,
                    source=self.source,
                )
            ]

    path = tmp_path / "non-krw.sqlite3"
    runner = HistoricalListingBackfill(
        path,
        sources=(NonKrwSource(),),
        state_path=tmp_path / "non-krw-state.json",
        pages_per_exchange=1,
    )
    result = runner.run_once()
    assert result["listing_notices_fetched"] == 1
    assert result["listing_cases_seeded"] == 0
    assert result["listing_case_count_after"] == 0


def test_historical_backfill_caps_pages_per_exchange(tmp_path) -> None:
    source = FakeSource("bithumb", "B")
    runner = HistoricalListingBackfill(
        tmp_path / "cap.sqlite3",
        sources=(source,),
        state_path=tmp_path / "cap-state.json",
        pages_per_exchange=999,
    )
    plan = runner.plan()
    assert plan["pages_per_exchange"] == MAX_PAGES_PER_EXCHANGE
