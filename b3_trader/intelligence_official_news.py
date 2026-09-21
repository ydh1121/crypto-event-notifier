from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from .http_retry import get_with_retry
from .intelligence_event import IntelligenceEvent, normalize_intelligence_event
from .intelligence_source_registry import OFFICIAL_NEWS

USER_AGENT = "crypto-paper-phase5-intelligence/1.0"
MAX_RSS_BYTES = 2_000_000
DEFAULT_MAX_ITEMS = 100

_CRYPTO_TERMS = (
    "crypto",
    "digital asset",
    "digital commodity",
    "bitcoin",
    "ether",
    "ethereum",
    "stablecoin",
    "token",
    "blockchain",
    "perpetual",
)
_ENFORCEMENT_TERMS = (
    "charges",
    "charged",
    "fraud",
    "insider trading",
    "manipulative",
    "enforcement action",
    "settles charges",
    "settlement",
    "penalty",
    "penalties",
    "violations",
    "violating",
    "resolves actions",
    "orders ",
)
_SEC_REGULATION_TERMS = (
    "proposes",
    "adopts",
    "approves",
    "rescinds",
    "regulation",
    "rule",
    "securities laws",
    "exchange-traded fund",
    "etf",
    "market structure",
    "24-hour trading",
    "public comment",
)
_SEC_POLICY_TERMS = (
    "guidance",
    "policy statement",
    "clarifies",
    "interpretation",
    "staff statement",
)
_CFTC_REGULATION_TERMS = (
    "proposed rule",
    "rule changes",
    "public comment",
    "request for information",
    "listing of",
    "derivatives",
    "event contract",
    "prediction market",
    "designated contract market",
    "swap",
    "margin",
    "self-certification",
)
_CFTC_POLICY_TERMS = (
    "no-action",
    "policy statement",
    "issues advisory",
    "releases advisory",
    "publishes advisory",
    "staff advisory",
    "market advisory",
    "guidance",
    "interpretation",
)


@dataclass(frozen=True)
class OfficialNewsFeed:
    source_id: str
    url: str
    authority_tag: str
    allowed_hosts: tuple[str, ...]


SEC_FEED = OfficialNewsFeed(
    source_id="us_sec_press_releases",
    url="https://www.sec.gov/news/pressreleases.rss",
    authority_tag="SEC",
    allowed_hosts=("sec.gov",),
)
CFTC_FEED = OfficialNewsFeed(
    source_id="us_cftc_press_releases",
    url="https://www.cftc.gov/RSS/RSSGP/rssgp.xml",
    authority_tag="CFTC",
    allowed_hosts=("cftc.gov",),
)


def _plain_text(value: str) -> str:
    unescaped = html.unescape(str(value or ""))
    no_tags = re.sub(r"<[^>]+>", " ", unescaped)
    return re.sub(r"\s+", " ", no_tags).strip()


def _local_name(tag: str) -> str:
    return str(tag or "").rsplit("}", 1)[-1].lower()


