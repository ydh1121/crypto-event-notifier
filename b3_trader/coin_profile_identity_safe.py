from __future__ import annotations

import html
import re
from io import BytesIO
from typing import Any

import requests

from .coin_profile_enricher import (
    BITHUMB_MANUAL_URL,
    CG_DETAIL_URL,
    CG_SEARCH_URL,
    USER_AGENT,
    CoinProfileEnricher,
    _clean_html,
    _normalize,
    _safe_url,
    _text,
)

_GENERIC_NAME_WORDS = {
    "token", "coin", "network", "protocol", "finance", "foundation",
    "project", "ecosystem", "platform", "labs", "dao",
}
_MANUAL_HEADER_LIMIT = 5000
_MANUAL_HEADER_MARKERS = (
    r"가\s*상\s*자\s*산\s*소\s*개",
    r"가\s*상\s*자\s*산\s*기\s*본\s*정\s*보",
)


def _name_tokens(value: Any) -> list[str]:
    words = re.findall(r"[a-z0-9]+", _text(value).lower())
    return [word for word in words if word not in _GENERIC_NAME_WORDS]


def project_name_matches(expected: Any, candidate: Any) -> bool:
    left = _normalize(expected)
    right = _normalize(candidate)
    if not left or not right:
        return False
    if left == right:
        return True
    if len(left) >= 5 and len(right) >= 5 and (left in right or right in left):
        return True
    a, b = set(_name_tokens(expected)), set(_name_tokens(candidate))
    if not a or not b:
        return False
    overlap = len(a & b) / max(len(a), len(b))
    return overlap >= 0.8


def row_matches_candidate(row: dict[str, str], candidate_name: Any) -> bool:
    return project_name_matches(row.get("english_name"), candidate_name)


def _manual_header(text: str) -> str:
    """Return only the identity/header area before the manual description."""

    visible = text[:_MANUAL_HEADER_LIMIT]
    positions: list[int] = []
    for pattern in _MANUAL_HEADER_MARKERS:
        match = re.search(pattern, visible, re.I)
        if match and match.start() > 0:
            positions.append(match.start())
    if not positions:
        return ""
    return visible[: min(positions)]


def _identity_pattern(value: Any) -> str:
    raw = _text(value)
    tokens = re.findall(r"[A-Za-z0-9가-힣]+", raw)
    if not tokens:
        return ""
    if len(tokens) > 1:
        body = r"[\s·•._\-–—/:：()\[\]]*".join(re.escape(token) for token in tokens)
    else:
        token = tokens[0]
        if re.fullmatch(r"[가-힣]{2,}", token):
            body = r"[\s·•._\-–—/:：()\[\]]*".join(re.escape(char) for char in token)
        else:
            body = re.escape(token)
    return rf"(?<![A-Za-z0-9가-힣]){body}(?![A-Za-z0-9가-힣])"


def _identity_phrase_in_text(text: str, value: Any) -> bool:
    pattern = _identity_pattern(value)
    return bool(pattern and re.search(pattern, text, re.I))


def _manual_identity_matches(row: dict[str, str], text: str) -> bool:
    """Require project identity in the PDF header, not merely a body mention."""

    header = _manual_header(text)
    if not header:
        return False
    korean_name = _text(row.get("korean_name"))
    english_name = _text(row.get("english_name"))
    symbol = _text(row.get("symbol")).upper()
    korean_hit = _identity_phrase_in_text(header, korean_name)
    english_hit = _identity_phrase_in_text(header, english_name)
    symbol_hit = bool(
        len(symbol) >= 2
        and re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", header.upper())
    )
    if korean_hit and english_hit:
        return True
    if symbol_hit and (korean_hit or english_hit):
        return True
    return False


def _manual_intro_identity_matches(row: dict[str, str], intro: str) -> bool:
    """Require the description itself to start with the current exchange asset."""

    probe = _normalize(_clean_html(intro, 320))
    if not probe:
        return False
    korean = _normalize(row.get("korean_name"))
    english = _normalize(row.get("english_name"))
    symbol = _text(row.get("symbol")).lower()
    if korean and probe.startswith(korean):
        return True
    if english and probe.startswith(english):
        return True
    if len(symbol) >= 2 and probe.startswith(symbol):
        return True
    return False


