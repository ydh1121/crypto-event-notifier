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


@dataclass(frozen=True)
class LifecycleEntryPolicy:
    state: str
    entry_allowed: bool
    add_allowed: bool
    exit_allowed: bool
    risk_flag: str
    reason: str


def normalize_lifecycle_state(value: str, default: str = NORMAL) -> str:
    state = str(value or "").strip().upper()
    return state if state in ALL_STATES else default


def lifecycle_entry_policy(state: str, *, has_position: bool = False) -> LifecycleEntryPolicy:
    """Pure PAPER eligibility policy for a composed lifecycle state.

    This is deliberately narrower than the future LifecycleRiskScore. CAUTION is
    still shadow information for the current adaptive strategy. Confirmed or
    scheduled termination blocks new/additional PAPER buys while preserving the
    ability to manage and exit an existing position.
    """
    normalized = normalize_lifecycle_state(state)
    if normalized == LISTING_ANNOUNCED:
        return LifecycleEntryPolicy(
            state=normalized,
            entry_allowed=False,
            add_allowed=False,
            exit_allowed=bool(has_position),
            risk_flag="pre_listing",
            reason="market_not_open",
        )
    if normalized in {TERMINATION_SCHEDULED, TERMINATED}:
        return LifecycleEntryPolicy(
            state=normalized,
            entry_allowed=False,
            add_allowed=False,
            exit_allowed=True,
            risk_flag="termination",
            reason="trading_support_ending" if normalized == TERMINATION_SCHEDULED else "trading_support_ended",
        )
    if normalized == CAUTION:
        return LifecycleEntryPolicy(
            state=normalized,
            entry_allowed=True,
            add_allowed=True,
            exit_allowed=True,
            risk_flag="caution_shadow",
            reason="caution_not_yet_promoted_to_paper_gate",
        )
    return LifecycleEntryPolicy(
        state=normalized,
        entry_allowed=True,
        add_allowed=True,
        exit_allowed=True,
        risk_flag="new_listing_shadow" if normalized == NEW_LISTING else "",
        reason="active_market",
    )


def merge_lifecycle_state(*, base_state: str, notice_state: str = "", market_present: bool) -> LifecycleDecision:
    """Compose market-list inference with normalized official notice state.

    Market availability remains authoritative for completed termination. Official
    notices may raise attention before the market-list API changes. A caution
    release never suppresses an API warning because the base state wins again.
    """
    base = normalize_lifecycle_state(base_state)
    notice = normalize_lifecycle_state(notice_state, default="") if notice_state else ""

    if base == TERMINATED:
        return LifecycleDecision(TERMINATED, "market_absence_confirmed")
    if notice in {TERMINATION_SCHEDULED, TERMINATED}:
        return LifecycleDecision(notice, "official_notice")
    if notice == CAUTION:
        return LifecycleDecision(CAUTION, "official_notice")
    if notice == LISTING_ANNOUNCED and not market_present:
        return LifecycleDecision(LISTING_ANNOUNCED, "official_notice")
    return LifecycleDecision(base, "market_state")


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