def _child_text(node: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in list(node):
        if _local_name(child.tag) in wanted:
            return "".join(child.itertext()).strip()
    return ""


def _published_at(value: str) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if parsed is None:
        return 0.0
    if parsed.tzinfo is None:
        return 0.0
    return max(0.0, parsed.timestamp())


def _trusted_link(value: str, allowed_hosts: tuple[str, ...]) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text)
    host = str(parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        return ""
    if not any(host == allowed or host.endswith("." + allowed) for allowed in allowed_hosts):
        return ""
    return text


def _classify_title(source_id: str, title: str) -> tuple[str, str]:
    value = re.sub(r"\s+", " ", str(title or "")).strip().casefold()
    if not value:
        return "", ""
    if any(term in value for term in _ENFORCEMENT_TERMS):
        suffix = "SEC" if source_id == SEC_FEED.source_id else "CFTC"
        return f"US_{suffix}_ENFORCEMENT", "enforcement_keyword"
    if source_id == SEC_FEED.source_id:
        if any(term in value for term in _SEC_POLICY_TERMS):
            return "US_SEC_POLICY", "policy_keyword"
        if any(term in value for term in _SEC_REGULATION_TERMS):
            return "US_SEC_REGULATION", "regulation_keyword"
    elif source_id == CFTC_FEED.source_id:
        if any(term in value for term in _CFTC_POLICY_TERMS):
            return "US_CFTC_POLICY", "policy_keyword"
        if any(term in value for term in _CFTC_REGULATION_TERMS):
            return "US_CFTC_REGULATION", "regulation_keyword"
    return "", ""


def parse_official_press_release_rss(
    xml_text: str,
    *,
    feed: OfficialNewsFeed,
    received_at: float | None = None,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> list[IntelligenceEvent]:
    payload = str(xml_text or "")
    if len(payload.encode("utf-8", errors="ignore")) > MAX_RSS_BYTES:
        raise ValueError("official news RSS payload exceeds bounded size")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError("invalid official news RSS XML") from exc
    received = float(received_at if received_at is not None else time.time())
    limit = max(1, min(500, int(max_items)))
    output: list[IntelligenceEvent] = []
    seen_ids: set[str] = set()

    items = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    for item in items:
        title = _plain_text(_child_text(item, "title"))
        event_type, classifier = _classify_title(feed.source_id, title)
        if not event_type:
            continue
        link = _trusted_link(_child_text(item, "link"), feed.allowed_hosts)
        if not link:
            for child in list(item):
                if _local_name(child.tag) == "link":
                    link = _trusted_link(str(child.attrib.get("href") or ""), feed.allowed_hosts)
                    if link:
                        break
        if not link:
            continue
        guid = _plain_text(_child_text(item, "guid", "id"))
        external_id = guid or link
        if external_id in seen_ids:
            continue
        seen_ids.add(external_id)
        published = _published_at(_child_text(item, "pubdate", "published", "updated"))
        if published <= 0:
            # Reaction windows need an official publication clock; do not replace
            # it with received_at and pretend the item had a known source time.
            continue
        description = _plain_text(_child_text(item, "description", "summary", "content"))
        lower = title.casefold()
        crypto_match = any(term in lower for term in _CRYPTO_TERMS)
        entities = ("US", feed.authority_tag, "CRYPTO") if crypto_match else ("US", feed.authority_tag)
        output.append(
            normalize_intelligence_event(
                source_id=feed.source_id,
                source_family=OFFICIAL_NEWS,
                event_type=event_type,
                title=title,
                source_url=link,
                external_id=external_id,
                published_at=published,
                received_at=received,
                entities=entities,
                market_scope=("US_REGULATION", "CRYPTO"),
                raw_text=description,
                attributes={
                    "classifier": classifier,
                    "crypto_keyword_match": crypto_match,
                    "authority": feed.authority_tag,
                    "severity": None,
                    "direction": None,
                    "uncertainty": None,
                },
            )
        )
        if len(output) >= limit:
            break
    return output


class OfficialPressReleaseRssSource:
    """Bounded SEC/CFTC official press-release RSS adapter.

    This adapter classifies source-domain news candidates only. It does not infer
    bullish/bearish direction, severity, coin impact or trading score.
    """

    def __init__(self, feed: OfficialNewsFeed) -> None:
        self.feed = feed

    def fetch(self, *, received_at: float | None = None, max_items: int = DEFAULT_MAX_ITEMS) -> list[IntelligenceEvent]:
        current = float(received_at if received_at is not None else time.time())
        response, _ = get_with_retry(
            self.feed.url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.1",
            },
            timeout=12,
            attempts=3,
        )
        payload = str(response.text or "")
        if len(payload.encode("utf-8", errors="ignore")) > MAX_RSS_BYTES:
            raise ValueError("official news RSS payload exceeds bounded size")
        return parse_official_press_release_rss(
            payload,
            feed=self.feed,
            received_at=current,
            max_items=max_items,
        )


def default_official_news_sources() -> tuple[OfficialPressReleaseRssSource, OfficialPressReleaseRssSource]:
    return OfficialPressReleaseRssSource(SEC_FEED), OfficialPressReleaseRssSource(CFTC_FEED)
