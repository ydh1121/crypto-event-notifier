"""Pure Strategy Lab rules shared by execution and read-only plan projection.

Moved without changing thresholds, precedence, sizing or fill semantics.
No database, runner, network or order side effects.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

FEE_RATE = 0.0004
SLIPPAGE_RATE = 0.0005

@dataclass(frozen=True)
class StyleSpec:
    key: str
    label: str
    description: str
    entry_regime: float
    entry_score: float
    opportunity: float
    base_weight_pct: float
    max_position_pct: float
    max_buys: int
    add_drop_pct: float
    take_profit_pct: float
    stop_loss_pct: float
    exit_regime: float
    min_hold_seconds: float
    max_volatility_pct: float


STYLE_SPECS: dict[str, StyleSpec] = {
    "conservative": StyleSpec(
        "conservative", "보수적", "강한 시장·진입 조건에서 작은 비중으로 시작하고 손실을 빠르게 제한합니다.",
        66.0, 68.0, 70.0, 5.0, 20.0, 2, 3.5, 8.0, -4.0, 51.0, 900.0, 3.8,
    ),
    "balanced": StyleSpec(
        "balanced", "균형", "시장·진입·기회 점수를 고르게 사용하며 수익과 낙폭의 균형을 봅니다.",
        60.0, 60.0, 64.0, 7.5, 30.0, 3, 3.0, 10.0, -6.0, 47.0, 600.0, 5.2,
    ),
    "aggressive": StyleSpec(
        "aggressive", "공격적", "낮은 진입 문턱과 큰 허용 비중으로 더 많은 기회를 탐색합니다.",
        54.0, 55.0, 58.0, 10.0, 45.0, 4, 2.5, 14.0, -8.0, 42.0, 300.0, 8.0,
    ),
    "dca": StyleSpec(
        "dca", "분할매수", "초기 비중을 낮추고 평균단가 아래에서 여러 차례 분할 진입합니다.",
        58.0, 56.0, 60.0, 6.0, 45.0, 6, 2.0, 9.0, -12.0, 44.0, 600.0, 6.5,
    ),
    "contrarian": StyleSpec(
        "contrarian", "역추세", "충분한 조정·되돌림이 발생했지만 시장 체력이 남아 있는 구간을 탐색합니다.",
        50.0, 58.0, 58.0, 6.5, 30.0, 3, 3.0, 12.0, -8.0, 42.0, 900.0, 6.5,
    ),
    "swing": StyleSpec(
        "swing", "스윙", "시장 강도와 상대 모멘텀이 유지되는 구간에서 더 긴 목표 폭을 추구합니다.",
        62.0, 58.0, 66.0, 8.0, 35.0, 2, 4.0, 18.0, -6.5, 48.0, 1800.0, 6.0,
    ),
}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def entry_reason(spec: StyleSpec, row: dict[str, Any], learning: dict[str, Any]) -> str:
    regime = _num(row.get("regime_score"))
    entry = _num(row.get("entry_score"))
    opportunity = _num(row.get("opportunity_score"))
    volatility = _num(row.get("volatility_pct"))
    pullback = _num(row.get("pullback_pct"))
    asset_ret = _num(row.get("asset_return_pct"))
    relative = _num(row.get("asset_vs_majors_pct"))
    fib = row.get("fib_retrace")
    bias = _num(learning.get("entry_bias"))
    if volatility > spec.max_volatility_pct:
        return ""
    if regime < spec.entry_regime + bias or entry < spec.entry_score + bias or opportunity < spec.opportunity + bias:
        return ""
    if spec.key == "conservative" and (pullback < 2.0 or pullback > 18.0 or relative < -2.0):
        return ""
    if spec.key == "contrarian":
        if pullback < 6.0 or pullback > 28.0 or asset_ret > 2.0:
            return ""
        if fib is not None and not (0.30 <= _num(fib) <= 0.75):
            return ""
        return "meaningful pullback with surviving regime"
    if spec.key == "swing" and (asset_ret <= 0.0 or relative < -1.5):
        return ""
    if spec.key == "dca" and pullback < 2.0:
        return ""
    return "style thresholds satisfied"


def buy_budget(account: dict[str, Any], learning: dict[str, Any], spec: StyleSpec, price: float, initial_krw: float) -> float:
    current_value = _num(account.get("volume")) * price
    max_value = initial_krw * spec.max_position_pct / 100.0
    room = max(0.0, max_value - current_value)
    multiplier = min(1.25, max(0.55, _num(learning.get("weight_multiplier"), 1.0)))
    desired = initial_krw * spec.base_weight_pct / 100.0 * multiplier
    if int(account.get("buy_count") or 0) > 0:
        desired *= 0.78 if spec.key != "dca" else 0.92
    order_krw = min(_num(account.get("cash_krw")), room, desired)
    return order_krw


def style_intent(spec: StyleSpec, row: dict[str, Any], account: dict[str, Any], learning: dict[str, Any]) -> tuple[str, str] | None:
    price = _num(row.get("price"))
    if price <= 0:
        return None
    volume = _num(account.get("volume"))
    avg_price = _num(account.get("avg_price"))
    held_seconds = max(0.0, _num(row.get("signal_ts"), _num(row.get("ts"))) - _num(account.get("entry_ts")))
    if volume > 0 and avg_price > 0:
        pnl_pct = (price / avg_price - 1.0) * 100.0
        if pnl_pct <= spec.stop_loss_pct:
            return ("sell", "style hard stop")
        if pnl_pct >= spec.take_profit_pct:
            return ("sell", "style take profit")
        if held_seconds >= spec.min_hold_seconds and _num(row.get("regime_score")) < spec.exit_regime:
            return ("sell", "regime weakened")
        if int(account.get("buy_count") or 0) < spec.max_buys:
            drop_from_avg = (price / avg_price - 1.0) * 100.0
            reason = entry_reason(spec, row, learning)
            if reason and drop_from_avg <= -spec.add_drop_pct:
                return ("buy", f"style add after {abs(drop_from_avg):.2f}% drop")
        return None
    reason = entry_reason(spec, row, learning)
    if reason:
        return ("buy", reason)
    return None
