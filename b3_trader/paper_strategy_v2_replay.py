from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .auto_demo_v2 import DB_PATH
from .paper_exit_policy_v2 import evaluate_exit
from .paper_position_plan_v2 import PositionPlanV2, PositionSizingPolicy, evaluate_next_add, plan_new_position

FEE_RATE = 0.0004
SLIPPAGE_RATE = 0.0005
DEFAULT_BUCKET_SECONDS = 300


def _num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _median(values: list[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


@dataclass
class ReplayPosition:
    market: str
    plan: PositionPlanV2
    entry_ts: float
    entry_regime: float
    entry_opportunity: float
    volume: float = 0.0
    cost_cash: float = 0.0
    completed_entries: int = 0
    peak_price: float = 0.0
    add_count: int = 0

    @property
    def average_price(self) -> float:
        return self.cost_cash / self.volume if self.volume > 0 else 0.0


@dataclass
class ReplayBook:
    policy: PositionSizingPolicy
    cash: float
    positions: dict[str, ReplayPosition] = field(default_factory=dict)
    last_prices: dict[str, float] = field(default_factory=dict)
    buy_tickets: list[float] = field(default_factory=list)
    initial_tickets: list[float] = field(default_factory=list)
    add_tickets: list[float] = field(default_factory=list)
    closed_returns: list[float] = field(default_factory=list)
    exit_reasons: Counter[str] = field(default_factory=Counter)
    positions_opened: int = 0
    positions_closed: int = 0
    cycles_with_adds: int = 0
    peak_equity: float = 0.0
    max_drawdown_pct: float = 0.0
    peak_gross_exposure_pct: float = 0.0
    exposure_pct_samples: list[float] = field(default_factory=list)
    max_concurrent_positions: int = 0

    def reserved_exposure(self) -> float:
        return sum(position.plan.reserved_position_krw for position in self.positions.values())

    def equity(self) -> float:
        marked = sum(
            position.volume * self.last_prices.get(market, position.average_price)
            for market, position in self.positions.items()
        )
        return self.cash + marked

    def mark_metrics(self) -> None:
        equity = self.equity()
        self.peak_equity = max(self.peak_equity or self.policy.portfolio_capital_krw, equity)
        if self.peak_equity > 0:
            dd = (equity / self.peak_equity - 1.0) * 100.0
            self.max_drawdown_pct = min(self.max_drawdown_pct, dd)
        exposure = sum(
            position.volume * self.last_prices.get(market, position.average_price)
            for market, position in self.positions.items()
        )
        exposure_pct = exposure / self.policy.portfolio_capital_krw * 100.0
        self.exposure_pct_samples.append(exposure_pct)
        self.peak_gross_exposure_pct = max(self.peak_gross_exposure_pct, exposure_pct)
        self.max_concurrent_positions = max(self.max_concurrent_positions, len(self.positions))

    def buy(self, position: ReplayPosition, order_krw: float, market_price: float, *, is_add: bool) -> bool:
        notional = max(0.0, min(float(order_krw), self.cash / (1.0 + FEE_RATE)))
        if notional < self.policy.min_order_krw:
            return False
        fill_price = float(market_price) * (1.0 + SLIPPAGE_RATE)
        fee = notional * FEE_RATE
        cash_used = notional + fee
        volume = notional / fill_price
        self.cash -= cash_used
        position.volume += volume
        position.cost_cash += cash_used
        position.completed_entries += 1
        position.peak_price = max(position.peak_price, float(market_price))
        self.buy_tickets.append(notional)
        if is_add:
            position.add_count += 1
            self.add_tickets.append(notional)
        else:
            self.initial_tickets.append(notional)
        return True

    def sell(self, market: str, market_price: float, reason: str) -> None:
        position = self.positions.get(market)
        if position is None or position.volume <= 0:
            return
        fill_price = float(market_price) * (1.0 - SLIPPAGE_RATE)
        gross = position.volume * fill_price
        fee = gross * FEE_RATE
        proceeds = gross - fee
        pnl = proceeds - position.cost_cash
        ret = pnl / position.cost_cash * 100.0 if position.cost_cash > 0 else 0.0
        self.cash += proceeds
        self.closed_returns.append(ret)
        self.exit_reasons[reason] += 1
        self.positions_closed += 1
        if position.add_count > 0:
            self.cycles_with_adds += 1
        del self.positions[market]


def _bucket_rows(rows: list[dict[str, Any]], bucket_seconds: int) -> list[list[dict[str, Any]]]:
    buckets: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        ts = _num(row.get("ts"))
        if ts <= 0:
            continue
        key = int(ts // max(1, int(bucket_seconds)))
        buckets.setdefault(key, []).append(row)
    return [buckets[key] for key in sorted(buckets)]


def replay_shared_portfolio(
    rows: Iterable[dict[str, Any]],
    *,
    policy: PositionSizingPolicy | None = None,
    max_positions: int = 3,
    bucket_seconds: int = DEFAULT_BUCKET_SECONDS,
) -> dict[str, Any]:
    policy = policy or PositionSizingPolicy()
    ordered = sorted((dict(row) for row in rows), key=lambda row: (_num(row.get("ts")), str(row.get("market") or "")))
    book = ReplayBook(policy=policy, cash=policy.portfolio_capital_krw, peak_equity=policy.portfolio_capital_krw)
    buckets = _bucket_rows(ordered, bucket_seconds)
    first_ts = _num(ordered[0].get("ts")) if ordered else 0.0
    last_ts = _num(ordered[-1].get("ts")) if ordered else 0.0

    for bucket in buckets:
        latest_by_market: dict[str, dict[str, Any]] = {}
        for row in bucket:
            market = str(row.get("market") or "")
            price = _num(row.get("price"))
            if market and price > 0:
                book.last_prices[market] = price
                latest_by_market[market] = row

        # Existing positions are managed before any new capital is admitted.
        for market, position in list(book.positions.items()):
            row = latest_by_market.get(market)
            if row is None:
                continue
            price = _num(row.get("price"))
            position.peak_price = max(position.peak_price, price)
            exit_decision = evaluate_exit(
                position.plan,
                average_price=position.average_price,
                current_price=price,
                peak_price=position.peak_price,
                current_regime_score=_num(row.get("regime_score")),
                current_opportunity_score=_num(row.get("opportunity_score")),
                holding_seconds=max(0.0, _num(row.get("ts")) - position.entry_ts),
                entry_opportunity_score=position.entry_opportunity,
                entry_regime_score=position.entry_regime,
            )
            if exit_decision.action == "sell":
                book.sell(market, price, exit_decision.reason)
                continue

            add = evaluate_next_add(
                position.plan,
                completed_entries=position.completed_entries,
                current_price=price,
                current_regime_score=_num(row.get("regime_score")),
                lifecycle_add_allowed=True,
                spread_ok=True,
                slippage_ok=True,
                btc_flash_crash=False,
            )
            if add.action == "invalidate":
                book.sell(market, price, add.reason)
            elif add.action == "add":
                book.buy(position, add.order_krw, price, is_add=True)

        available_slots = max(0, int(max_positions) - len(book.positions))
        if available_slots > 0:
            candidates = sorted(
                [row for market, row in latest_by_market.items() if market not in book.positions],
                key=lambda row: (
                    _num(row.get("opportunity_score")),
                    _num(row.get("entry_score")),
                    _num(row.get("regime_score")),
                ),
                reverse=True,
            )
            for row in candidates:
                if available_slots <= 0:
                    break
                market = str(row.get("market") or "")
                price = _num(row.get("price"))
                plan = plan_new_position(
                    first_entry_price=price,
                    regime_score=_num(row.get("regime_score")),
                    entry_score=_num(row.get("entry_score")),
                    opportunity_score=_num(row.get("opportunity_score")),
                    volatility_pct=_num(row.get("volatility_pct")),
                    current_reserved_exposure_krw=book.reserved_exposure(),
                    available_cash_krw=book.cash,
                    policy=policy,
                )
                if not plan.allowed:
                    continue
                position = ReplayPosition(
                    market=market,
                    plan=plan,
                    entry_ts=_num(row.get("ts")),
                    entry_regime=_num(row.get("regime_score")),
                    entry_opportunity=_num(row.get("opportunity_score")),
                )
                if not book.buy(position, plan.initial_order_krw, price, is_add=False):
                    continue
                book.positions[market] = position
                book.positions_opened += 1
                available_slots -= 1

        book.mark_metrics()

    # End-of-window mark is liquidated so final portfolio return is comparable
    # across replay windows. This is a replay accounting close, not a strategy exit.
    for market in list(book.positions):
        price = book.last_prices.get(market, book.positions[market].average_price)
        if price > 0:
            book.sell(market, price, "end_of_replay_mark")
    book.mark_metrics()

    start_capital = policy.portfolio_capital_krw
    final_equity = book.cash
    return_pct = (final_equity / start_capital - 1.0) * 100.0 if start_capital > 0 else 0.0
    wins = sum(1 for value in book.closed_returns if value > 0)
    adds = len(book.add_tickets)
    return {
        "paper_only": True,
        "read_only": True,
        "can_place_orders": False,
        "model": "shared_portfolio_v2_historical_replay",
        "execution_model": {
            "fee_rate_each_side": FEE_RATE,
            "fixed_slippage_rate_each_side": SLIPPAGE_RATE,
            "historical_orderbook_depth_replayed": False,
            "historical_spread_gate_replayed": False,
            "historical_lifecycle_gate_replayed": False,
        },
        "window": {
            "first_ts": first_ts,
            "last_ts": last_ts,
            "rows": len(ordered),
            "buckets": len(buckets),
            "bucket_seconds": int(bucket_seconds),
        },
        "portfolio": {
            "start_krw": round(start_capital, 2),
            "final_krw": round(final_equity, 2),
            "return_pct": round(return_pct, 4),
            "max_drawdown_pct": round(book.max_drawdown_pct, 4),
            "peak_gross_exposure_pct": round(book.peak_gross_exposure_pct, 3),
            "mean_gross_exposure_pct": round(statistics.fmean(book.exposure_pct_samples), 3) if book.exposure_pct_samples else 0.0,
            "max_concurrent_positions": book.max_concurrent_positions,
        },
        "trades": {
            "positions_opened": book.positions_opened,
            "positions_closed": book.positions_closed,
            "wins": wins,
            "win_rate_pct": round(wins / len(book.closed_returns) * 100.0, 2) if book.closed_returns else 0.0,
            "mean_closed_return_pct": round(statistics.fmean(book.closed_returns), 4) if book.closed_returns else 0.0,
            "median_closed_return_pct": round(_median(book.closed_returns), 4),
            "buy_orders": len(book.buy_tickets),
            "initial_orders": len(book.initial_tickets),
            "add_orders": adds,
            "cycles_with_adds": book.cycles_with_adds,
            "cycles_with_adds_pct": round(book.cycles_with_adds / book.positions_closed * 100.0, 2) if book.positions_closed else 0.0,
            "initial_order_mean_krw": round(statistics.fmean(book.initial_tickets), 2) if book.initial_tickets else 0.0,
            "initial_order_median_krw": round(_median(book.initial_tickets), 2),
            "add_order_mean_krw": round(statistics.fmean(book.add_tickets), 2) if book.add_tickets else 0.0,
            "add_vs_initial_size_ratio": round(statistics.fmean(book.add_tickets) / statistics.fmean(book.initial_tickets), 4) if book.add_tickets and book.initial_tickets and statistics.fmean(book.initial_tickets) > 0 else 0.0,
            "exit_reasons": dict(book.exit_reasons),
        },
        "policy": {
            "max_gross_exposure_pct": policy.max_gross_exposure_pct,
            "reserve_cash_pct": policy.reserve_cash_pct,
            "max_position_pct": policy.max_position_pct,
            "risk_budget_pct": policy.risk_budget_pct,
            "ladder_weights": list(policy.ladder_weights),
            "max_positions": int(max_positions),
        },
    }


def load_memory_rows(
    path: Path | str = DB_PATH,
    *,
    exchange: str = "bithumb",
    strategy: str = "adaptive",
    limit: int = 0,
) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_market_memory_mx'"
        ).fetchone()
        if not exists:
            return []
        sql = """SELECT id,ts,exchange,market,strategy,price,regime_score,entry_score,
                        opportunity_score,volatility_pct,trade_intent
                 FROM research_market_memory_mx
                 WHERE exchange=? AND strategy=? ORDER BY ts,id"""
        params: list[Any] = [str(exchange).strip().lower(), str(strategy).strip().lower()]
        if int(limit) > 0:
            sql += " LIMIT ?"
            params.append(int(limit))
        return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]
    finally:
        conn.close()


def legacy_observed_metrics(
    path: Path | str,
    *,
    exchange: str,
    strategy: str,
    first_ts: float,
    last_ts: float,
) -> dict[str, Any]:
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_fills_mx'"
        ).fetchone()
        if not exists:
            return {"fills": 0, "note": "legacy fill table absent"}
        rows = conn.execute(
            """SELECT market,side,krw,realized_pnl,return_pct,ts
               FROM research_fills_mx
               WHERE exchange=? AND strategy=? AND ts>=? AND ts<=?
               ORDER BY market,ts""",
            (str(exchange).strip().lower(), str(strategy).strip().lower(), float(first_ts), float(last_ts)),
        ).fetchall()
        buys = [row for row in rows if str(row["side"] or "").lower() == "buy"]
        sells = [row for row in rows if str(row["side"] or "").lower() == "sell"]
        tickets = [_num(row["krw"]) for row in buys]
        returns = [_num(row["return_pct"]) for row in sells]
        cycles_with_adds = 0
        current_counts: dict[str, int] = {}
        for row in rows:
            market = str(row["market"] or "")
            side = str(row["side"] or "").lower()
            if side == "buy":
                current_counts[market] = current_counts.get(market, 0) + 1
            elif side == "sell":
                if current_counts.get(market, 0) > 1:
                    cycles_with_adds += 1
                current_counts[market] = 0
        wins = sum(1 for value in returns if value > 0)
        return {
            "fills": len(rows),
            "buys": len(buys),
            "sells": len(sells),
            "buy_ticket_mean_krw": round(statistics.fmean(tickets), 2) if tickets else 0.0,
            "buy_ticket_median_krw": round(_median(tickets), 2),
            "cycles_with_adds": cycles_with_adds,
            "cycles_with_adds_pct": round(cycles_with_adds / len(sells) * 100.0, 2) if sells else 0.0,
            "win_rate_pct": round(wins / len(returns) * 100.0, 2) if returns else 0.0,
            "mean_closed_return_pct": round(statistics.fmean(returns), 4) if returns else 0.0,
            "median_closed_return_pct": round(_median(returns), 4),
            "realized_pnl_sum_krw": round(sum(_num(row["realized_pnl"]) for row in sells), 2),
            "portfolio_return_comparable": False,
            "reason_not_comparable": "legacy uses independent 10M KRW per-market accounts; v2 uses one shared 10M KRW portfolio",
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only shared-portfolio v2 historical replay")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--exchange", default="bithumb")
    parser.add_argument("--strategy", default="adaptive")
    parser.add_argument("--max-positions", type=int, default=3)
    parser.add_argument("--bucket-seconds", type=int, default=DEFAULT_BUCKET_SECONDS)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    rows = load_memory_rows(args.db, exchange=args.exchange, strategy=args.strategy, limit=args.limit)
    replay = replay_shared_portfolio(rows, max_positions=args.max_positions, bucket_seconds=args.bucket_seconds)
    window = replay.get("window") if isinstance(replay.get("window"), dict) else {}
    legacy = legacy_observed_metrics(
        args.db,
        exchange=args.exchange,
        strategy=args.strategy,
        first_ts=_num(window.get("first_ts")),
        last_ts=_num(window.get("last_ts")),
    ) if rows else {}
    result = {
        "v2_replay": replay,
        "legacy_observed_same_window": legacy,
        "comparison_contract": {
            "same_source_time_window": True,
            "v2_uses_shared_10m_portfolio": True,
            "legacy_observed_uses_independent_per_market_accounts": True,
            "do_not_compare_raw_portfolio_return_directly": True,
            "replay_is_strategy_research_not_live_execution_proof": True,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
