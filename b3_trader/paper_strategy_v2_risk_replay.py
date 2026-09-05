from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .auto_demo_v2 import DB_PATH
from .paper_exit_policy_v2 import evaluate_exit
from .paper_portfolio_risk_v2 import PortfolioRiskPolicy, cap_plan_to_portfolio_risk, reserved_risk_krw
from .paper_position_plan_v2 import PositionSizingPolicy, evaluate_next_add, plan_new_position
from .paper_strategy_v2_replay import ReplayBook, ReplayPosition, _bucket_rows, _num, load_memory_rows


@dataclass(frozen=True)
class ReplayPreset:
    name: str
    sizing: PositionSizingPolicy
    risk: PortfolioRiskPolicy
    max_positions: int


def default_presets() -> tuple[ReplayPreset, ...]:
    return (
        ReplayPreset(
            "control_70_30_r2_5",
            PositionSizingPolicy(max_gross_exposure_pct=70.0, reserve_cash_pct=20.0, max_position_pct=30.0, risk_budget_pct=2.5),
            PortfolioRiskPolicy(max_portfolio_risk_pct=7.5),
            3,
        ),
        ReplayPreset(
            "balanced_60_25_r2_agg5",
            PositionSizingPolicy(max_gross_exposure_pct=60.0, reserve_cash_pct=25.0, max_position_pct=25.0, risk_budget_pct=2.0),
            PortfolioRiskPolicy(max_portfolio_risk_pct=5.0),
            3,
        ),
        ReplayPreset(
            "conservative_50_22_r1_5_agg4",
            PositionSizingPolicy(max_gross_exposure_pct=50.0, reserve_cash_pct=30.0, max_position_pct=22.0, risk_budget_pct=1.5),
            PortfolioRiskPolicy(max_portfolio_risk_pct=4.0),
            3,
        ),
        ReplayPreset(
            "concentrated_55_28_r2_agg4",
            PositionSizingPolicy(max_gross_exposure_pct=55.0, reserve_cash_pct=30.0, max_position_pct=28.0, risk_budget_pct=2.0),
            PortfolioRiskPolicy(max_portfolio_risk_pct=4.0),
            2,
        ),
    )


