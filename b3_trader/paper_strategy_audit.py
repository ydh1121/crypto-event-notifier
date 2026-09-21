from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH, DEFAULT_BASE_WEIGHT_PCT, MAX_POSITION_PCT, START_KRW


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(math.ceil(fraction * len(ordered))) - 1))
    return ordered[index]


def _buy_cycles(rows: list[sqlite3.Row]) -> tuple[list[list[float]], list[float], list[float]]:
    cycles: list[list[float]] = []
    current: list[float] = []
    first_buys: list[float] = []
    adds: list[float] = []
    for row in rows:
        side = str(row["side"] or "").lower()
        if side == "sell":
            if current:
                cycles.append(current)
                current = []
            continue
        if side != "buy":
            continue
        krw = max(0.0, _num(row["krw"]))
        if not current:
            first_buys.append(krw)
        else:
            adds.append(krw)
        current.append(krw)
    if current:
        cycles.append(current)
    return cycles, first_buys, adds


def _execution_blockers(conn: sqlite3.Connection, exchange: str, strategy: str) -> dict[str, int]:
    if not _table_exists(conn, "research_market_memory_mx"):
        return {}
    rows = conn.execute(
        """SELECT trade_intent,feature_json FROM research_market_memory_mx
           WHERE exchange=? AND strategy=? ORDER BY id""",
        (exchange, strategy),
    ).fetchall()
    blockers: Counter[str] = Counter()
    for row in rows:
        try:
            feature = json.loads(str(row["feature_json"] or "{}"))
        except json.JSONDecodeError:
            continue
        if not isinstance(feature, dict):
            continue
        note = str(feature.get("execution_note") or "").strip()
        if note.startswith("blocked:"):
            blockers[note.split(";", 1)[0][:160]] += 1
    return dict(blockers.most_common(12))


def audit_paper_strategy(
    path: Path | str = DB_PATH,
    *,
    exchange: str = "bithumb",
    strategy: str = "adaptive",
) -> dict[str, Any]:
    normalized_exchange = str(exchange or "").strip().lower()
    normalized_strategy = str(strategy or "").strip().lower()
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        fills: list[sqlite3.Row] = []
        if _table_exists(conn, "research_fills_mx"):
            fills = conn.execute(
                """SELECT id,market,side,krw,reason,ts FROM research_fills_mx
                   WHERE exchange=? AND strategy=? ORDER BY market,id""",
                (normalized_exchange, normalized_strategy),
            ).fetchall()

        buy_rows = [row for row in fills if str(row["side"] or "").lower() == "buy"]
        sell_rows = [row for row in fills if str(row["side"] or "").lower() == "sell"]
        tickets = [max(0.0, _num(row["krw"])) for row in buy_rows]

        by_market: dict[str, list[sqlite3.Row]] = {}
        for row in fills:
            by_market.setdefault(str(row["market"] or ""), []).append(row)
        all_cycles: list[list[float]] = []
        first_buys: list[float] = []
        add_buys: list[float] = []
        for rows in by_market.values():
            cycles, first, adds = _buy_cycles(rows)
            all_cycles.extend(cycles)
            first_buys.extend(first)
            add_buys.extend(adds)

        current_intents: Counter[str] = Counter()
        current_reasons: Counter[str] = Counter()
        if _table_exists(conn, "research_signals_mx"):
            rows = conn.execute(
                """SELECT trade_intent,reason FROM research_signals_mx
                   WHERE exchange=? AND strategy=?""",
                (normalized_exchange, normalized_strategy),
            ).fetchall()
            for row in rows:
                current_intents[str(row["trade_intent"] or "unknown")] += 1
                reason = str(row["reason"] or "").strip()
                if reason:
                    current_reasons[reason[:180]] += 1

        small_500 = sum(1 for value in tickets if value <= 500_000.0)
        small_750 = sum(1 for value in tickets if value <= 750_000.0)
        cycles_with_adds = sum(1 for cycle in all_cycles if len(cycle) > 1)
        max_buys = max((len(cycle) for cycle in all_cycles), default=0)

        return {
            "paper_only": True,
            "read_only": True,
            "can_place_orders": False,
            "exchange": normalized_exchange,
            "strategy": normalized_strategy,
            "db": str(path),
            "capital_model": {
                "per_market_start_krw": START_KRW,
                "shared_portfolio_budget": False,
                "default_base_weight_pct": DEFAULT_BASE_WEIGHT_PCT,
                "default_max_position_pct": MAX_POSITION_PCT,
                "exploration_weight_multiplier": 0.55,
                "add_weight_multiplier": 0.75,
                "suggested_weight_floor_pct": 2.5,
                "suggested_weight_ceiling_pct": 15.0,
            },
            "fills": {
                "total": len(fills),
                "buys": len(buy_rows),
                "sells": len(sell_rows),
                "buy_ticket_krw": {
                    "min": round(min(tickets), 2) if tickets else 0.0,
                    "median": round(statistics.median(tickets), 2) if tickets else 0.0,
                    "mean": round(statistics.fmean(tickets), 2) if tickets else 0.0,
                    "p90": round(_percentile(tickets, 0.90), 2),
                    "max": round(max(tickets), 2) if tickets else 0.0,
                    "lte_500k_pct": round(small_500 / len(tickets) * 100.0, 2) if tickets else 0.0,
                    "lte_750k_pct": round(small_750 / len(tickets) * 100.0, 2) if tickets else 0.0,
                },
            },
            "averaging": {
                "cycles": len(all_cycles),
                "cycles_with_adds": cycles_with_adds,
                "cycles_with_adds_pct": round(cycles_with_adds / len(all_cycles) * 100.0, 2) if all_cycles else 0.0,
                "add_fill_count": len(add_buys),
                "max_buys_in_cycle": max_buys,
                "first_buy_mean_krw": round(statistics.fmean(first_buys), 2) if first_buys else 0.0,
                "add_buy_mean_krw": round(statistics.fmean(add_buys), 2) if add_buys else 0.0,
                "add_vs_first_size_ratio": round(
                    statistics.fmean(add_buys) / statistics.fmean(first_buys), 4
                    if add_buys and first_buys and statistics.fmean(first_buys) > 0 else 0.0
                ) if add_buys and first_buys and statistics.fmean(first_buys) > 0 else 0.0,
            },
            "current_intents": dict(current_intents),
            "current_reason_top": dict(current_reasons.most_common(10)),
            "historical_execution_blockers": _execution_blockers(conn, normalized_exchange, normalized_strategy),
            "static_findings": [
                "per_market_independent_10m_accounts_are_not_shared_portfolio_allocation",
                "exploration_orders_are_deliberately_reduced_to_55_percent_of_weight",
                "add_orders_are_deliberately_reduced_to_75_percent_of_weight",
                "averaging_requires_cooldown_plus_high_opportunity_plus_price_trigger",
                "paper_fill_model_is_not_yet_a_live_order_lifecycle",
            ],
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only PAPER sizing and averaging audit")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--exchange", default="bithumb")
    parser.add_argument("--strategy", default="adaptive")
    args = parser.parse_args()
    result = audit_paper_strategy(args.db, exchange=args.exchange, strategy=args.strategy)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
