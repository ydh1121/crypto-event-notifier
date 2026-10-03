"""Presentation metadata for saved events; never changes collection or trading rules."""
from __future__ import annotations

ECONOMIC_SOURCES = (
    'us_bls_release_calendar', 'us_bea_release_schedule', 'us_fed_fomc_calendar',
)
LABELS = {
    'US_CPI': '소비자물가 · CPI',
    'US_EMPLOYMENT': '미국 고용',
    'US_ECI': '고용비용 · ECI',
    'US_PPI': '생산자물가 · PPI',
    'US_PCE': '개인소비지출 · PCE',
    'US_GDP': '미국 성장률 · GDP',
    'US_PERSONAL_INCOME': '미국 개인소득·지출',
    'US_TRADE': '미국 무역수지',
    'FOMC_STATEMENT': 'FOMC 성명',
    'FOMC_MINUTES': 'FOMC 회의록',
    'FOMC_PROJECTIONS': 'FOMC 경제전망',
    'US_SEC_REGULATION': 'SEC · 규제',
    'US_SEC_ENFORCEMENT': 'SEC · 법 집행',
    'US_SEC_POLICY': 'SEC · 정책',
    'US_CFTC_REGULATION': 'CFTC · 규제',
    'US_CFTC_ENFORCEMENT': 'CFTC · 법 집행',
    'US_CFTC_POLICY': 'CFTC · 정책',
}


def category(event: dict) -> str:
    return 'economic' if event.get('source_id') in ECONOMIC_SOURCES else 'news'


def presentation(event: dict) -> dict:
    # Unknown titles and identifiers are preserved, not globally translated.
    return {'category': category(event),
            'short_label': LABELS.get(event.get('event_type'), event.get('title') or event.get('event_type', ''))}


def select_events(events: list[dict], limit: int) -> list[dict]:
    """Reserve half the bounded view for each category, filling unused places by recency."""
    ordered = sorted(events, key=lambda e: (-e['event_ts'], e['event_id'], e['source_id'], e['event_type']))
    reserved = []
    for group in ('economic', 'news'):
        reserved.extend([e for e in ordered if category(e) == group][:limit // 2])
    selected = {id(e) for e in reserved}
    for event in ordered:
        if len(selected) >= limit:
            break
        selected.add(id(event))
    return [e for e in ordered if id(e) in selected]
