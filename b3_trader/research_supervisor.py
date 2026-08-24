from __future__ import annotations

import os
import signal
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from .cloudflare_market_detail_publisher import CloudflareMarketDetailPublisher
from .cloudflare_pages_deployer import CloudflarePagesDeployer
from .cloudflare_snapshot_publisher import CloudflareSnapshotPublisher
from .reference_components import ReferenceComponentWatcher
from .research_control import COMPONENT_DEFINITIONS, STATUS_PATH, atomic_json, load_control
from .research_warehouse import ResearchWarehouse

LOG_PATH = Path("b3_trader/data/research-platform/supervisor.log")


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
    """Non-trading sidecar for storage, web snapshots, Pages deployment and version observation."""

    def __init__(self) -> None:
        load_dotenv()
        self.stop_event = threading.Event()
        self.started_at = time.time()
        self.control = load_control()
        self.warehouse = ResearchWarehouse()
        self.reference_watcher = ReferenceComponentWatcher()
        self.cloudflare_publisher = CloudflareSnapshotPublisher()
        self.cloudflare_market_detail_publisher = CloudflareMarketDetailPublisher()
        self.cloudflare_deployer = CloudflarePagesDeployer()
        self.states: dict[str, ComponentState] = {}
        self.runners: dict[str, Callable[[], dict[str, Any]]] = {
            "warehouse-export": self.warehouse.export_once,
            "reference-version-watch": self.reference_watcher.check_once,
            "cloudflare-snapshot-publish": self.cloudflare_publisher.publish_once,
            "cloudflare-market-detail-publish": self.cloudflare_market_detail_publisher.publish_once,
            "cloudflare-pages-deploy": self.cloudflare_deployer.deploy_once,
        }
        self.threads: dict[str, threading.Thread] = {}
        self.wake_events: dict[str, threading.Event] = {}
        self.force_run: dict[str, bool] = {}
        self.last_run_nonce: dict[str, int] = {}
        self._lock = threading.RLock()
        self._install_components()

    def _install_components(self) -> None:
        components = self.control.get("components") or {}
        global_enabled = bool(self.control.get("enabled", True))
        for name, definition in COMPONENT_DEFINITIONS.items():
            cfg = components.get(name) or {}
            default_enabled = bool(definition.get("default_enabled", True))
            enabled = bool(cfg.get("enabled", default_enabled)) and global_enabled
            minimum = float(definition["min_interval_seconds"])
            interval = max(minimum, float(cfg.get("interval_seconds") or definition["default_interval_seconds"]))
            self.states[name] = ComponentState(
                name=name,
                enabled=enabled,
                interval_seconds=interval,
                status="starting" if enabled else "stopped",
            )
            self.wake_events[name] = threading.Event()
            self.force_run[name] = False
            self.last_run_nonce[name] = int(cfg.get("run_nonce") or 0)
            self.threads[name] = threading.Thread(
                target=self._component_loop,
                args=(name, self.runners[name]),
                name=f"research-{name}",
                daemon=True,
            )

    def _write_status(self) -> None:
        with self._lock:
            payload = {
                "version": 2,
                "pid": os.getpid(),
                "running": not self.stop_event.is_set(),
                "paper_only": True,
                "started_at": self.started_at,
                "updated_at": time.time(),
                "control_revision": int(self.control.get("revision") or 1),
                "components": {name: state.to_dict() for name, state in self.states.items()},
                "safety": {
                    "can_place_orders": False,
                    "can_modify_strategy_profiles": False,
                    "auto_promote_external_code": False,
                    "cloudflare_viewer_read_only": True,
                },
            }
        atomic_json(STATUS_PATH, payload)

    def _apply_control(self) -> None:
        next_control = load_control()
        current_revision = int(self.control.get("revision") or 0)
        next_revision = int(next_control.get("revision") or 0)
        if next_revision == current_revision:
            return
        global_enabled = bool(next_control.get("enabled", True))
        components = next_control.get("components") or {}
        with self._lock:
            self.control = next_control
            for name, state in self.states.items():
                definition = COMPONENT_DEFINITIONS[name]
                cfg = components.get(name) or {}
                default_enabled = bool(definition.get("default_enabled", True))
                minimum = float(definition["min_interval_seconds"])
                state.enabled = bool(cfg.get("enabled", default_enabled)) and global_enabled
                state.interval_seconds = max(
                    minimum,
                    float(cfg.get("interval_seconds") or definition["default_interval_seconds"]),
                )
                nonce = int(cfg.get("run_nonce") or 0)
                if nonce != self.last_run_nonce.get(name, 0):
                    self.last_run_nonce[name] = nonce
                    self.force_run[name] = True
                if not state.enabled and state.status != "running":
                    state.status = "stopped"
                self.wake_events[name].set()
        _log(f"control revision {next_revision} applied")

    def _component_loop(self, name: str, runner: Callable[[], dict[str, Any]]) -> None:
        state = self.states[name]
        wake = self.wake_events[name]
        next_due = 0.0
        while not self.stop_event.is_set():
            if not state.enabled:
                if state.status != "running":
                    state.status = "stopped"
                wake.wait(2.0)
                wake.clear()
                continue

            now = time.time()
            forced = bool(self.force_run.get(name))
            if not forced and next_due > now:
                wake.wait(min(2.0, max(0.1, next_due - now)))
                wake.clear()
                continue

            self.force_run[name] = False
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
                next_due = state.last_finished_at + state.interval_seconds
                if not state.enabled:
                    state.status = "stopped"
                self._write_status()

    def run(self) -> None:
        _log("research supervisor starting")
        self._write_status()
        for thread in self.threads.values():
            thread.start()
        while not self.stop_event.wait(2.0):
            self._apply_control()
            self._write_status()
        for event in self.wake_events.values():
            event.set()
        for thread in self.threads.values():
            thread.join(timeout=5.0)
        self._write_status()
        _log("research supervisor stopped")

    def stop(self) -> None:
        self.stop_event.set()
        for event in self.wake_events.values():
            event.set()


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
