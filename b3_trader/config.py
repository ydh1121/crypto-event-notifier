from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None: return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    value = os.getenv(name); return float(value) if value is not None else default


def _int(name: str, default: int) -> int:
    value = os.getenv(name); return int(value) if value is not None else default


def _str(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
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
    adaptive_size_min_multiplier: float = field(default_factory=lambda: _float("ADAPTIVE_SIZE_MIN_MULTIPLIER", 0.60))
    adaptive_size_max_multiplier: float = field(default_factory=lambda: _float("ADAPTIVE_SIZE_MAX_MULTIPLIER", 1.25))
    min_regime_score: float = field(default_factory=lambda: _float("MIN_REGIME_SCORE", 65.0))
    min_entry_score: float = field(default_factory=lambda: _float("MIN_ENTRY_SCORE", 68.0))
    max_daily_loss_pct: float = field(default_factory=lambda: _float("MAX_DAILY_LOSS_PCT", 3.0))
    max_slippage_bps: float = field(default_factory=lambda: _float("MAX_SLIPPAGE_BPS", 35.0))
    max_spread_bps: float = field(default_factory=lambda: _float("MAX_SPREAD_BPS", 45.0))
    max_orders_per_minute: int = field(default_factory=lambda: _int("MAX_ORDERS_PER_MINUTE", 2))
    max_orders_per_hour: int = field(default_factory=lambda: _int("MAX_ORDERS_PER_HOUR", 8))
    btc_flash_crash_pct: float = field(default_factory=lambda: _float("BTC_FLASH_CRASH_PCT", -3.0))
    btc_flash_window_candles: int = field(default_factory=lambda: _int("BTC_FLASH_WINDOW_CANDLES", 3))
    journal_db: str = field(default_factory=lambda: _str("B3_JOURNAL_DB", "b3_trader/data/crypto_trader.sqlite3"))
    asset_registry_path: str = field(default_factory=lambda: _str("ASSET_REGISTRY_PATH", "control/assets.json"))
    runtime_config_path: str = field(default_factory=lambda: _str("RUNTIME_CONFIG_PATH", "control/runtime.json"))
    dashboard_dir: str = field(default_factory=lambda: _str("DASHBOARD_DIR", "dashboard"))
    news_modifier: float = field(default_factory=lambda: _float("NEWS_MODIFIER", 0.0))
    service_host: str = field(default_factory=lambda: _str("DASHBOARD_HOST", "0.0.0.0"))
    service_port: int = field(default_factory=lambda: _int("DASHBOARD_PORT", 8765))
    health_stale_seconds: float = field(default_factory=lambda: _float("HEALTH_STALE_SECONDS", 180.0))
    dashboard_token: str = field(default_factory=lambda: _str("DASHBOARD_TOKEN", ""))
    telegram_enabled: bool = field(default_factory=lambda: _bool("TELEGRAM_ENABLED", False))
    telegram_token: str = field(default_factory=lambda: _str("TELEGRAM_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: _str("TELEGRAM_CHAT_ID", ""))
    auto_git_sync: bool = field(default_factory=lambda: _bool("AUTO_GIT_SYNC", True))
    auto_git_push_control: bool = field(default_factory=lambda: _bool("AUTO_GIT_PUSH_CONTROL", True))
    git_sync_branch: str = field(default_factory=lambda: _str("GIT_SYNC_BRANCH", "b3-auto-trader-phase1"))
    git_sync_interval_seconds: float = field(default_factory=lambda: _float("GIT_SYNC_INTERVAL_SECONDS", 60.0))
    git_repo_dir: str = field(default_factory=lambda: _str("GIT_REPO_DIR", "."))
    backup_interval_seconds: float = field(default_factory=lambda: _float("BACKUP_INTERVAL_SECONDS", 3600.0))
    local_backup_dir: str = field(default_factory=lambda: _str("LOCAL_BACKUP_DIR", "b3_trader/data/backups"))
    rclone_remote: str = field(default_factory=lambda: _str("RCLONE_REMOTE", "gdrive:Crypto Auto Trader/backups"))
    live_trading_enabled: bool = field(default_factory=lambda: _bool("LIVE_TRADING_ENABLED", False))
    live_trading_ack: str = field(default_factory=lambda: _str("LIVE_TRADING_ACK", ""))
    bithumb_access_key: str = field(default_factory=lambda: _str("BITHUMB_ACCESS_KEY", ""))
    bithumb_secret_key: str = field(default_factory=lambda: _str("BITHUMB_SECRET_KEY", ""))

    @property
    def live_trading_armed(self) -> bool:
        return self.live_trading_enabled and self.live_trading_ack == "I_UNDERSTAND_REAL_ORDERS" and bool(self.bithumb_access_key) and bool(self.bithumb_secret_key)
