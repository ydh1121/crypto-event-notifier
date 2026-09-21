from __future__ import annotations

import sqlite3

from b3_trader.market_lifecycle import (
    CAUTION,
    LISTING_ANNOUNCED,
    NEW_LISTING,
    NORMAL,
    TERMINATED,
    TERMINATION_SCHEDULED,
    lifecycle_entry_policy,
)
from b3_trader.market_lifecycle_service import MarketLifecycleService


def test_lifecycle_entry_policy_blocks_prelisting_and_termination_only() -> None:
    announced = lifecycle_entry_policy(LISTING_ANNOUNCED)
    assert announced.entry_allowed is False
    assert announced.add_allowed is False
    assert announced.risk_flag == "pre_listing"

    scheduled = lifecycle_entry_policy(TERMINATION_SCHEDULED)
    assert scheduled.entry_allowed is False
    assert scheduled.add_allowed is False
    assert scheduled.exit_allowed is True

    terminated = lifecycle_entry_policy(TERMINATED, has_position=True)
    assert terminated.entry_allowed is False
    assert terminated.add_allowed is False
    assert terminated.exit_allowed is True

    caution = lifecycle_entry_policy(CAUTION)
    assert caution.entry_allowed is True
    assert caution.add_allowed is True
    assert caution.risk_flag == "caution_shadow"

    assert lifecycle_entry_policy(NORMAL).entry_allowed is True
    assert lifecycle_entry_policy(NEW_LISTING).entry_allowed is True


def test_lifecycle_service_uses_supplied_composed_snapshot_without_requery() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    service = MarketLifecycleService(conn)
    snapshot = {"states": {"KRW-END": TERMINATION_SCHEDULED, "KRW-NEW": NEW_LISTING}}

    blocked = service.entry_policy("bithumb", "KRW-END", snapshot=snapshot)
    active = service.entry_policy("bithumb", "KRW-NEW", snapshot=snapshot)

    assert blocked.entry_allowed is False
    assert blocked.add_allowed is False
    assert active.entry_allowed is True
    conn.close()
