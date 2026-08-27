from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from .market_lifecycle import (
    CAUTION,
    LISTING_ANNOUNCED,
    NEW_LISTING,
    NORMAL,
    TERMINATED,
    TERMINATION_SCHEDULED,
    merge_lifecycle_state,
)
from .market_lifecycle_store import MarketLifecycleStore
from .market_notice_store import MarketNoticeStore

ATTENTION_STATES = {LISTING_ANNOUNCED, NEW_LISTING, CAUTION, TERMINATION_SCHEDULED, TERMINATED}
NOTICE_DETAIL_FIELDS = {
    "notice_id",
    "title",
    "url",
    "source",
    "effective_at",
    "announcement_at",
    "deposit_at",
    "trade_open_at",
    "termination_at",
}


class MarketLifecycleService:
    """Composes exchange market-list state with normalized official notices."""

    def __init__(self, conn) -> None:
        self.market_store = MarketLifecycleStore(conn)
        self.notice_store = MarketNoticeStore(conn)

    @staticmethod
    def _market_key(source: Any) -> str:
        return str(getattr(source, "market", "") or "").strip().upper()

    @staticmethod
    def _notice_detail(source: Any) -> dict[str, Any]:
        if not isinstance(source, dict):
            return {}
        return {key: value for key, value in source.items() if key in NOTICE_DETAIL_FIELDS}

    def _compose(self, exchange: str, base: dict[str, Any], active_markets: set[str]) -> dict[str, Any]:
        notice = self.notice_store.state_snapshot(exchange)
        base_states = base.get("states") if isinstance(base.get("states"), dict) else {}
        notice_states = notice.get("states") if isinstance(notice.get("states"), dict) else {}
        notice_details = notice.get("details") if isinstance(notice.get("details"), dict) else {}

        if base.get("observation_rejected"):
            active_markets = {
                str(market)
                for market, state in base_states.items()
                if str(state or NORMAL).upper() != TERMINATED
            }

        states: dict[str, str] = {}
        reasons: dict[str, str] = {}
        for market in set(base_states) | set(notice_states):
            base_state = str(base_states.get(market) or NORMAL)
            notice_state = str(notice_states.get(market) or "")
            decision = merge_lifecycle_state(
                base_state=base_state,
                notice_state=notice_state,
                market_present=market in active_markets,
            )
            # Notice-only rows are useful only while they announce a not-yet-listed market.
            if market not in base_states and decision.state != LISTING_ANNOUNCED:
                continue
            states[str(market)] = decision.state
            reasons[str(market)] = decision.reason

        counts = Counter(
            state for market, state in states.items()
            if market in base_states
        )
        notice_only = [
            {
                "market": market,
                "state": state,
                **self._notice_detail(notice_details.get(market)),
            }
            for market, state in states.items()
            if market not in base_states and state == LISTING_ANNOUNCED
        ]
        attention: list[dict[str, Any]] = []
        for market, state in states.items():
            if state not in ATTENTION_STATES:
                continue
            detail = self._notice_detail(notice_details.get(market))
            attention.append(
                {
                    "market": market,
                    "state": state,
                    "reason": reasons.get(market, ""),
                    **detail,
                }
            )
        attention.sort(key=lambda row: (float(row.get("effective_at") or 0.0), str(row.get("market") or "")), reverse=True)

        return {
            **base,
            "states": states,
            "state_reasons": reasons,
            "counts": dict(sorted(counts.items())),
            "attention": attention[:120],
            "notice_only": notice_only[:80],
            "notice_state_count": len(notice_states),
            "notice_overlay": True,
        }

    def observe_markets(
        self,
        exchange: str,
        markets: Iterable[Any],
        *,
        observed_at: float | None = None,
    ) -> dict[str, Any]:
        materialized = list(markets)
        active = {self._market_key(row) for row in materialized if self._market_key(row).startswith("KRW-")}
        base = self.market_store.observe_markets(exchange, materialized, observed_at=observed_at)
        return self._compose(str(exchange or "").strip().lower(), base, active)

    def snapshot(self, exchange: str) -> dict[str, Any]:
        exchange = str(exchange or "").strip().lower()
        base = self.market_store.snapshot(exchange)
        active = {
            str(market)
            for market, state in (base.get("states") or {}).items()
            if str(state or NORMAL).upper() != TERMINATED
        }
        return self._compose(exchange, base, active)
