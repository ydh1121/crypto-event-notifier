from __future__ import annotations

from dataclasses import dataclass

NORMAL = "NORMAL"
LISTING_ANNOUNCED = "LISTING_ANNOUNCED"
NEW_LISTING = "NEW_LISTING"
CAUTION = "CAUTION"
TERMINATION_SCHEDULED = "TERMINATION_SCHEDULED"
TERMINATED = "TERMINATED"

ALL_STATES = {
    NORMAL,
    LISTING_ANNOUNCED,
    NEW_LISTING,
    CAUTION,
    TERMINATION_SCHEDULED,
    TERMINATED,
}

NEW_LISTING_WINDOW_SECONDS = 7 * 86400
MISSING_CONFIRMATIONS = 3


@dataclass(frozen=True)
class LifecycleDecision:
    state: str
    reason: str


def decide_lifecycle_state(
    *,
    previous_state: str = "",
    warning: bool = False,
    first_seen_at: float = 0.0,
    now: float,
    missing_observations: int = 0,
    baseline: bool = False,
    explicit_state: str = "",
) -> LifecycleDecision:
    """Pure market lifecycle classifier.

    Explicit exchange-notice states outrank market-list inference. Market-list
    disappearance is intentionally conservative so one transient API omission
    cannot mark a market terminated.
    """
    explicit = str(explicit_state or "").upper()
    if explicit in {LISTING_ANNOUNCED, TERMINATION_SCHEDULED, TERMINATED}:
        return LifecycleDecision(explicit, "explicit_exchange_notice")

    if int(missing_observations) >= MISSING_CONFIRMATIONS:
        return LifecycleDecision(TERMINATED, f"missing_{int(missing_observations)}_observations")

    if warning:
        return LifecycleDecision(CAUTION, "exchange_warning")

    previous = str(previous_state or "").upper()
    age = max(0.0, float(now) - float(first_seen_at or 0.0)) if first_seen_at else NEW_LISTING_WINDOW_SECONDS + 1
    if not baseline and age <= NEW_LISTING_WINDOW_SECONDS:
        if previous in {"", NEW_LISTING, TERMINATED}:
            return LifecycleDecision(NEW_LISTING, "recent_market_first_seen")

    return LifecycleDecision(NORMAL, "market_active")
