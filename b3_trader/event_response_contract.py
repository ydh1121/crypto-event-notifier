"""Identity and time windows shared by event collection and read-only views."""
from __future__ import annotations

import math
import json
import sqlite3
from typing import Any
from statistics import mean, median

HORIZONS = (("15m", 900), ("1h", 3600), ("4h", 14400), ("1d", 86400))
PROVIDER_ID = "local_public_exchange_trade_stream"
OFFICIAL_EVENT_SOURCES = (
    "us_bls_release_calendar", "us_bea_release_schedule", "us_fed_fomc_calendar",
    "us_sec_press_releases", "us_cftc_press_releases",
)
# Date-only meetings have no defensible reaction clock.
EXCLUDED_EVENT_TYPES = {"FOMC_MEETING"}
OBSERVATION_TOLERANCE_SECONDS = 120.0
EVENT_LOOKBACK_SECONDS = 3 * 86400
MAX_EVENTS = 80


def observation(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    r = dict(row)
    seconds = dict(HORIZONS).get(r.get('horizon_label'))
    keys = ('event_ts', 'horizon_seconds', 'baseline_trade_ts', 'baseline_price',
            'target_ts', 'target_trade_ts', 'target_price', 'return_pct',
            'captured_at', 'observation_tolerance_seconds')
    if seconds is None or any(not isinstance(r.get(k), (int, float)) or not math.isfinite(r[k]) for k in keys):
        return None
    tolerance = r['observation_tolerance_seconds']
    if not (0 <= tolerance <= 600 and r['event_ts'] > 0 and r['horizon_seconds'] == seconds
            and r['baseline_price'] > 0 and r['target_price'] > 0
            and r['target_ts'] == r['event_ts'] + seconds
            and 0 <= r['event_ts'] - r['baseline_trade_ts'] <= tolerance
            and 0 <= r['target_trade_ts'] - r['target_ts'] <= tolerance
            and r['captured_at'] >= r['target_trade_ts']):
        return None
    expected = (r['target_price'] / r['baseline_price'] - 1) * 100
    if not math.isclose(r['return_pct'], expected, rel_tol=1e-9, abs_tol=1e-8):
        return None
    result = {key: r[key] for key in ('return_pct', 'event_ts', 'baseline_trade_ts', 'baseline_price',
                                    'target_ts', 'target_trade_ts', 'target_price', 'captured_at')}
    try:
        attrs = json.loads(r.get('attributes_json') or '{}')
    except (ValueError, TypeError):
        attrs = {}
    if isinstance(attrs, dict):
        for key in ('baseline_observation_kind', 'target_observation_kind'):
            if attrs.get(key) in {'trade', 'minute_endpoints'}:
                result[key] = attrs[key]
    return result


def summarize_returns(values: list[float]) -> dict:
    return {'samples': len(values), 'mean_pct': mean(values) if values else None,
            'median_pct': median(values) if values else None,
            'positive_samples': sum(v > 0 for v in values) if values else None}
