from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .auto_demo_v2 import DB_PATH
from .paper_position_plan_v2 import PositionSizingPolicy, plan_new_position


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_shadow_portfolio(
    rows: Iterable[dict[str, Any]],
    *,
    policy: PositionSizingPolicy | None = None,
    max_positions: int = 3,
) -> dict[str, Any]:
    """Build a flat-start shared-capital proposal from current PAPER signals.

    This is a read-only comparison surface. It does not alter the legacy adaptive
    accounts and cannot place an order. Full target capital is reserved when a
    candidate is accepted, so partially filled ladders cannot overbook the same
    10M KRW pool.
    """

    policy = policy or PositionSizingPolicy()
    ordered = sorted(
        [dict(row) for row in rows],
        key=lambda row: (
            _num(row.get("opportunity_score")),
            _num(row.get("entry_score")),
            _num(row.get("regime_score")),
        ),
        reverse=True,
    )

    reserved = 0.0
    proposals: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for row in ordered:
        if len(proposals) >= max(1, int(max_positions)):
            break
        signal = row.get("signal") if isinstance(row.get("signal"), dict) else {}
        plan = plan_new_position(
            first_entry_price=_num(row.get("price")),
            regime_score=_num(row.get("regime_score")),
            entry_score=_num(row.get("entry_score")),
            opportunity_score=_num(row.get("opportunity_score")),
            volatility_pct=_num(signal.get("volatility_pct")),
            current_reserved_exposure_krw=reserved,
            available_cash_krw=max(0.0, policy.portfolio_capital_krw - reserved),
            policy=policy,
        )
        base = {
            "exchange": str(row.get("exchange") or ""),
            "market": str(row.get("market") or ""),
            "symbol": str(row.get("symbol") or ""),
            "price": _num(row.get("price")),
            "regime_score": _num(row.get("regime_score")),
            "entry_score": _num(row.get("entry_score")),
            "opportunity_score": _num(row.get("opportunity_score")),
            "legacy_trade_intent": str(row.get("trade_intent") or ""),
        }
        if not plan.allowed:
            if len(rejected) < 20:
                rejected.append({**base, "reason": plan.reason})
            continue
        reserved = round(reserved + plan.reserved_position_krw, 2)
        proposals.append({**base, "plan": plan.to_dict()})

    return {
        "paper_only": True,
        "read_only": True,
        "can_place_orders": False,
        "shared_portfolio_budget": True,
        "portfolio_capital_krw": policy.portfolio_capital_krw,
        "reserved_target_capital_krw": reserved,
        "remaining_unreserved_capital_krw": round(policy.portfolio_capital_krw - reserved, 2),
        "max_positions": max(1, int(max_positions)),
        "proposals": proposals,
        "rejected_top": rejected,
        "policy": {
            "max_gross_exposure_pct": policy.max_gross_exposure_pct,
            "reserve_cash_pct": policy.reserve_cash_pct,
            "max_position_pct": policy.max_position_pct,
            "risk_budget_pct": policy.risk_budget_pct,
            "ladder_weights": list(policy.ladder_weights),
            "new_entry_floors": {
                "regime": policy.min_regime_for_new,
                "entry": policy.min_entry_for_new,
                "opportunity": policy.min_opportunity_for_new,
            },
            "thesis_regime_floor": policy.thesis_regime_floor,
        },
    }


def load_current_signals(
    path: Path | str = DB_PATH,
    *,
    exchange: str = "bithumb",
    strategy: str = "adaptive",
) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_signals_mx'"
        ).fetchone()
        if not exists:
            return []
        rows = conn.execute(
            """SELECT exchange,market,strategy,symbol,price,regime_score,entry_score,
                      opportunity_score,trade_intent,signal_json
               FROM research_signals_mx
               WHERE exchange=? AND strategy=?""",
            (str(exchange).strip().lower(), str(strategy).strip().lower()),
        ).fetchall()
        output: list[dict[str, Any]] = []
        for source in rows:
            row = dict(source)
            row["signal"] = _safe_json(row.pop("signal_json", "{}"))
            output.append(row)
        return output
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only shared-portfolio Position Sizing v2 shadow planner")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--exchange", default="bithumb")
    parser.add_argument("--strategy", default="adaptive")
    parser.add_argument("--max-positions", type=int, default=3)
    args = parser.parse_args()
    rows = load_current_signals(args.db, exchange=args.exchange, strategy=args.strategy)
    result = build_shadow_portfolio(rows, max_positions=args.max_positions)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
