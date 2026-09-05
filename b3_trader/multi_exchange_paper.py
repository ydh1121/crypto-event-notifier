from __future__ import annotations

import argparse
import os
import threading
import time
from pathlib import Path
from typing import Any

from .asset_strategy import AssetSignal, AssetStrategy
from .auto_demo_v2 import (
    BUY_COOLDOWN_SECONDS,
    DEFAULT_BASE_WEIGHT_PCT,
    MAX_POSITION_PCT,
    MAX_SLIPPAGE_BPS,
    MAX_SPREAD_BPS,
    SCAN_INTERVAL_SECONDS,
    START_KRW,
    AutoPaperDemo,
    _atomic_json,
    _num,
)
from .exchange_public import PublicExchangeAdapter, PublicMarket, public_exchange
from .market_feature_store import MarketFeatureStore
from .market_lifecycle import NORMAL, lifecycle_entry_policy
from .market_lifecycle_service import MarketLifecycleService
from .scoped_paper_store import ScopedPaperStore

MARKET_MEMORY_RETENTION_DAYS = 45
ENTRY_INTENTS = {"buy", "explore", "idle_explore"}


class MultiExchangePaperDemo(AutoPaperDemo):
    """Phase 3 PAPER runtime scoped by exchange + market + strategy.

    No private exchange API is used. It reuses the existing adaptive PAPER
    execution semantics while sourcing quotation data through a public adapter.
    """

    def __init__(
        self,
        exchange: str = "upbit",
        strategy_name: str = "adaptive",
        *,
        market_limit: int = 0,
    ) -> None:
        self.exchange = exchange.strip().lower()
        self.strategy_name = strategy_name.strip().lower()
        self.market_limit = max(0, int(market_limit))
        self.client: PublicExchangeAdapter = public_exchange(self.exchange)
        self.strategy = AssetStrategy()
        self.store = ScopedPaperStore(self.exchange, self.strategy_name)
        self.lifecycle = MarketLifecycleService(self.store.conn)
        self.lifecycle_snapshot = self.lifecycle.snapshot(self.exchange)
        self.market_features = MarketFeatureStore(self.store.conn)
        self.prices: dict[str, float] = {}
        self.names: dict[str, str] = {}
        self.market_meta: dict[str, PublicMarket] = {}
        self.scan_number = 0
        self.last_scan_started = 0.0
        self.last_scan_completed = 0.0
        self.status_path = Path(f"dashboard/runtime-demo-{self.exchange}.json")
        self.detail_dir = Path(f"dashboard/demo-runtime-{self.exchange}")

    def _all_tickers(self) -> tuple[list[dict[str, Any]], dict[str, str]]:
        markets = self.client.krw_markets()
        self.lifecycle_snapshot = self.lifecycle.observe_markets(self.exchange, markets)
        self.market_meta = {row.market: row for row in markets}
        names = {row.market: row.name for row in markets}
        # Seed every active KRW market immediately. A market discovered after
        # baseline therefore receives its PAPER account/profile before scoring.
        for row in markets:
            self.store.ensure_market(row.market, row.symbol, row.name)
        return self.client.krw_tickers(), names

    def _rank_universe(self, tickers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
        rows, breadth = super()._rank_universe(tickers)
        market_limit = max(0, int(getattr(self, "market_limit", 0) or 0))
        if market_limit > 0:
            rows = rows[:market_limit]
        return rows, breadth

    def _entry_policy(self, market: str, account: dict[str, Any]):
        has_position = _num(account.get("volume")) > 0
        lifecycle = getattr(self, "lifecycle", None)
        snapshot = getattr(self, "lifecycle_snapshot", None)
        exchange = str(getattr(self, "exchange", "") or "")
        if lifecycle is None or not exchange or not isinstance(snapshot, dict):
            # Compatibility for legacy/test construction paths that intentionally
            # bypass __init__. The normal active-market policy preserves the
            # previous trade-plan behavior without duplicating lifecycle logic.
            return lifecycle_entry_policy(NORMAL, has_position=has_position)
        return lifecycle.entry_policy(
            exchange,
            market,
            has_position=has_position,
            snapshot=snapshot,
        )

    def _build_trade_plan(
        self,
        account: dict[str, Any],
        profile: dict[str, Any],
        signal: AssetSignal,
        opportunity: float,
        price: float,
        intent: str,
    ) -> dict[str, Any]:
        plan = super()._build_trade_plan(account, profile, signal, opportunity, price, intent)
        policy = self._entry_policy(str(account.get("market") or ""), account)
        plan["lifecycle_state"] = policy.state
        plan["lifecycle_entry_eligible"] = policy.entry_allowed
        plan["lifecycle_add_eligible"] = policy.add_allowed
        plan["lifecycle_risk_flag"] = policy.risk_flag
        plan["lifecycle_policy_reason"] = policy.reason
        if not policy.entry_allowed or not policy.add_allowed:
            plan["suggested_weight_pct"] = 0.0
            plan["expected_entry_price"] = 0.0
        return plan

    def _trade_intent(
        self,
        account: dict[str, Any],
        profile: dict[str, Any],
        signal: AssetSignal,
        opportunity: float,
        price: float,
        now: float,
        plan: dict[str, Any],
    ) -> tuple[str, str]:
        intent, reason = super()._trade_intent(account, profile, signal, opportunity, price, now, plan)
        policy = self._entry_policy(str(account.get("market") or ""), account)
        if intent in ENTRY_INTENTS and not policy.entry_allowed:
            return "wait", f"lifecycle_block {policy.state}: {policy.reason}; {reason}"
        if intent == "add" and not policy.add_allowed:
            return "hold", f"lifecycle_block {policy.state}: {policy.reason}; {reason}"
        return intent, reason

    def _lifecycle_decorated_row(self, row: dict[str, Any]) -> dict[str, Any]:
        market = str(row.get("market") or "")
        account = {"market": market, "volume": 1.0 if row.get("has_position") else 0.0}
        policy = self._entry_policy(market, account)
        return {
            **row,
            "lifecycle_state": policy.state,
            "lifecycle_entry_eligible": policy.entry_allowed,
            "lifecycle_add_eligible": policy.add_allowed,
            "lifecycle_risk_flag": policy.risk_flag,
        }

    def _write_market_detail(self, market: str) -> None:
        detail = self.store.market_detail(market)
        if detail:
            account = detail.get("account") if isinstance(detail.get("account"), dict) else {}
            policy = self._entry_policy(market, account)
            detail["lifecycle_state"] = policy.state
            detail["lifecycle_entry_eligible"] = policy.entry_allowed
            detail["lifecycle_add_eligible"] = policy.add_allowed
            detail["lifecycle_risk_flag"] = policy.risk_flag
            detail = self.market_features.enrich_market_detail(
                detail,
                exchange=self.exchange,
                market=market,
                strategy=self.strategy_name,
            )
            _atomic_json(self.detail_dir / f"{market.replace('/', '_')}.json", detail)

    def _write_status(self, *, scanned: int, total: int, error: str = "") -> None:
        lifecycle = self.lifecycle_snapshot if isinstance(self.lifecycle_snapshot, dict) else {}
        leaderboard = [self._lifecycle_decorated_row(row) for row in self.store.leaderboard(5000)]
        active_positions = sum(1 for row in leaderboard if row["has_position"])
        total_equity = sum(_num(row.get("equity_krw")) for row in leaderboard)
        total_cash = sum(_num(row.get("cash_krw")) for row in leaderboard)
        best = leaderboard[0] if leaderboard else None
        warning_count = sum(1 for row in self.market_meta.values() if row.warning)
        lifecycle_summary = {
            "market_count": int(lifecycle.get("market_count") or 0),
            "counts": lifecycle.get("counts") if isinstance(lifecycle.get("counts"), dict) else {},
            "attention": (lifecycle.get("attention") if isinstance(lifecycle.get("attention"), list) else [])[:80],
            "notice_only": (lifecycle.get("notice_only") if isinstance(lifecycle.get("notice_only"), list) else [])[:40],
            "notice_state_count": int(lifecycle.get("notice_state_count") or 0),
            "notice_overlay": bool(lifecycle.get("notice_overlay")),
            "transitions": (lifecycle.get("transitions") if isinstance(lifecycle.get("transitions"), list) else [])[:40],
            "entry_blocked_markets": sum(1 for row in leaderboard if not row.get("lifecycle_entry_eligible", True)),
            "paper_gate": "termination_only",
            "shadow_only": False,
        }
        payload = {
            "running": not bool(error),
            "paper_only": True,
            "phase": 3,
            "mode": "multi_exchange_per_coin_adaptive_research",
            "exchange": self.exchange,
            "strategy": self.strategy_name,
            "identity": "exchange+market+strategy",
            "pid": os.getpid(),
            "start_krw": START_KRW,
            "per_market_start_krw": START_KRW,
            "market_count": len(leaderboard),
            "scanned_count": scanned,
            "scan_total": total,
            "active_positions": active_positions,
            "warning_markets": warning_count,
            "market_lifecycle": lifecycle_summary,
            "aggregate_virtual_capital_krw": START_KRW * len(leaderboard),
            "equity_krw": round(total_equity, 2),
            "cash_krw": round(total_cash, 2),
            "positions": [row for row in leaderboard if row["has_position"]],
            "candidates": sorted(leaderboard, key=lambda row: row["opportunity_score"], reverse=True)[:30],
            "leaderboard": leaderboard,
            "best_market": best,
            "updated_at": time.time(),
            "last_scan_started": self.last_scan_started,
            "last_scan_completed": self.last_scan_completed,
            "scan_number": self.scan_number,
            "error": error,
            "rules": {
                "each_scope_start_krw": START_KRW,
                "scan_interval_seconds": SCAN_INTERVAL_SECONDS,
                "max_position_pct": MAX_POSITION_PCT,
                "base_weight_pct": DEFAULT_BASE_WEIGHT_PCT,
                "buy_cooldown_seconds": BUY_COOLDOWN_SECONDS,
                "bounded_exploration": True,
                "adaptive_profile_learning": True,
                "dynamic_exit_plan": True,
                "staged_add_plan": True,
                "max_spread_bps": MAX_SPREAD_BPS,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
                "public_market_data_only": True,
                "market_memory_retention_days": MARKET_MEMORY_RETENTION_DAYS,
                "market_lifecycle_mode": "termination_gate_only",
                "market_lifecycle_notice_overlay": True,
                "termination_blocks_new_paper_entries": True,
                "caution_remains_shadow_for_current_adaptive": True,
                "new_listing_remains_shadow_for_current_adaptive": True,
                "return_windows_source": "research_market_memory_mx",
            },
        }
        _atomic_json(self.status_path, payload)

    def scan_once(self) -> None:
        super().scan_once()
        cutoff = time.time() - MARKET_MEMORY_RETENTION_DAYS * 86400.0
        self.store.conn.execute(
            "DELETE FROM research_market_memory_mx WHERE exchange=? AND strategy=? AND ts < ?",
            (self.exchange, self.strategy_name, cutoff),
        )
        self.store.conn.commit()

    def run_once(self) -> None:
        try:
            self.scan_once()
        finally:
            self.store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 multi-exchange PAPER research")
    parser.add_argument("--exchange", default="upbit", choices=["bithumb", "upbit"])
    parser.add_argument("--strategy", default="adaptive")
    parser.add_argument("--limit", type=int, default=0, help="Score only top N markets; all accounts are still seeded")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    args = parser.parse_args()

    demo = MultiExchangePaperDemo(args.exchange, args.strategy, market_limit=args.limit)
    if args.once:
        demo.run_once()
    else:
        demo.run(threading.Event())


if __name__ == "__main__":
    main()
