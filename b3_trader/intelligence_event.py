from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

_SPACE_RE = re.compile(r"\s+")


def _clean_text(value: Any) -> str:
    return _SPACE_RE.sub(" ", str(value or "")).strip()


def _clean_tags(values: Iterable[Any]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = _clean_text(value).upper()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return tuple(result)


def _nonnegative(value: Any) -> float:
    return max(0.0, float(value or 0.0))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _dedup_hash(*, event_type: str, title: str, source_ts: float, entities: tuple[str, ...]) -> str:
    payload = {
        "event_type": _clean_text(event_type).upper(),
        "title": _clean_text(title).casefold(),
        "source_ts": round(float(source_ts or 0.0), 3),
        "entities": list(entities),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IntelligenceEvent:
    event_id: str
    external_id: str
    source_id: str
    source_family: str
    event_type: str
    title: str
    source_url: str
    published_at: float
    scheduled_at: float
    observed_at: float
    source_ts: float
    received_at: float
    entities: tuple[str, ...]
    market_scope: tuple[str, ...]
    raw_text: str
    summary_ko: str
    attributes: dict[str, Any]
    dedup_hash: str
    confidence: float | None
    version: int = 1

    def freshness_seconds(self, now: float | None = None) -> float | None:
        if self.source_ts <= 0:
            return None
        current = float(now if now is not None else time.time())
        if self.source_ts > current:
            return None
        return max(0.0, current - self.source_ts)


def normalize_intelligence_event(
    *,
    source_id: str,
    source_family: str,
    event_type: str,
    title: str,
    source_url: str,
    external_id: str = "",
    published_at: float = 0.0,
    scheduled_at: float = 0.0,
    observed_at: float = 0.0,
    received_at: float | None = None,
    entities: Iterable[Any] = (),
    market_scope: Iterable[Any] = (),
    raw_text: str = "",
    summary_ko: str = "",
    attributes: dict[str, Any] | None = None,
    confidence: float | None = None,
    version: int = 1,
) -> IntelligenceEvent:
    clean_source_id = _clean_text(source_id).lower()
    clean_family = _clean_text(source_family).lower()
    clean_event_type = _clean_text(event_type).upper()
    clean_title = _clean_text(title)
    clean_url = _clean_text(source_url)
    clean_external_id = _clean_text(external_id)
    if not clean_source_id or not clean_family or not clean_event_type or not clean_title or not clean_url:
        raise ValueError("source_id/source_family/event_type/title/source_url are required")

    published = _nonnegative(published_at)
    scheduled = _nonnegative(scheduled_at)
    observed = _nonnegative(observed_at)
    source_ts = observed or published or scheduled
    received = float(received_at if received_at is not None else time.time())
    if received <= 0:
        raise ValueError("received_at must be positive")

    clean_entities = _clean_tags(entities)
    clean_scope = _clean_tags(market_scope)
    attrs = dict(attributes or {})
    dedup = _dedup_hash(
        event_type=clean_event_type,
        title=clean_title,
        source_ts=source_ts,
        entities=clean_entities,
    )
    event_id = f"{clean_source_id}:{clean_external_id}" if clean_external_id else f"{clean_source_id}:{dedup[:24]}"

    normalized_confidence: float | None
    if confidence is None:
        normalized_confidence = None
    else:
        normalized_confidence = float(confidence)
        if not 0.0 <= normalized_confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
    normalized_version = int(version)
    if normalized_version < 1:
        raise ValueError("version must be >= 1")

    return IntelligenceEvent(
        event_id=event_id,
        external_id=clean_external_id,
        source_id=clean_source_id,
        source_family=clean_family,
        event_type=clean_event_type,
        title=clean_title,
        source_url=clean_url,
        published_at=published,
        scheduled_at=scheduled,
        observed_at=observed,
        source_ts=source_ts,
        received_at=received,
        entities=clean_entities,
        market_scope=clean_scope,
        raw_text=str(raw_text or "").strip(),
        summary_ko=str(summary_ko or "").strip(),
        attributes=attrs,
        dedup_hash=dedup,
        confidence=normalized_confidence,
        version=normalized_version,
    )
