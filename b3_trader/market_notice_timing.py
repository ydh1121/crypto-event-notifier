from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class NoticeTiming:
    announcement_at: float = 0.0
    deposit_at: float = 0.0
    trade_open_at: float = 0.0
    termination_at: float = 0.0


DEPOSIT_LABELS = (
    "입금 지원 개시",
    "입금지원 개시",
    "입금 지원 시작",
    "입금지원 시작",
    "입금 개시",
    "입금 오픈",
    "입출금 지원 개시",
)
TRADE_OPEN_LABELS = (
    "원화 마켓 거래지원 개시",
    "원화마켓 거래지원 개시",
    "거래지원 개시",
    "거래 지원 개시",
    "거래지원 시작",
    "거래 지원 시작",
    "거래 개시",
    "거래 시작",
)
TERMINATION_LABELS = (
    "거래지원 종료",
    "거래 지원 종료",
    "거래 종료",
)

_FULL_DATETIME_RE = re.compile(
    r"(?P<year>20\d{2})\s*(?:년|[.\-/])\s*"
    r"(?P<month>\d{1,2})\s*(?:월|[.\-/])\s*"
    r"(?P<day>\d{1,2})\s*(?:일)?\s*"
    r"(?:\([^)]{0,12}\)\s*)?"
    r"(?P<ampm>오전|오후)?\s*"
    r"(?P<hour>\d{1,2})\s*(?:시|:)\s*"
    r"(?P<minute>\d{1,2})\s*(?:분)?"
    r"(?:\s*:\s*(?P<second>\d{1,2}))?"
)
_MONTH_DAY_DATETIME_RE = re.compile(
    r"(?<!\d)(?P<month>\d{1,2})\s*월\s*"
    r"(?P<day>\d{1,2})\s*일\s*"
    r"(?:\([^)]{0,12}\)\s*)?"
    r"(?P<ampm>오전|오후)?\s*"
    r"(?P<hour>\d{1,2})\s*(?:시|:)\s*"
    r"(?P<minute>\d{1,2})\s*(?:분)?"
    r"(?:\s*:\s*(?P<second>\d{1,2}))?"
)


def _plain_text(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"</(?:p|div|li|tr|h\d)\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def _to_timestamp(match: re.Match[str], *, base_ts: float) -> float:
    groups = match.groupdict()
    year_text = groups.get("year")
    if year_text:
        year = int(year_text)
    elif base_ts > 0:
        year = datetime.fromtimestamp(base_ts, KST).year
    else:
        return 0.0
    month = int(groups["month"])
    day = int(groups["day"])
    hour = int(groups["hour"])
    minute = int(groups["minute"])
    second = int(groups.get("second") or 0)
    ampm = groups.get("ampm") or ""
    if ampm == "오후" and hour < 12:
        hour += 12
    elif ampm == "오전" and hour == 12:
        hour = 0
    try:
        value = datetime(year, month, day, hour, minute, second, tzinfo=KST).timestamp()
    except ValueError:
        return 0.0
    if not year_text and base_ts > 0 and value < base_ts - 7 * 86400:
        try:
            value = datetime(year + 1, month, day, hour, minute, second, tzinfo=KST).timestamp()
        except ValueError:
            return 0.0
    return value


def _first_datetime(value: str, *, base_ts: float) -> float:
    for pattern in (_FULL_DATETIME_RE, _MONTH_DAY_DATETIME_RE):
        match = pattern.search(value)
        if match:
            parsed = _to_timestamp(match, base_ts=base_ts)
            if parsed > 0:
                return parsed
    return 0.0


def _after_labels(text: str, labels: Iterable[str], *, base_ts: float, window: int = 220) -> float:
    best_position: int | None = None
    best_value = 0.0
    for label in labels:
        start = 0
        while True:
            position = text.find(label, start)
            if position < 0:
                break
            segment = text[position : position + max(80, int(window))]
            parsed = _first_datetime(segment, base_ts=base_ts)
            if parsed > 0 and (best_position is None or position < best_position):
                best_position = position
                best_value = parsed
            start = position + max(1, len(label))
    return best_value


def parse_notice_timing(detail_text: str, *, published_at: float = 0.0) -> NoticeTiming:
    """Extract lifecycle times near explicit Korean notice labels.

    Publication time is the announcement timestamp. Other fields are populated
    only when an explicit date *and clock time* appears near the matching label.
    Date-only wording is intentionally left unresolved rather than inventing a
    midnight timestamp.
    """
    announcement_at = max(0.0, float(published_at or 0.0))
    text = _plain_text(detail_text)
    if not text:
        return NoticeTiming(announcement_at=announcement_at)
    return NoticeTiming(
        announcement_at=announcement_at,
        deposit_at=_after_labels(text, DEPOSIT_LABELS, base_ts=announcement_at),
        trade_open_at=_after_labels(text, TRADE_OPEN_LABELS, base_ts=announcement_at),
        termination_at=_after_labels(text, TERMINATION_LABELS, base_ts=announcement_at),
    )
