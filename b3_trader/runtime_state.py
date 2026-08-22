from __future__ import annotations

import copy
import threading
import time
from typing import Any


class RuntimeState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.started_at = time.time()
        self.paused = False
        self.kill_switch = False
        self.restart_required = False
        self.last_error: dict[str, Any] | None = None
        self.assets: dict[str, dict[str, Any]] = {}
        self.portfolio: dict[str, Any] = {}
        self.sync: dict[str, Any] = {"status": "idle"}
        self.backup: dict[str, Any] = {"status": "idle"}

    def set_asset(self, market: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self.assets[market] = copy.deepcopy(payload)

    def remove_asset(self, market: str) -> None:
        with self._lock:
            self.assets.pop(market, None)

    def set_portfolio(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self.portfolio = copy.deepcopy(payload)

    def set_error(self, error: Exception | str, *, scope: str = "engine") -> None:
        with self._lock:
            self.last_error = {
                "ts": time.time(),
                "scope": scope,
                "message": str(error),
                "type": type(error).__name__ if isinstance(error, Exception) else "Error",
            }

    def set_sync(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self.sync = copy.deepcopy(payload)

    def set_backup(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self.backup = copy.deepcopy(payload)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "started_at": self.started_at,
                "uptime_seconds": round(time.time() - self.started_at, 1),
                "paused": self.paused,
                "kill_switch": self.kill_switch,
                "restart_required": self.restart_required,
                "last_error": copy.deepcopy(self.last_error),
                "assets": copy.deepcopy(self.assets),
                "portfolio": copy.deepcopy(self.portfolio),
                "sync": copy.deepcopy(self.sync),
                "backup": copy.deepcopy(self.backup),
            }
