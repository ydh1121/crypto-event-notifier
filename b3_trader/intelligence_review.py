"""Allowlisted source failure evidence; never export raw exception strings."""
from __future__ import annotations

import math
import re

from .event_response_contract import OFFICIAL_EVENT_SOURCES

CAPTURES = ('macro_actual_capture', 'bea_actual_capture', 'consensus_capture')
STATUSES = {'ok', 'partial', 'source_error', 'unsupported_source', 'capture_error',
            'not_requested', 'network_disabled', 'disabled', 'idle', 'not_configured',
            'missing_api_key', 'skipped_missing_api_key', 'credential_missing'}
ERROR_PATTERNS = {
    'dns': r'NameResolutionError|getaddrinfo failed|Name or service not known|Temporary failure in name resolution',
    'connection': r'ConnectionError|ConnectionRefusedError|NewConnectionError|connection reset|RemoteDisconnected',
    'tls': r'SSLError|CERTIFICATE_VERIFY_FAILED|certificate verify failed',
    'proxy': r'ProxyError|proxy tunnel',
    'parse': r'JSONDecodeError|ParseError|ExpatError',
    'invalid_source_data': r'\bValueError:',
}


def _error_evidence(errors, classify):
    text = '\n'.join(e[:2000] for e in errors[:64] if isinstance(e, str))
    kinds = set(classify(text))
    kinds.update(name for name, pattern in ERROR_PATTERNS.items() if re.search(pattern, text, re.I))
    codes = set(re.findall(r'\bHTTP(?:Error)?\s*[:= ]+\s*([45]\d\d)\b', text, re.I))
    codes.update(re.findall(r'\b([45]\d\d)\s+(?:Client|Server)\s+Error\b', text, re.I))
    return {'error_kinds': sorted(kinds), 'http_status_codes': sorted(int(c) for c in codes),
            'error_present': bool(text)}


def _row(row, classify):
    if not isinstance(row, dict):
        return {'status': 'unavailable'}
    status = row.get('status')
    out = {'status': status if isinstance(status, str) and status in STATUSES else 'unrecognized'}
    for key in ('events', 'inserted', 'updated', 'capture_failures', 'captured', 'events_considered'):
        value = row.get(key)
        if type(value) in (int, float) and math.isfinite(value) and value >= 0:
            out[key] = value
    errors = [row.get('error', '')]
    children = row.get('errors')
    if isinstance(children, list):
        errors.extend(r.get('error', '') for r in children[:63] if isinstance(r, dict))
    return {**out, **_error_evidence(errors, classify)}


def source_result_evidence(result, classify):
    sources = result.get('source_results')
    out = {}
    if isinstance(sources, dict):
        out['source_results'] = {name: _row(sources[name], classify)
                                 for name in OFFICIAL_EVENT_SOURCES if name in sources}
    for name in CAPTURES:
        if name in result:
            out[name] = _row(result[name], classify)
    return out