def _drop_ungrounded_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Do not present taxonomy/template guesses as researched business facts."""

    if int(profile.get("source_count") or 0) > 0:
        return profile
    safe = dict(profile)
    for key in (
        "description_ko", "description_en", "business_summary_ko", "business_summary_en",
        "homepage", "image_url", "official_docs", "whitepaper", "source_code",
    ):
        safe[key] = ""
    safe["categories"] = []
    safe["tags"] = []
    safe["community"] = []
    safe["evidence"] = []
    safe["research_status"] = "unresolved"
    safe["summary_source"] = ""
    safe["match_confidence"] = 0.0
    safe["ungrounded_content_removed"] = True
    return safe


class IdentitySafeCoinProfileEnricher(CoinProfileEnricher):
    """Coin profiler that refuses same-ticker / different-project matches."""

    def __init__(self) -> None:
        super().__init__()
        self._upbit_names: dict[str, str] | None = None

    @staticmethod
    def _choose_cmc(raw: Any, row: dict[str, str]) -> tuple[dict[str, Any] | None, float]:
        candidates = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
        candidates = [item for item in candidates if isinstance(item, dict)]
        matched = [item for item in candidates if row_matches_candidate(row, item.get("name"))]
        if not matched:
            return None, 0.0
        wanted = _normalize(row.get("english_name"))
        matched.sort(key=lambda item: 0 if wanted and _normalize(item.get("name")) == wanted else 1)
        chosen = matched[0]
        confidence = 0.99 if wanted and _normalize(chosen.get("name")) == wanted else 0.94
        return chosen, confidence

    def _coingecko(self, row: dict[str, str]) -> tuple[dict[str, Any] | None, float]:
        response = self.session.get(CG_SEARCH_URL, params={"query": row["symbol"]}, timeout=15)
        if not response.ok:
            return None, 0.0
        payload = response.json()
        candidates = [
            item for item in (payload.get("coins") or [])
            if isinstance(item, dict)
            and _text(item.get("symbol")).upper() == row["symbol"]
            and row_matches_candidate(row, item.get("name"))
        ]
        if not candidates:
            return None, 0.0
        wanted = _normalize(row.get("english_name"))
        candidates.sort(key=lambda item: (
            0 if wanted and _normalize(item.get("name")) == wanted else 1,
            int(item.get("market_cap_rank") or 999999),
        ))
        chosen = candidates[0]
        coin_id = _text(chosen.get("id"))
        if not coin_id:
            return None, 0.0
        detail = self.session.get(
            CG_DETAIL_URL.format(coin_id=coin_id),
            params={
                "localization": "true", "tickers": "false", "market_data": "false",
                "community_data": "false", "developer_data": "false", "sparkline": "false",
            },
            timeout=18,
        )
        if not detail.ok:
            return None, 0.0
        value = detail.json()
        if not isinstance(value, dict) or not row_matches_candidate(row, value.get("name")):
            return None, 0.0
        confidence = 0.99 if wanted and _normalize(value.get("name")) == wanted else 0.94
        return value, confidence

    def _read_manual_pdf_checked(self, url: str, row: dict[str, str]) -> dict[str, str]:
        try:
            from pypdf import PdfReader

            response = self.session.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            if len(response.content) > 8_000_000:
                return {}
            reader = PdfReader(BytesIO(response.content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:6])
        except Exception:
            return {}
        if not _manual_identity_matches(row, text):
            return {}
        text = re.sub(r"[ \t]+", " ", text)
        intro = re.search(r"가\s*상\s*자\s*산\s*소\s*개\s*(.*?)\s*가\s*상\s*자\s*산\s*기\s*본\s*정\s*보", text, re.S)
        purpose = re.search(r"가\s*상\s*자\s*산\s*의\s*이\s*용\s*목\s*적\s*(.*?)\s*가\s*상\s*자\s*산\s*백\s*서", text, re.S)
        homepage = re.search(r"가\s*상\s*자\s*산\s*홈\s*페\s*이\s*지\s*(https?://\S+)", text, re.S)
        whitepaper = re.search(r"가\s*상\s*자\s*산\s*백\s*서\s*(https?://\S+)", text, re.S)
        intro_text = _clean_html(intro.group(1) if intro else "", 1800)
        if not intro_text or not _manual_intro_identity_matches(row, intro_text):
            return {}
        return {
            "description_ko": intro_text,
            "purpose_ko": _clean_html(purpose.group(1) if purpose else "", 500),
            "homepage": _safe_url((homepage.group(1) if homepage else "").rstrip(".,)")),
            "whitepaper": _safe_url((whitepaper.group(1) if whitepaper else "").rstrip(".,)")),
            "identity_verified": "strict_header_and_intro",
        }

    def _bithumb_manual(self, row: dict[str, str]) -> dict[str, str]:
        if row["exchange"] != "bithumb":
            return {}
        for params in ({"keyword": row["symbol"]}, {"search": row["symbol"]}):
            try:
                response = self.session.get(BITHUMB_MANUAL_URL, params=params, timeout=12)
                if not response.ok:
                    continue
            except requests.RequestException:
                continue
            html_text = response.text
            urls = re.findall(r"https://feed-content\.bithumb\.com/cms/[^\"'<>\s]+\.pdf", html_text, flags=re.I)
            if not urls:
                urls = [html.unescape(x) for x in re.findall(r"href=[\"']([^\"']+\.pdf)[\"']", html_text, flags=re.I)]
            seen: set[str] = set()
            for candidate in urls[:12]:
                candidate = _safe_url(candidate)
                if not candidate or candidate in seen:
                    continue
                seen.add(candidate)
                result = self._read_manual_pdf_checked(candidate, row)
                if result:
                    result["url"] = candidate
                    return result
        return {}

    def _upbit_project_matches(self, row: dict[str, str]) -> bool:
        if self._upbit_names is None:
            names: dict[str, str] = {}
            try:
                for item in self.upbit.krw_markets(details=True):
                    market = _text(item.get("market")).upper()
                    if market.startswith("KRW-"):
                        names[market.removeprefix("KRW-")] = _text(item.get("english_name"))
            except Exception:
                names = {}
            self._upbit_names = names
        candidate = self._upbit_names.get(row["symbol"], "")
        return bool(candidate and project_name_matches(row.get("english_name"), candidate))

    def _build_profile(self, row: dict[str, str], cmc_raw: Any, *, upbit_available: bool) -> dict[str, Any]:
        safe_upbit = bool(upbit_available and self._upbit_project_matches(row))
        profile = super()._build_profile(row, cmc_raw, upbit_available=safe_upbit)
        profile["english_name"] = row.get("english_name") or profile.get("english_name")
        profile["korean_name"] = row.get("korean_name") or profile.get("korean_name")
        profile = _drop_ungrounded_profile(profile)
        profile["identity_guard"] = "exchange_name_verified"
        return profile
