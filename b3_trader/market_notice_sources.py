from __future__ import annotations

import html
import re
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import requests

from .http_retry import get_with_retry
from .market_notice import MarketNotice, OTHER, normalize_notice

USER_AGENT = "crypto-paper-market-notice-watch/1.0"
KST = timezone(timedelta(hours=9))


def _timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw > 10_000_000_000:
            raw /= 1000.0
        return max(0.0, raw)
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.timestamp()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=KST).timestamp()
        except ValueError:
            continue
    return 0.0


class _BithumbLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href = ""
        self._text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a" or self._href:
            return
        href = dict(attrs).get("href") or ""
        if re.search(r"/notice/\d+", href):
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._href:
            return
        title = re.sub(r"\s+", " ", " ".join(self._text)).strip()
        self.links.append((self._href, title))
        self._href = ""
        self._text = []


def _bithumb_detail_timestamp(text: str) -> float:
    plain = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    match = re.search(r"(20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", plain)
    return _timestamp(match.group(1)) if match else 0.0


def _upbit_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("list", "items", "announcements", "notices"):
            rows = data.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    for key in ("list", "items", "announcements", "notices"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _upbit_detail_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""
    for key in ("body", "content", "contents", "description", "text", "html"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("data", "notice", "announcement"):
        nested = _upbit_detail_text(payload.get(key))
        if nested:
            return nested
    return ""


def _upbit_detail_timestamp(payload: Any) -> float:
    if not isinstance(payload, dict):
        return 0.0
    for key in ("created_at", "createdAt", "published_at", "publishedAt", "date"):
        parsed = _timestamp(payload.get(key))
        if parsed > 0:
            return parsed
    for key in ("data", "notice", "announcement"):
        nested = _upbit_detail_timestamp(payload.get(key))
        if nested > 0:
            return nested
    return 0.0


def _upbit_public_notice_id(row: dict[str, Any]) -> str:
    """Extract the user-facing Upbit notice id while keeping row `id` as fallback."""
    for key in ("announcement_id", "notice_id", "public_id", "article_id", "post_id"):
        value = str(row.get(key) or "").strip()
        if value.isdigit():
            return value
    # Current list payloads can carry a user-facing notice URL in nested fields.
    stack: list[Any] = [row]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            stack.extend(value.values())
            continue
        if isinstance(value, (list, tuple)):
            stack.extend(value)
            continue
        text = str(value or "")
        match = re.search(r"upbit\.com/service_center/notice\?[^\s\"']*\bid=(\d+)", text, re.IGNORECASE)
        if match:
            return match.group(1)
    fallback = str(row.get("id") or "").strip()
    return fallback if fallback.isdigit() else ""


class BithumbNoticeSource:
    exchange = "bithumb"
    source = "bithumb_official_feed"
    base_url = "https://feed.bithumb.com"

    def __init__(self, pages: int = 2) -> None:
        self.pages = max(1, min(4, int(pages)))

    def fetch(self) -> list[MarketNotice]:
        candidates: dict[str, MarketNotice] = {}
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        for page in range(1, self.pages + 1):
            response, _ = get_with_retry(
                f"{self.base_url}/notice",
                params={"category": "", "page": page},
                headers=headers,
                timeout=12,
                attempts=3,
            )
            parser = _BithumbLinkParser()
            parser.feed(response.text)
            for href, title in parser.links:
                match = re.search(r"/notice/(\d+)", href)
                if not match or not title:
                    continue
                notice_id = match.group(1)
                notice = normalize_notice(
                    exchange=self.exchange,
                    notice_id=notice_id,
                    title=title,
                    url=urljoin(self.base_url, href),
                    source=self.source,
                )
                if notice.event_kind != OTHER:
                    candidates[notice_id] = notice

        output: list[MarketNotice] = []
        for notice in candidates.values():
            published = notice.published_at
            detail_text = ""
            try:
                detail, _ = get_with_retry(notice.url, headers=headers, timeout=10, attempts=2)
                detail_text = detail.text or ""
                if published <= 0:
                    published = _bithumb_detail_timestamp(detail_text)
            except requests.RequestException:
                pass
            output.append(
                normalize_notice(
                    exchange=notice.exchange,
                    notice_id=notice.notice_id,
                    title=notice.title,
                    url=notice.url,
                    published_at=published,
                    source=notice.source,
                    detail_text=detail_text,
                )
            )
        return output


class UpbitNoticeSource:
    exchange = "upbit"
    source = "upbit_official_web_feed"
    current_url = "https://api-manager.upbit.com/api/v1/announcements"
    legacy_url = "https://api-manager.upbit.com/api/v1/notices"

    def __init__(self, per_page: int = 30) -> None:
        self.per_page = max(10, min(50, int(per_page)))

    def _request_rows(self) -> list[dict[str, Any]]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        try:
            response, _ = get_with_retry(
                self.current_url,
                params={"os": "web", "page": 1, "per_page": self.per_page, "category": "all"},
                headers=headers,
                timeout=12,
                attempts=3,
            )
            return _upbit_rows(response.json())
        except (requests.RequestException, ValueError):
            response, _ = get_with_retry(
                self.legacy_url,
                params={"page": 1, "per_page": self.per_page, "thread_name": "general"},
                headers=headers,
                timeout=12,
                attempts=2,
            )
            return _upbit_rows(response.json())

    def _detail(self, *notice_ids: str) -> tuple[str, float]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        seen: set[str] = set()
        for notice_id in notice_ids:
            clean_id = str(notice_id or "").strip()
            if not clean_id or clean_id in seen:
                continue
            seen.add(clean_id)
            candidates = (
                (f"{self.current_url}/{clean_id}", {"os": "web"}),
                (f"{self.legacy_url}/{clean_id}", None),
            )
            for url, params in candidates:
                try:
                    response, _ = get_with_retry(
                        url,
                        params=params,
                        headers=headers,
                        timeout=10,
                        attempts=2,
                    )
                    payload = response.json()
                    text = _upbit_detail_text(payload)
                    published = _upbit_detail_timestamp(payload)
                    if text or published > 0:
                        return text, published
                except (requests.RequestException, ValueError):
                    continue
        return "", 0.0

    def fetch(self) -> list[MarketNotice]:
        output: list[MarketNotice] = []
        for row in self._request_rows():
            stable_id = str(row.get("id") or row.get("announcement_id") or row.get("notice_id") or "").strip()
            public_id = _upbit_public_notice_id(row) or stable_id
            title = str(row.get("title") or row.get("subject") or "").strip()
            if not stable_id or not title:
                continue
            published = _timestamp(
                row.get("created_at") or row.get("createdAt") or row.get("published_at") or row.get("date")
            )
            preliminary = normalize_notice(
                exchange=self.exchange,
                notice_id=stable_id,
                title=title,
                url=f"https://upbit.com/service_center/notice?id={public_id}",
                published_at=published,
                source=self.source,
            )
            if preliminary.event_kind == OTHER:
                continue
            detail_text, detail_published = self._detail(public_id, stable_id)
            output.append(
                normalize_notice(
                    exchange=self.exchange,
                    notice_id=stable_id,
                    title=title,
                    url=preliminary.url,
                    published_at=published or detail_published,
                    source=self.source,
                    detail_text=detail_text,
                )
            )
        return output


def default_notice_sources() -> tuple[BithumbNoticeSource, UpbitNoticeSource]:
    return BithumbNoticeSource(), UpbitNoticeSource()
