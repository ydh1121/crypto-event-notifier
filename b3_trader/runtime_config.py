from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimeConfig:
    poll_seconds: float = 5.0
    candle_refresh_seconds: float = 60.0
    external_refresh_seconds: float = 60.0
    default_order_krw: float = 50_000.0
    default_max_position_krw: float = 300_000.0
    max_total_exposure_krw: float = 600_000.0
    buy_cooldown_seconds: float = 1800.0
    adaptive_size_min_multiplier: float = 0.60
    adaptive_size_max_multiplier: float = 1.25
    min_regime_score: float = 65.0
    min_entry_score: float = 68.0
    max_daily_loss_pct: float = 3.0
    max_slippage_bps: float = 35.0
    max_spread_bps: float = 45.0
    max_orders_per_minute: int = 2
    max_orders_per_hour: int = 8
    btc_flash_crash_pct: float = -3.0
    btc_flash_window_candles: int = 3

    def validate(self) -> "RuntimeConfig":
        if self.poll_seconds < 1: raise ValueError("poll_seconds must be >= 1")
        if self.candle_refresh_seconds < 10: raise ValueError("candle_refresh_seconds must be >= 10")
        if self.external_refresh_seconds < 15: raise ValueError("external_refresh_seconds must be >= 15")
        if self.default_order_krw <= 0: raise ValueError("default_order_krw must be positive")
        if self.default_max_position_krw <= 0: raise ValueError("default_max_position_krw must be positive")
        if self.max_total_exposure_krw <= 0: raise ValueError("max_total_exposure_krw must be positive")
        if not (0 <= self.min_regime_score <= 100 and 0 <= self.min_entry_score <= 100): raise ValueError("score thresholds must be 0..100")
        if self.max_orders_per_minute < 1 or self.max_orders_per_hour < 1: raise ValueError("order limits must be positive")
        return self

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RuntimeConfig":
        allowed = {field.name for field in fields(cls)}
        payload = {key: value for key, value in raw.items() if key in allowed}
        return cls(**payload).validate()


class RuntimeConfigStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._mtime_ns = -1
        self._config = RuntimeConfig()
        if self.path.exists(): self.reload(force=True)
        else: self.save(self._config)

    def get(self) -> RuntimeConfig:
        self.reload()
        with self._lock: return self._config

    def reload(self, force: bool = False) -> bool:
        with self._lock:
            try: mtime_ns = self.path.stat().st_mtime_ns
            except FileNotFoundError: return False
            if not force and mtime_ns == self._mtime_ns: return False
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._config = RuntimeConfig.from_dict(raw.get("trading", raw))
            self._mtime_ns = mtime_ns
            return True

    def patch(self, updates: dict[str, Any]) -> RuntimeConfig:
        with self._lock:
            current = asdict(self.get())
            current.update(updates)
            config = RuntimeConfig.from_dict(current)
            self.save(config)
            return config

    def save(self, config: RuntimeConfig) -> None:
        with self._lock:
            payload = {
                "schema_version": 2,
                "mode": "paper",
                "trading": asdict(config),
                "storage_policy": {
                    "local_sqlite": "authoritative runtime database",
                    "google_drive": "backup/mirror via rclone",
                    "github_private": "code and non-secret desired state",
                    "cloudflare_pages": "optional static dashboard mirror",
                },
            }
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, self.path)
            self._config = config
            self._mtime_ns = self.path.stat().st_mtime_ns
