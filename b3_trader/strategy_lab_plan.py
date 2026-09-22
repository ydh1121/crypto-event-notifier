"""Price/weight projection from the unchanged execution rules; never places a trade."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .paper_constants import START_KRW
from .strategy_lab_rules import FEE_RATE, SLIPPAGE_RATE
from .strategy_lab_rules import StyleSpec, _num, buy_budget, entry_reason, style_intent


def project_plan(account: dict[str, Any], memory: dict[str, Any] | None, spec: StyleSpec | None) -> dict[str, Any]:
    if spec is None:
        return {"available": False, "reason": "unknown_spec"}
    held = _num(account.get("volume")) > 0 and _num(account.get("avg_price")) > 0
    average = _num(account.get("avg_price"))
    remaining = max(0, spec.max_buys - int(account.get("buy_count") or 0)) if held else spec.max_buys
    source_ts = _num((memory or {}).get("signal_ts")) or _num((memory or {}).get("ts"))
    eligible = bool(memory and entry_reason(spec, memory, account))
    intent = style_intent(spec, memory, account, account) if memory else None
    result = {
        "available": True, "paper_only": True, "source_ts": source_ts or None,
        "source_memory_id": (memory or {}).get("id"), "status": account.get("status"),
        "entry_conditions_met": eligible if memory else None,
        "action": intent[0] if intent else "wait", "reason": intent[1] if intent else None,
        "fee_rate": FEE_RATE, "slippage_rate": SLIPPAGE_RATE,
        "weight_basis_krw": START_KRW, "remaining_entries": remaining,
        "completed_entries": int(account.get("buy_count") or 0),
        "rules": asdict(spec), "entry_bias": _num(account.get("entry_bias")),
        "entries": [], "exits": [],
        "stop_price": average * (1 + spec.stop_loss_pct / 100) if held else None,
        "weak_market_exit": {"below": spec.exit_regime, "after_seconds": spec.min_hold_seconds},
    }
    if held:
        result["exits"] = [{"price": average * (1 + spec.take_profit_pct / 100),
                            "weight_pct": 100, "volume": account["volume"], "basis": "current_average"}]
    hypothetical = dict(account)
    first_price = average * (1 - spec.add_drop_pct / 100) if held else (_num((memory or {}).get("price")) if eligible else 0.0)
    for i in range(remaining):
        price = first_price if i == 0 else _num(hypothetical["avg_price"]) * (1 - spec.add_drop_pct / 100)
        if price <= 0:
            break
        amount = buy_budget(hypothetical, account, spec, price, START_KRW)
        if amount < 50_000:
            break
        fill_price = price * (1 + SLIPPAGE_RATE)
        quantity = amount / (1 + FEE_RATE) / fill_price
        result["entries"].append({"round": int(hypothetical.get("buy_count") or 0) + 1,
                                  "price": price, "fill_price": fill_price, "amount_krw": amount,
                                  "weight_pct": amount / START_KRW * 100, "volume": quantity,
                                  "basis": "next_condition" if i == 0 else "conditional_recalculation"})
        old_cost = _num(hypothetical.get("volume")) * _num(hypothetical.get("avg_price"))
        hypothetical["cash_krw"] = _num(hypothetical.get("cash_krw")) - amount
        hypothetical["volume"] = _num(hypothetical.get("volume")) + quantity
        hypothetical["avg_price"] = (old_cost + amount) / hypothetical["volume"]
        hypothetical["buy_count"] = int(hypothetical.get("buy_count") or 0) + 1
    return result
