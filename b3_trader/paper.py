from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Fill:
    side: str
    price: float
    volume: float
    krw: float
    reason: str


@dataclass
class PaperAccount:
    start_krw: float
    max_position_krw: float
    max_daily_loss_pct: float
    cash_krw: float = field(init=False)
    b3_volume: float = 0.0
    avg_price: float = 0.0
    fills: list[Fill] = field(default_factory=list)
    day: date = field(default_factory=date.today)
    day_start_equity: float = field(init=False)

    def __post_init__(self) -> None:
        self.cash_krw = self.start_krw
        self.day_start_equity = self.start_krw

    def equity(self, price: float) -> float:
        return self.cash_krw + self.b3_volume * price

    def position_value(self, price: float) -> float:
        return self.b3_volume * price

    def _roll_day(self, price: float) -> None:
        today = date.today()
        if today != self.day:
            self.day = today
            self.day_start_equity = self.equity(price)

    def daily_drawdown_pct(self, price: float) -> float:
        self._roll_day(price)
        if self.day_start_equity <= 0:
            return 0.0
        return max(0.0, (self.day_start_equity - self.equity(price)) / self.day_start_equity * 100.0)

    def can_buy(self, price: float, order_krw: float) -> tuple[bool, str]:
        self._roll_day(price)
        if self.daily_drawdown_pct(price) >= self.max_daily_loss_pct:
            return False, "daily loss circuit breaker"
        if order_krw <= 0 or order_krw > self.cash_krw:
            return False, "insufficient paper KRW"
        if self.position_value(price) + order_krw > self.max_position_krw:
            return False, "max B3 position reached"
        return True, "ok"

    def buy(self, price: float, order_krw: float, reason: str) -> Fill:
        allowed, why = self.can_buy(price, order_krw)
        if not allowed:
            raise RuntimeError(why)
        volume = order_krw / price
        previous_cost = self.avg_price * self.b3_volume
        self.b3_volume += volume
        self.cash_krw -= order_krw
        self.avg_price = (previous_cost + order_krw) / self.b3_volume
        fill = Fill("buy", price, volume, order_krw, reason)
        self.fills.append(fill)
        return fill

    def sell_all(self, price: float, reason: str) -> Fill | None:
        if self.b3_volume <= 0:
            return None
        volume = self.b3_volume
        proceeds = volume * price
        self.cash_krw += proceeds
        self.b3_volume = 0.0
        self.avg_price = 0.0
        fill = Fill("sell", price, volume, proceeds, reason)
        self.fills.append(fill)
        return fill