def replay_shared_portfolio_risk_capped(
    rows: Iterable[dict[str, Any]],
    *,
    policy: PositionSizingPolicy | None = None,
    risk_policy: PortfolioRiskPolicy | None = None,
    max_positions: int = 3,
    bucket_seconds: int = 300,
) -> dict[str, Any]:
    policy = policy or PositionSizingPolicy()
    risk_policy = risk_policy or PortfolioRiskPolicy()
    ordered = sorted((dict(row) for row in rows), key=lambda row: (_num(row.get("ts")), str(row.get("market") or "")))
    book = ReplayBook(policy=policy, cash=policy.portfolio_capital_krw, peak_equity=policy.portfolio_capital_krw)
    buckets = _bucket_rows(ordered, bucket_seconds)
    first_ts = _num(ordered[0].get("ts")) if ordered else 0.0
    last_ts = _num(ordered[-1].get("ts")) if ordered else 0.0
    peak_reserved_risk_pct = 0.0
    risk_cap_rejections = 0
    risk_scaled_entries = 0

    for bucket in buckets:
        latest_by_market: dict[str, dict[str, Any]] = {}
        for row in bucket:
            market = str(row.get("market") or "")
            price = _num(row.get("price"))
            if market and price > 0:
                book.last_prices[market] = price
                latest_by_market[market] = row

        exited_this_bucket: set[str] = set()
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
                exited_this_bucket.add(market)
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
                exited_this_bucket.add(market)
            elif add.action == "add":
                book.buy(position, add.order_krw, price, is_add=True)

        available_slots = max(0, int(max_positions) - len(book.positions))
        if available_slots > 0:
            candidates = sorted(
                [
                    row
                    for market, row in latest_by_market.items()
                    if market not in book.positions and market not in exited_this_bucket
                ],
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
                base_plan = plan_new_position(
                    first_entry_price=price,
                    regime_score=_num(row.get("regime_score")),
                    entry_score=_num(row.get("entry_score")),
                    opportunity_score=_num(row.get("opportunity_score")),
                    volatility_pct=_num(row.get("volatility_pct")),
                    current_reserved_exposure_krw=book.reserved_exposure(),
                    available_cash_krw=book.cash,
                    policy=policy,
                )
                if not base_plan.allowed:
                    continue
                current_risk = reserved_risk_krw(position.plan for position in book.positions.values())
                plan = cap_plan_to_portfolio_risk(
                    base_plan,
                    current_reserved_risk_krw=current_risk,
                    risk_policy=risk_policy,
                )
                if not plan.allowed:
                    risk_cap_rejections += 1
                    continue
                if plan.target_position_krw + 0.01 < base_plan.target_position_krw:
                    risk_scaled_entries += 1
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

        current_reserved_risk = reserved_risk_krw(position.plan for position in book.positions.values())
        peak_reserved_risk_pct = max(
            peak_reserved_risk_pct,
            current_reserved_risk / policy.portfolio_capital_krw * 100.0 if policy.portfolio_capital_krw > 0 else 0.0,
        )
        book.mark_metrics()

    for market in list(book.positions):
        price = book.last_prices.get(market, book.positions[market].average_price)
        if price > 0:
            book.sell(market, price, "end_of_replay_mark")
    book.mark_metrics()

    start_capital = policy.portfolio_capital_krw
    final_equity = book.cash
    return_pct = (final_equity / start_capital - 1.0) * 100.0 if start_capital > 0 else 0.0
    wins = sum(1 for value in book.closed_returns if value > 0)
    return {
        "paper_only": True,
        "read_only": True,
        "can_place_orders": False,
        "model": "shared_portfolio_v2_risk_capped_replay",
        "execution_model": {
            "fee_rate_each_side": 0.0004,
            "fixed_slippage_rate_each_side": 0.0005,
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
            "peak_reserved_risk_pct": round(peak_reserved_risk_pct, 3),
            "max_concurrent_positions": book.max_concurrent_positions,
        },
        "trades": {
            "positions_opened": book.positions_opened,
            "positions_closed": book.positions_closed,
            "wins": wins,
            "win_rate_pct": round(wins / len(book.closed_returns) * 100.0, 2) if book.closed_returns else 0.0,
            "mean_closed_return_pct": round(statistics.fmean(book.closed_returns), 4) if book.closed_returns else 0.0,
            "median_closed_return_pct": round(statistics.median(book.closed_returns), 4) if book.closed_returns else 0.0,
            "buy_orders": len(book.buy_tickets),
            "initial_orders": len(book.initial_tickets),
            "add_orders": len(book.add_tickets),
            "cycles_with_adds": book.cycles_with_adds,
            "cycles_with_adds_pct": round(book.cycles_with_adds / book.positions_closed * 100.0, 2) if book.positions_closed else 0.0,
            "initial_order_mean_krw": round(statistics.fmean(book.initial_tickets), 2) if book.initial_tickets else 0.0,
            "add_order_mean_krw": round(statistics.fmean(book.add_tickets), 2) if book.add_tickets else 0.0,
            "risk_cap_rejections": risk_cap_rejections,
            "risk_scaled_entries": risk_scaled_entries,
            "exit_reasons": dict(book.exit_reasons),
        },
        "policy": {
            "max_gross_exposure_pct": policy.max_gross_exposure_pct,
            "reserve_cash_pct": policy.reserve_cash_pct,
            "max_position_pct": policy.max_position_pct,
            "per_position_risk_budget_pct": policy.risk_budget_pct,
            "max_portfolio_risk_pct": risk_policy.max_portfolio_risk_pct,
            "max_positions": int(max_positions),
            "ladder_weights": list(policy.ladder_weights),
        },
    }


def run_policy_sweep(rows: list[dict[str, Any]], *, bucket_seconds: int = 300) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for preset in default_presets():
        replay = replay_shared_portfolio_risk_capped(
            rows,
            policy=preset.sizing,
            risk_policy=preset.risk,
            max_positions=preset.max_positions,
            bucket_seconds=bucket_seconds,
        )
        portfolio = replay["portfolio"]
        trades = replay["trades"]
        results.append(
            {
                "name": preset.name,
                "portfolio": portfolio,
                "trades": trades,
                "policy": replay["policy"],
            }
        )
    return {
        "paper_only": True,
        "read_only": True,
        "can_place_orders": False,
        "same_source_rows_for_all_presets": True,
        "rows": len(rows),
        "bucket_seconds": int(bucket_seconds),
        "presets": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Risk-capped shared-portfolio PAPER v2 replay")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--exchange", default="bithumb")
    parser.add_argument("--strategy", default="adaptive")
    parser.add_argument("--bucket-seconds", type=int, default=300)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()
    rows = load_memory_rows(
        Path(args.db),
        exchange=args.exchange,
        strategy=args.strategy,
        limit=max(0, int(args.limit)),
    )
    if args.sweep:
        result = run_policy_sweep(rows, bucket_seconds=args.bucket_seconds)
    else:
        preset = default_presets()[1]
        result = replay_shared_portfolio_risk_capped(
            rows,
            policy=preset.sizing,
            risk_policy=preset.risk,
            max_positions=preset.max_positions,
            bucket_seconds=args.bucket_seconds,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
