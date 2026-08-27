from __future__ import annotations

from datetime import datetime, timedelta, timezone

from b3_trader.market_notice_timing import parse_notice_timing

KST = timezone(timedelta(hours=9))


def _ts(year: int, month: int, day: int, hour: int, minute: int = 0) -> float:
    return datetime(year, month, day, hour, minute, tzinfo=KST).timestamp()


def test_listing_notice_extracts_deposit_and_trade_open_times() -> None:
    published = _ts(2026, 8, 27, 9)
    timing = parse_notice_timing(
        """
        <p>입금 지원 개시: 2026.08.27(목) 14:00</p>
        <p>원화 마켓 거래지원 개시: 2026-08-27 17:00:00</p>
        """,
        published_at=published,
    )
    assert timing.announcement_at == published
    assert timing.deposit_at == _ts(2026, 8, 27, 14)
    assert timing.trade_open_at == _ts(2026, 8, 27, 17)
    assert timing.termination_at == 0.0


def test_revised_listing_notice_uses_final_active_clock_time() -> None:
    published = _ts(2026, 8, 11, 10, 17)
    timing = parse_notice_timing(
        "거래 개시 시점 : 2026.08.11(화) 오후 2:00 -> 오후 4:00 -> 오후 5:00 예정",
        published_at=published,
    )
    assert timing.trade_open_at == _ts(2026, 8, 11, 17)


def test_revised_listing_notice_with_strikethrough_markup_uses_final_clock_time() -> None:
    published = _ts(2026, 8, 11, 10, 17)
    timing = parse_notice_timing(
        "거래 개시 시점 : 2026.08.11(화) <del>오후 2:00</del> -> <del>오후 4:00</del> -> 오후 5:00 예정",
        published_at=published,
    )
    assert timing.trade_open_at == _ts(2026, 8, 11, 17)


def test_termination_notice_extracts_korean_datetime() -> None:
    published = _ts(2026, 8, 27, 10)
    timing = parse_notice_timing(
        "거래지원 종료 일시: 2026년 9월 2일 오후 3시 30분",
        published_at=published,
    )
    assert timing.termination_at == _ts(2026, 9, 2, 15, 30)


def test_month_day_time_rolls_into_next_year_when_needed() -> None:
    published = _ts(2026, 12, 30, 9)
    timing = parse_notice_timing(
        "거래 지원 개시: 1월 2일 오후 2시 00분",
        published_at=published,
    )
    assert timing.trade_open_at == _ts(2027, 1, 2, 14)


def test_date_only_text_is_not_invented_as_midnight() -> None:
    published = _ts(2026, 8, 27, 9)
    timing = parse_notice_timing(
        "거래지원 종료 예정일은 2026년 9월 2일입니다.",
        published_at=published,
    )
    assert timing.termination_at == 0.0


def test_withdrawal_end_does_not_become_market_termination() -> None:
    published = _ts(2026, 8, 27, 9)
    timing = parse_notice_timing(
        "출금 지원 종료: 2026-09-02 15:00",
        published_at=published,
    )
    assert timing.termination_at == 0.0
