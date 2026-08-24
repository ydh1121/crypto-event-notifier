from __future__ import annotations

import json
import os
import signal
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from .reference_components import ReferenceComponentWatcher
from .research_warehouse import ResearchWarehouse

CONTROL_PATH = Path("b3_trader/data/research-platform/components.json")
STATUS_PATH = Path("b3_trader/data/research-platform/status.json")
LOG_PATH = Path("b3_trader/data/research-platform/supervisor.log")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)


def _log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n"
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line)
    try:
        if LOG_PATH.stat().st_size > 2_000_000:
            text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
            LOG_PATH.write_text(text[-1_000_000:], encoding="utf-8")
    except OSError:
        pass


def _default_control() -> dict[str, Any]:
    return {
        "version": 1,
        "enabled": True,
        "components": {
            "warehouse-export": {"enabled": True, "interval_seconds": 300},
            "reference-version-watch": {"enabled": True, "interval_seconds": 21600},
        },
    }


def load_control() -> dict[str, Any]:
    default = _default_control()
    if not CONTROL_PATH.exists():
        _atomic_json(CONTROL_PATH, default)
        return default
    try:
        loaded = json.loads(CONTROL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    if not isinstance(loaded, dict):
        return default
    loaded.setdefault("version", 1)
    loaded.setdefault("enabled", True)
    loaded.setdefault("components", {})
    for name, config in default["components"].items():
        current = loaded["components"].setdefault(name, {})
        for key, value in config.items():
            current.setdefault(key, value)
    return loaded


@dataclass
class ComponentState:
    name: str
    enabled: bool
    interval_seconds: float
    status: str = "starting"
    last_started_at: float = 0.0
    last_finished_at: float = 0.0
    last_success_at: float = 0.0
    last_error_at: float = 0.0
    last_error: str = ""
    runs: int = 0
    last_result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "status": self.status,
            "last_started_at": self.last_started_at,
            "last_finished_at": self.last_finished_at,
            "last_success_at": self.last_success_at,
            "last_error_at": self.last_error_at,
            "last_error": self.last_error,
            "runs": self.runs,
            "last_result": self.last_result,
        }


class ResearchSupervisor:
    """Non-trading sidecar for research storage and external-version observation.

    It cannot place orders, alter PAPER strategy profiles or auto-promote external code.
    A failed research component is isolated and retried without stopping the trader.
    """

    def __init__(self) -> None:
        load_dotenv()
        self.stop_event = threading.Event()
        self.started_at = time.time()
        self.control = load_control()
        self.warehouse = ResearchWarehouse()
        self.reference_watcher = ReferenceComponentWatcher()
        self.threads: dict[str, threading.Thread] = {}
        self.states: dict[str, ComponentState] = {}
        self._lock = threading.RLock()
        self._install_components()

    def _install_components(self) -> None:
        definitions: dict[str, Callable[[], dict[str, Any]]] = {
            "warehouse-export": self.warehouse.export_once,
            "reference-version-watch": self.reference_watcher.check_once,
        }
        components = self.control.get("components") or {}
        for name, runner in definitions.items():
            cfg = components.get(name) or {}
            enabled = bool(cfg.get("enabled", True)) and bool(self.control.get("enabled", True))
            interval = max(30.0, float(cfg.get("interval_seconds") or 300.0))
            self.states[name] = ComponentState(name=name, enabled=enabled, interval_seconds=interval)
            if enabled:
                thread = threading.Thread(
                    target=self._component_loop,
                    args=(name, runner),
                    name=f"research-{name}",
                    daemon=True,
                )
                self.threads[name] = thread

    def _write_status(self) -> None:
        with self._lock:
            payload = {
                "version": 1,
                "pid": os.getpid(),
                "running": not self.stop_event.is_set(),
                "paper_only": True,
                "started_at": self.started_at,
                "updated_at": time.time(),
                "components": {name: state.to_dict() for name, state in self.states.items()},
                "safety": {
                    "can_place_orders": False,
                    "can_modify_strategy_profiles": False,
                    "auto_promote_external_code": False,
                },
            }
        _atomic_json(STATUS_PATH, payload)

    def _component_loop(self, name: str, runner: Callable[[], dict[str, Any]]) -> None:
        state = self.states[name]
        first = True
        while not self.stop_event.is_set():
            if not first and self.stop_event.wait(state.interval_seconds):
                break
            first = False
            state.status = "running"
            state.last_started_at = time.time()
            self._write_status()
            try:
                result = runner()
                state.last_result = result if isinstance(result, dict) else {"result": str(result)}
                state.last_success_at = time.time()
                state.last_error = ""
                state.status = "healthy"
                _log(f"{name}: healthy")
            except Exception as exc:
                state.last_error_at = time.time()
                state.last_error = f"{type(exc).__name__}: {exc}"
                state.status = "degraded"
                _log(f"{name}: degraded: {state.last_error}")
            finally:
                state.runs += 1
                state.last_finished_at = time.time()
                self._write_status()

    def run(self) -> None:
        _log("research supervisor starting")
        self._write_status()
        for thread in self.threads.values():
            thread.start()
        while not self.stop_event.wait(5.0):
            self._write_status()
        for thread in self.threads.values():
            thread.join(timeout=5.0)
        self._write_status()
        _log("research supervisor stopped")

    def stop(self) -> None:
        self.stop_event.set()


def main() -> None:
    supervisor = ResearchSupervisor()

    def _signal_handler(_signum, _frame) -> None:
        supervisor.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _signal_handler)
        except (ValueError, OSError):
            pass
    supervisor.run()


if __name__ == "__main__":
    main()
