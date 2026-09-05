from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

from .intelligence_event import IntelligenceEvent

REACTION_WINDOWS_SECONDS: dict[str, int] = {
    "15m": 15 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
    "1d": 24 * 60 * 60,
}
DEFAULT_MAX_OBSERVATION_DELAY_SECONDS = 120.0
REACTION_VERSION = 1


def _finite(value: Any, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _clean(value: Any) -> str:
    return str(value or "").strip()


def event_reaction_anchor(event: IntelligenceEvent) -> tuple[str, float] | None:
    """Return the best source clock for a forward reaction window.

    Publication time wins when present because official news/release adapters
    expose that clock. Observed time is next for observations. A precise
    scheduled time is the final fallback for calendar events. `received_at` is
    intentionally never used because doing so would fabricate the event clock.
    """
    if float(event.published_at or 0.0) > 0:
        return "published_at", float(event.published_at)
    if float(event.observed_at or 0.0) > 0:
        return "observed_at", float(event.observed_at)
    if float(event.scheduled_at or 0.0) > 0:
        return "scheduled_at", float(event.scheduled_at)
    return None


@dataclass(frozen=True)
class ReactionPriceObservation:
    market: str
    observed_at: float
    price: float
    provider_id: str
    exchange: str
    source: str
    received_at: float
    evidence: dict[str, Any]


def normalize_reaction_price_observation(
    *,
    market: str,
    observed_at: float,
    price: float,
    provider_id: str,
    exchange: str,
    source: str,
    received_at: float | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> ReactionPriceObservation:
    clean_market = _clean(market).upper()
    clean_provider = _clean(provider_id).lower()
    clean_exchange = _clean(exchange).lower()
    clean_source = _clean(source)
    if not clean_market or not clean_provider or not clean_exchange or not clean_source:
        raise ValueError("market/provider_id/exchange/source are required")
    observed = _finite(observed_at, name="observed_at")
    level = _finite(price, name="price")
    received = _finite(received_at if received_at is not None else observed, name="received_at")
    if observed <= 0 or received <= 0:
        raise ValueError("observed_at/received_at must be positive")
    if level <= 0:
        raise ValueError("price must be positive")
    return ReactionPriceObservation(
        market=clean_market,
        observed_at=observed,
        price=level,
        provider_id=clean_provider,
        exchange=clean_exchange,
        source=clean_source,
        received_at=received,
        evidence=dict(evidence or {}),
    )


@dataclass(frozen=True)
class IntelligenceReaction:
    reaction_id: str
    event_id: str
    source_id: str
    event_type: str
    market: str
    window: str
    horizon_seconds: int
    anchor_kind: str
    anchor_at: float
    provider_id: str
    exchange: str
    start_at: float
    end_at: float
    start_price: float
    end_price: float
    forward_return_pct: float
    start_delay_seconds: float
    end_delay_seconds: float
    start_source: str
    end_source: str
    evidence: dict[str, Any]
    version: int = REACTION_VERSION


def _reaction_id(
    *,
    event_id: str,
    market: str,
    window: str,
    provider_id: str,
    exchange: str,
) -> str:
    payload = json.dumps(
        [event_id, market, window, provider_id, exchange],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "irx:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def compute_event_reaction(
    event: IntelligenceEvent,
    *,
    market: str,
    window: str,
    start: ReactionPriceObservation,
    end: ReactionPriceObservation,
    max_observation_delay_seconds: float = DEFAULT_MAX_OBSERVATION_DELAY_SECONDS,
) -> IntelligenceReaction | None:
    clean_window = _clean(window).lower()
    horizon = REACTION_WINDOWS_SECONDS.get(clean_window)
    if horizon is None:
        raise ValueError(f"unsupported reaction window: {window!r}")
    anchor = event_reaction_anchor(event)
    if anchor is None:
        return None
    anchor_kind, anchor_at = anchor
    clean_market = _clean(market).upper()
    if not clean_market:
        raise ValueError("market is required")
    if start.market != clean_market or end.market != clean_market:
        return None
    if not start.provider_id or start.provider_id != end.provider_id:
        return None
    if not start.exchange or start.exchange != end.exchange:
        return None

    max_delay = _finite(max_observation_delay_seconds, name="max_observation_delay_seconds")
    if max_delay < 0:
        raise ValueError("max_observation_delay_seconds must be >= 0")
    target_end = anchor_at + float(horizon)
    start_delay = start.observed_at - anchor_at
    end_delay = end.observed_at - target_end

    # Forward-only alignment: never select a pre-event/pre-horizon price. This
    # deliberately differs from a symmetric nearest-neighbour lookup.
    if start_delay < 0 or start_delay > max_delay:
        return None
    if end_delay < 0 or end_delay > max_delay:
        return None
    if end.observed_at <= start.observed_at:
        return None
    if start.price <= 0 or end.price <= 0:
        return None

    forward_return_pct = (end.price / start.price - 1.0) * 100.0
    return IntelligenceReaction(
        reaction_id=_reaction_id(
            event_id=event.event_id,
            market=clean_market,
            window=clean_window,
            provider_id=start.provider_id,
            exchange=start.exchange,
        ),
        event_id=event.event_id,
        source_id=event.source_id,
        event_type=event.event_type,
        market=clean_market,
        window=clean_window,
        horizon_seconds=horizon,
        anchor_kind=anchor_kind,
        anchor_at=anchor_at,
        provider_id=start.provider_id,
        exchange=start.exchange,
        start_at=start.observed_at,
        end_at=end.observed_at,
        start_price=start.price,
        end_price=end.price,
        forward_return_pct=forward_return_pct,
        start_delay_seconds=start_delay,
        end_delay_seconds=end_delay,
        start_source=start.source,
        end_source=end.source,
        evidence={
            "event": {
                "source_id": event.source_id,
                "source_url": event.source_url,
                "anchor_kind": anchor_kind,
                "anchor_at": anchor_at,
            },
            "start": dict(start.evidence),
            "end": dict(end.evidence),
            "alignment": {
                "forward_only": True,
                "max_observation_delay_seconds": max_delay,
            },
        },
    )
