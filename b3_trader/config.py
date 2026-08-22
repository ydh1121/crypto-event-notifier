from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


@dataclass(frozen=True)
class Settings:
    market: str = os.getenv("B3_MARKET", "KRW-B3")
    btc_market: str = os.getenv("BTC_MARKET", "KRW-BTC")
    eth_market: str = os.getenv("ETH_MARKET", "KRW-ETH")
    poll_seconds: float = _float("POLL_SECONDS", 10.0)

    paper_start_krw: float = _float("PAPER_START_KRW", 1_000_000.0)
    paper_max_position_krw: float = _float("PAPER_MAX_POSITION_KRW", 300_000.0)
    order_krw: float = _float("ORDER_KRW", 50_000.0)

    min_regime_score: float = _float("MIN_REGIME_SCORE", 65.0)
    min_entry_score: float = _float("MIN_ENTRY_SCORE", 68.0)
    max_daily_loss_pct: float = _float("MAX_DAILY_LOSS_PCT", 3.0)
    max_slippage_bps: float = _float("MAX_SLIPPAGE_BPS", 35.0)

    live_trading_enabled: bool = _bool("LIVE_TRADING_ENABLED", False)
    live_trading_ack: str = os.getenv("LIVE_TRADING_ACK", "")

    bithumb_access_key: str = os.getenv("BITHUMB_ACCESS_KEY", "")
    bithumb_secret_key: str = os.getenv("BITHUMB_SECRET_KEY", "")

    @property
    def live_trading_armed(self) -> bool:
        return (
            self.live_trading_enabled
            and self.live_trading_ack == "I_UNDERSTAND_REAL_ORDERS"
            and bool(self.bithumb_access_key)
            and bool(self.bithumb_secret_key)
        )
