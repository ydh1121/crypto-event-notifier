from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def _str(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    # default_factory is intentional: .env is loaded before Settings() is created.
    market: str = field(default_factory=lambda: _str("B3_MARKET", "KRW-B3"))
    btc_market: str = field(default_factory=lambda: _str("BTC_MARKET", "KRW-BTC"))
    eth_market: str = field(default_factory=lambda: _str("ETH_MARKET", "KRW-ETH"))

    poll_seconds: float = field(default_factory=lambda: _float("POLL_SECONDS", 5.0))
    candle_refresh_seconds: float = field(default_factory=lambda: _float("CANDLE_REFRESH_SECONDS", 60.0))
    external_refresh_seconds: float = field(default_factory=lambda: _float("EXTERNAL_REFRESH_SECONDS", 60.0))
    candle_unit_minutes: int = field(default_factory=lambda: _int("CANDLE_UNIT_MINUTES", 5))
    candle_count: int = field(default_factory=lambda: _int("CANDLE_COUNT", 48))

    websocket_enabled: bool = field(default_factory=lambda: _bool("WEBSOCKET_ENABLED", True))
    private_websocket_enabled: bool = field(default_factory=lambda: _bool("PRIVATE_WEBSOCKET_ENABLED", False))
    okx_derivatives_enabled: bool = field(default_factory=lambda: _bool("OKX_DERIVATIVES_ENABLED", True))

    paper_start_krw: float = field(default_factory=lambda: _float("PAPER_START_KRW", 1_000_000.0))
    paper_max_position_krw: float = field(default_factory=lambda: _float("PAPER_MAX_POSITION_KRW", 300_000.0))
    order_krw: float = field(default_factory=lambda: _float("ORDER_KRW", 50_000.0))
    buy_cooldown_seconds: float = field(default_factory=lambda: _float("BUY_COOLDOWN_SECONDS", 1800.0))
    adaptive_size_min_multiplier: float = field(
        default_factory=lambda: _float("ADAPTIVE_SIZE_MIN_MULTIPLIER", 0.60)
    )
    adaptive_size_max_multiplier: float = field(
        default_factory=lambda: _float("ADAPTIVE_SIZE_MAX_MULTIPLIER", 1.25)
    )

    min_regime_score: float = field(default_factory=lambda: _float("MIN_REGIME_SCORE", 65.0))
    min_entry_score: float = field(default_factory=lambda: _float("MIN_ENTRY_SCORE", 68.0))
    max_daily_loss_pct: float = field(default_factory=lambda: _float("MAX_DAILY_LOSS_PCT", 3.0))
    max_slippage_bps: float = field(default_factory=lambda: _float("MAX_SLIPPAGE_BPS", 35.0))
    max_spread_bps: float = field(default_factory=lambda: _float("MAX_SPREAD_BPS", 45.0))
    max_orders_per_minute: int = field(default_factory=lambda: _int("MAX_ORDERS_PER_MINUTE", 2))
    max_orders_per_hour: int = field(default_factory=lambda: _int("MAX_ORDERS_PER_HOUR", 8))
    btc_flash_crash_pct: float = field(default_factory=lambda: _float("BTC_FLASH_CRASH_PCT", -3.0))
    btc_flash_window_candles: int = field(
        default_factory=lambda: _int("BTC_FLASH_WINDOW_CANDLES", 3)
    )

    journal_db: str = field(
        default_factory=lambda: _str("B3_JOURNAL_DB", "b3_trader/data/b3_trader.sqlite3")
    )
    news_modifier: float = field(default_factory=lambda: _float("NEWS_MODIFIER", 0.0))
    service_port: int = field(default_factory=lambda: _int("PORT", 8080))
    health_stale_seconds: float = field(
        default_factory=lambda: _float("HEALTH_STALE_SECONDS", 180.0)
    )

    live_trading_enabled: bool = field(default_factory=lambda: _bool("LIVE_TRADING_ENABLED", False))
    live_trading_ack: str = field(default_factory=lambda: _str("LIVE_TRADING_ACK", ""))

    bithumb_access_key: str = field(default_factory=lambda: _str("BITHUMB_ACCESS_KEY", ""))
    bithumb_secret_key: str = field(default_factory=lambda: _str("BITHUMB_SECRET_KEY", ""))

    @property
    def live_trading_armed(self) -> bool:
        return (
            self.live_trading_enabled
            and self.live_trading_ack == "I_UNDERSTAND_REAL_ORDERS"
            and bool(self.bithumb_access_key)
            and bool(self.bithumb_secret_key)
        )
