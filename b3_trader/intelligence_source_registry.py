from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

MACRO_CALENDAR = "macro_calendar"
US_MARKET_REFERENCE = "us_market_reference"
OFFICIAL_NEWS = "official_news"

ICS = "ics"
HTML_REFERENCE = "html_reference"
RSS = "rss"
JSON_API = "json_api"

_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{2,63}$")
_ALLOWED_FAMILIES = {MACRO_CALENDAR, US_MARKET_REFERENCE, OFFICIAL_NEWS}
_ALLOWED_TRANSPORTS = {ICS, HTML_REFERENCE, RSS, JSON_API}


@dataclass(frozen=True)
class IntelligenceSource:
    source_id: str
    name: str
    family: str
    authority: str
    url: str
    transport: str
    event_types: tuple[str, ...]
    market_scope: tuple[str, ...]
    official: bool = True
    collection_enabled: bool = False
    notes: str = ""


def validate_source(source: IntelligenceSource) -> None:
    if not _SOURCE_ID_RE.fullmatch(str(source.source_id or "")):
        raise ValueError(f"invalid intelligence source_id: {source.source_id!r}")
    if source.family not in _ALLOWED_FAMILIES:
        raise ValueError(f"invalid intelligence source family: {source.family!r}")
    if source.transport not in _ALLOWED_TRANSPORTS:
        raise ValueError(f"invalid intelligence source transport: {source.transport!r}")
    parsed = urlparse(str(source.url or ""))
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"intelligence source must use https: {source.url!r}")
    if not str(source.name or "").strip() or not str(source.authority or "").strip():
        raise ValueError("intelligence source name/authority must be present")
    if not source.event_types:
        raise ValueError(f"intelligence source must declare event types: {source.source_id}")


DEFAULT_INTELLIGENCE_SOURCES: tuple[IntelligenceSource, ...] = (
    IntelligenceSource(
        source_id="us_bls_release_calendar",
        name="U.S. Bureau of Labor Statistics release calendar",
        family=MACRO_CALENDAR,
        authority="U.S. Bureau of Labor Statistics",
        url="https://www.bls.gov/schedule/news_release/bls.ics",
        transport=ICS,
        event_types=("US_CPI", "US_EMPLOYMENT", "US_ECI", "US_PPI"),
        market_scope=("GLOBAL", "CRYPTO"),
        notes="Official BLS calendar feed. Adapter preserves the documented Eastern release clock and source timestamps.",
    ),
    IntelligenceSource(
        source_id="us_bea_release_schedule",
        name="U.S. Bureau of Economic Analysis release schedule",
        family=MACRO_CALENDAR,
        authority="U.S. Bureau of Economic Analysis",
        url="https://www.bea.gov/news/schedule",
        transport=HTML_REFERENCE,
        event_types=("US_PCE", "US_GDP", "US_PERSONAL_INCOME", "US_TRADE"),
        market_scope=("GLOBAL", "CRYPTO"),
        notes="Official BEA release schedule. Bounded adapter preserves explicit Eastern release times and leaves TBA times unknown.",
    ),
    IntelligenceSource(
        source_id="us_fed_fomc_calendar",
        name="Federal Reserve FOMC calendar and releases",
        family=MACRO_CALENDAR,
        authority="Board of Governors of the Federal Reserve System",
        url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        transport=HTML_REFERENCE,
        event_types=("FOMC_MEETING", "FOMC_STATEMENT", "FOMC_MINUTES", "FOMC_PROJECTIONS"),
        market_scope=("GLOBAL", "US_EQUITY", "CRYPTO"),
        notes="Official FOMC calendar. Date-only meeting evidence is stored without inventing a statement or minutes clock time.",
    ),
    IntelligenceSource(
        source_id="us_nasdaq_composite",
        name="Nasdaq Composite official index reference",
        family=US_MARKET_REFERENCE,
        authority="Nasdaq",
        url="https://indexes.nasdaq.com/Index/Overview/COMP",
        transport=HTML_REFERENCE,
        event_types=("NASDAQ_COMPOSITE",),
        market_scope=("US_EQUITY", "CRYPTO"),
        notes="Official index reference only. Actual observations require a separately reviewed provider with timestamp, latency and data-rights metadata.",
    ),
    IntelligenceSource(
        source_id="us_sp500",
        name="S&P 500 official index reference",
        family=US_MARKET_REFERENCE,
        authority="S&P Dow Jones Indices",
        url="https://www.spglobal.com/spdji/en/indices/equity/sp-500/",
        transport=HTML_REFERENCE,
        event_types=("SP500",),
        market_scope=("US_EQUITY", "CRYPTO"),
        notes="Official index reference only. Actual observations require a separately reviewed provider with timestamp, latency and data-rights metadata.",
    ),
    IntelligenceSource(
        source_id="us_cboe_vix",
        name="Cboe VIX official index reference",
        family=US_MARKET_REFERENCE,
        authority="Cboe Global Markets",
        url="https://www.cboe.com/en/tradable-products/vix/",
        transport=HTML_REFERENCE,
        event_types=("VIX",),
        market_scope=("US_EQUITY", "CRYPTO"),
        notes="Official volatility-index reference. Delayed/reference data must not be presented as real-time without explicit provider metadata.",
    ),
    IntelligenceSource(
        source_id="us_sec_press_releases",
        name="SEC press releases RSS",
        family=OFFICIAL_NEWS,
        authority="U.S. Securities and Exchange Commission",
        url="https://www.sec.gov/news/pressreleases.rss",
        transport=RSS,
        event_types=("US_SEC_REGULATION", "US_SEC_ENFORCEMENT", "US_SEC_POLICY"),
        market_scope=("US_REGULATION", "CRYPTO"),
        notes="Official SEC press-release RSS. Adapter stores policy/regulatory/enforcement candidates only; direction and severity remain unset until reaction validation.",
    ),
    IntelligenceSource(
        source_id="us_cftc_press_releases",
        name="CFTC general press releases RSS",
        family=OFFICIAL_NEWS,
        authority="U.S. Commodity Futures Trading Commission",
        url="https://www.cftc.gov/RSS/RSSGP/rssgp.xml",
        transport=RSS,
        event_types=("US_CFTC_REGULATION", "US_CFTC_ENFORCEMENT", "US_CFTC_POLICY"),
        market_scope=("US_REGULATION", "CRYPTO"),
        notes="Official CFTC general press-release RSS. Adapter stores policy/regulatory/enforcement candidates only; direction and severity remain unset until reaction validation.",
    ),
)


def default_intelligence_sources() -> tuple[IntelligenceSource, ...]:
    seen: set[str] = set()
    for source in DEFAULT_INTELLIGENCE_SOURCES:
        validate_source(source)
        if source.source_id in seen:
            raise ValueError(f"duplicate intelligence source_id: {source.source_id}")
        seen.add(source.source_id)
    return DEFAULT_INTELLIGENCE_SOURCES


def intelligence_source_map() -> dict[str, IntelligenceSource]:
    return {source.source_id: source for source in default_intelligence_sources()}
