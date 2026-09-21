from __future__ import annotations

import sqlite3

import pytest

import b3_trader.intelligence_official_news as news
from b3_trader.intelligence_event_store import IntelligenceEventStore
from b3_trader.intelligence_official_news import (
    CFTC_FEED,
    SEC_FEED,
    OfficialPressReleaseRssSource,
    parse_official_press_release_rss,
)
from b3_trader.intelligence_source_registry import RSS, intelligence_source_map


def _sec_fixture() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item>
        <title>SEC Clarifies the Application of Federal Securities Laws to Crypto Assets</title>
        <link>https://www.sec.gov/newsroom/press-releases/2026-30</link>
        <guid>https://www.sec.gov/newsroom/press-releases/2026-30</guid>
        <pubDate>Tue, 17 Mar 2026 14:00:00 -0400</pubDate>
        <description><![CDATA[<p>Official SEC release about crypto assets.</p>]]></description>
      </item>
      <item>
        <title>SEC Charges Example Firm With Fraud</title>
        <link>https://www.sec.gov/newsroom/press-releases/2026-99</link>
        <guid>sec-2026-99</guid>
        <pubDate>Wed, 18 Mar 2026 09:30:00 -0400</pubDate>
        <description>Enforcement release</description>
      </item>
      <item>
        <title>SEC Appoints Example Person as Director</title>
        <link>https://www.sec.gov/newsroom/press-releases/2026-100</link>
        <guid>sec-2026-100</guid>
        <pubDate>Thu, 19 Mar 2026 09:30:00 -0400</pubDate>
      </item>
      <item>
        <title>SEC Proposes New Regulation Crypto Assets</title>
        <link>https://evil.example/news/2026-101</link>
        <guid>sec-2026-101</guid>
        <pubDate>Fri, 20 Mar 2026 09:30:00 -0400</pubDate>
      </item>
      <item>
        <title>SEC Adopts Final Rule for Market Structure</title>
        <link>https://www.sec.gov/newsroom/press-releases/2026-102</link>
        <guid>sec-2026-102</guid>
      </item>
    </channel></rss>"""


def _cftc_fixture() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item>
        <title>CFTC Issues Policy Statement Concerning the Listing of Perpetual Contracts</title>
        <link>https://www.cftc.gov/PressRoom/PressReleases/9242-26</link>
        <guid>9242-26</guid>
        <pubDate>Fri, 29 May 2026 12:00:00 -0400</pubDate>
        <description>Official policy statement</description>
      </item>
      <item>
        <title>CFTC Resolves Actions Against Former Alameda CEO, and Alameda and FTX Co-Founder</title>
        <link>https://www.cftc.gov/PressRoom/PressReleases/9285-26</link>
        <guid>9285-26</guid>
        <pubDate>Wed, 19 Aug 2026 10:00:00 -0400</pubDate>
        <description>Official enforcement release</description>
      </item>
      <item>
        <title>Chairman Announces Agenda for Advisory Committee Meeting</title>
        <link>https://www.cftc.gov/PressRoom/PressReleases/9999-26</link>
        <guid>9999-26</guid>
        <pubDate>Thu, 20 Aug 2026 10:00:00 -0400</pubDate>
      </item>
    </channel></rss>"""


def test_registry_uses_official_sec_and_cftc_rss_transport() -> None:
    sources = intelligence_source_map()
    assert sources["us_sec_press_releases"].transport == RSS
    assert sources["us_sec_press_releases"].url == "https://www.sec.gov/news/pressreleases.rss"
    assert sources["us_cftc_press_releases"].transport == RSS
    assert sources["us_cftc_press_releases"].url == "https://www.cftc.gov/RSS/RSSGP/rssgp.xml"
    assert sources["us_sec_press_releases"].collection_enabled is False
    assert sources["us_cftc_press_releases"].collection_enabled is False


def test_sec_rss_filters_non_market_items_and_keeps_timestamped_policy_enforcement_candidates() -> None:
    events = parse_official_press_release_rss(_sec_fixture(), feed=SEC_FEED, received_at=2_000_000_000)
    assert [event.event_type for event in events] == ["US_SEC_POLICY", "US_SEC_ENFORCEMENT"]
    assert events[0].entities == ("US", "SEC", "CRYPTO")
    assert events[0].attributes["crypto_keyword_match"] is True
    assert events[0].attributes["severity"] is None
    assert events[0].attributes["direction"] is None
    assert events[0].published_at > 0
    assert events[0].source_url.startswith("https://www.sec.gov/")
    assert events[0].raw_text == "Official SEC release about crypto assets."


def test_cftc_rss_classifies_policy_and_enforcement_without_bullish_bearish_guess() -> None:
    events = parse_official_press_release_rss(_cftc_fixture(), feed=CFTC_FEED, received_at=2_000_000_000)
    assert [event.event_type for event in events] == ["US_CFTC_POLICY", "US_CFTC_ENFORCEMENT"]
    assert events[0].attributes["crypto_keyword_match"] is True
    assert events[1].attributes["direction"] is None
    assert events[1].attributes["uncertainty"] is None


def test_official_news_parser_rejects_untrusted_links_missing_source_time_invalid_xml_and_oversize() -> None:
    events = parse_official_press_release_rss(_sec_fixture(), feed=SEC_FEED, received_at=2_000_000_000)
    titles = {event.title for event in events}
    assert "SEC Proposes New Regulation Crypto Assets" not in titles
    assert "SEC Adopts Final Rule for Market Structure" not in titles

    with pytest.raises(ValueError, match="invalid official news RSS XML"):
        parse_official_press_release_rss("<rss>", feed=SEC_FEED)
    with pytest.raises(ValueError, match="bounded size"):
        parse_official_press_release_rss("X" * (news.MAX_RSS_BYTES + 1), feed=SEC_FEED)


def test_official_news_source_uses_shared_bounded_retry_without_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        text = _sec_fixture()

    def fake_get(url: str, **kwargs: object):
        calls.append({"url": url, **kwargs})
        return Response(), 0

    monkeypatch.setattr(news, "get_with_retry", fake_get)
    events = OfficialPressReleaseRssSource(SEC_FEED).fetch(received_at=2_000_000_000, max_items=10)
    assert len(events) == 2
    assert len(calls) == 1
    assert calls[0]["url"] == SEC_FEED.url
    assert calls[0]["timeout"] == 12
    assert calls[0]["attempts"] == 3


def test_sec_and_cftc_events_fit_shared_phase5_store_and_remain_unscored() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = IntelligenceEventStore(conn)
    events = [
        *parse_official_press_release_rss(_sec_fixture(), feed=SEC_FEED, received_at=2_000_000_000),
        *parse_official_press_release_rss(_cftc_fixture(), feed=CFTC_FEED, received_at=2_000_000_000),
    ]
    assert store.ingest(events, seen_at=2_000_000_001) == {
        "received": 4,
        "inserted": 4,
        "updated": 0,
    }
    rows = store.recent(source_family="official_news", limit=10, now=2_000_000_100)
    assert len(rows) == 4
    assert all(row["confidence"] is None for row in rows)
    assert all(row["attributes"]["severity"] is None for row in rows)
    assert all(row["attributes"]["direction"] is None for row in rows)
