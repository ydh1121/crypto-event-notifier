from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping

from .paper import Fill


@dataclass
class Position:
    volume: float = 0.0
    avg_price: float = 0.0


@dataclass
class MultiPaperPortfolio:
    start_krw: float
    max_total_exposure_krw: float
    max_daily_loss_pct: float
    cash_krw: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    day: date = field(default_factory=date.today)
    day_start_equity: float = field(init=False)

    def __post_init__(self) -> None:
        self.cash_krw = self.start_krw
        self.day_start_equity = self.start_krw

    def position(self, market: str) -> Position:
        return self.positions.setdefault(market, Position())

    def position_value(self, market: str, price: float) -> float:
        return self.position(market).volume * price

    def total_exposure(self, prices: Mapping[str, float]) -> float:
        return sum(position.volume * float(prices.get(market, position.avg_price)) for market, position in self.positions.items() if position.volume > 0)

    def equity(self, prices: Mapping[str, float]) -> float:
        return self.cash_krw + self.total_exposure(prices)

    def _roll_day(self, prices: Mapping[str, float]) -> None:
        today = date.today()
        if today != self.day:
            self.day = today
            self.day_start_equity = self.equity(prices)

    def daily_drawdown_pct(self, prices: Mapping[str, float]) -> float:
        self._roll_day(prices)
        if self.day_start_equity <= 0:
            return 0.0
        return max(0.0, (self.day_start_equity - self.equity(prices)) / self.day_start_equity * 100.0)

    def can_buy(self, *, market: str, price: float, order_krw: float, max_position_krw: float, prices: Mapping[str, float]) -> tuple[bool, str]:
        self._roll_day(prices)
        if self.daily_drawdown_pct(prices) >= self.max_daily_loss_pct:
            return False, "daily loss circuit breaker"
        if order_krw <= 0 or order_krw > self.cash_krw:
            return False, "insufficient paper KRW"
        if self.position_value(market, price) + order_krw > max_position_krw:
            return False, "max asset position reached"
        if self.total_exposure(prices) + order_krw > self.max_total_exposure_krw:
            return False, "max total exposure reached"
        return True, "ok"

    def buy(self, *, market: str, price: float, order_krw: float, reason: str, max_position_krw: float, prices: Mapping[str, float]) -> Fill:
        allowed, why = self.can_buy(market=market, price=price, order_krw=order_krw, max_position_krw=max_position_krw, prices=prices)
        if not allowed:
            raise RuntimeError(why)
        position = self.position(market)
        volume = order_krw / price
        previous_cost = position.avg_price * position.volume
        position.volume += volume
        position.avg_price = (previous_cost + order_krw) / position.volume
        self.cash_krw -= order_krw
        fill = Fill("buy", price, volume, order_krw, reason)
        self.fills.append(fill)
        return fill

    def sell_all(self, market: str, price: float, reason: str) -> Fill | None:
        position = self.position(market)
        if position.volume <= 0:
            return None
        volume = position.volume
        proceeds = volume * price
        self.cash_krw += proceeds
        position.volume = 0.0
        position.avg_price = 0.0
        fill = Fill("sell", price, volume, proceeds, reason)
        self.fills.append(fill)
        return fill

    def snapshot(self, prices: Mapping[str, float]) -> dict:
        return {
            "cash_krw": round(self.cash_krw, 2),
            "equity_krw": round(self.equity(prices), 2),
            "exposure_krw": round(self.total_exposure(prices), 2),
            "daily_drawdown_pct": round(self.daily_drawdown_pct(prices), 4),
            "positions": {
                market: {
                    "volume": round(position.volume, 12),
                    "avg_price": round(position.avg_price, 12),
                    "value_krw": round(position.volume * float(prices.get(market, position.avg_price)), 2),
                }
                for market, position in self.positions.items() if position.volume > 0
            },
        }
