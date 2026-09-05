from __future__ import annotations

import re
from dataclasses import dataclass

from .market_lifecycle import CAUTION, LISTING_ANNOUNCED, NORMAL, TERMINATION_SCHEDULED
from .market_notice_timing import parse_notice_timing

LISTING = "LISTING"
CAUTION_NOTICE = "CAUTION"
CAUTION_RELEASE = "CAUTION_RELEASE"
TERMINATION = "TERMINATION"
OTHER = "OTHER"

_SYMBOL_RE = re.compile(r"\(([A-Z0-9][A-Z0-9._-]{0,19})\)")


@dataclass(frozen=True)
class MarketNotice:
    exchange: str
    notice_id: str
    title: str
    url: str
    published_at: float
    event_kind: str
    symbols: tuple[str, ...]
    source: str
    announcement_at: float = 0.0
    deposit_at: float = 0.0
    trade_open_at: float = 0.0
    termination_at: float = 0.0


def extract_notice_symbols(title: str) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for match in _SYMBOL_RE.findall(str(title or "").upper()):
        symbol = match.strip(" ._-")
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        result.append(symbol)
    return tuple(result)


def classify_notice_title(title: str) -> str:
    compact = re.sub(r"\s+", "", str(title or ""))
    if not compact:
        return OTHER
    if "거래지원종료" in compact or "거래종료" in compact:
        return TERMINATION
    if any(token in compact for token in ("거래유의종목지정해제", "유의종목지정해제", "유의종목해제", "유의해제")):
        return CAUTION_RELEASE
    if any(token in compact for token in ("거래유의종목지정", "유의종목지정", "유의촉구")):
        return CAUTION_NOTICE

    # Promotional notices often repeat phrases such as "원화마켓 추가" or
    # "신규 거래지원" in an airdrop/reward event title. Those are not listing
    # lifecycle events and must never seed listing-history research cases.
    if "이벤트" in compact and any(
        token in compact for token in ("원화마켓추가", "KRW마켓추가", "신규거래지원", "거래지원개시")
    ):
        return OTHER

    if any(token in compact for token in ("원화마켓추가", "KRW마켓추가", "신규거래지원", "거래지원개시")):
        return LISTING
    return OTHER


def lifecycle_state_for_notice(event_kind: str) -> str:
    return {
        LISTING: LISTING_ANNOUNCED,
        CAUTION_NOTICE: CAUTION,
        CAUTION_RELEASE: NORMAL,
        TERMINATION: TERMINATION_SCHEDULED,
    }.get(str(event_kind or "").upper(), "")


def normalize_notice(
    *,
    exchange: str,
    notice_id: str,
    title: str,
    url: str,
    published_at: float = 0.0,
    source: str = "official_notice",
    detail_text: str = "",
) -> MarketNotice:
    published = max(0.0, float(published_at or 0.0))
    timing = parse_notice_timing(detail_text, published_at=published)
    return MarketNotice(
        exchange=str(exchange or "").strip().lower(),
        notice_id=str(notice_id or "").strip(),
        title=str(title or "").strip(),
        url=str(url or "").strip(),
        published_at=published,
        event_kind=classify_notice_title(title),
        symbols=extract_notice_symbols(title),
        source=str(source or "official_notice"),
        announcement_at=timing.announcement_at,
        deposit_at=timing.deposit_at,
        trade_open_at=timing.trade_open_at,
        termination_at=timing.termination_at,
    )
