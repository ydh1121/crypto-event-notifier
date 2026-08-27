from __future__ import annotations

from dataclasses import dataclass

import pytest

from b3_trader.market_notice import normalize_notice
from b3_trader.market_notice_collector import MarketNoticeCollector


@dataclass
class _GoodSource:
    exchange: str = "bithumb"
    source: str = "test_good"

    def fetch(self):
        return [
            normalize_notice(
                exchange=self.exchange,
                notice_id="100",
                title="알파(AAA) 거래유의종목 지정",
                url="https://example.test/100",
                published_at=1_000.0,
                source=self.source,
            )
        ]


@dataclass
class _FailSource:
    exchange: str = "upbit"
    source: str = "test_fail"

    def fetch(self):
        raise RuntimeError("source unavailable")


def test_partial_source_failure_does_not_block_other_exchange(tmp_path) -> None:
    collector = MarketNoticeCollector(
        tmp_path / "paper.sqlite3",
        sources=(_GoodSource(), _FailSource()),
    )
    try:
        result = collector.run_once()
        assert result["status"] == "partial"
        assert result["sources_ok"] == 1
        assert result["sources_failed"] == 1
        assert result["received"] == 1
        assert result["state_updates"] == 1
        snapshot = collector._notice_store().state_snapshot("bithumb")
        assert snapshot["states"]["KRW-AAA"] == "CAUTION"
    finally:
        collector.close()


def test_all_sources_failing_marks_component_run_failed(tmp_path) -> None:
    collector = MarketNoticeCollector(tmp_path / "paper.sqlite3", sources=(_FailSource(),))
    try:
        with pytest.raises(RuntimeError, match="all market notice sources failed"):
            collector.run_once()
    finally:
        collector.close()
