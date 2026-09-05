from __future__ import annotations

import json
import os
import signal
import threading
import time
from pathlib import Path
from typing import Callable, Protocol

from .auto_demo import AutoPaperDemo

STATUS_PATH = Path("b3_trader/data/paper-runtime-supervisor.json")
RESTART_DELAY_SECONDS = 5.0


class PaperDemoRunner(Protocol):
    def run(self, stop_event: threading.Event | None = None) -> None: ...


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)


class PaperRuntimeSupervisor:
    """Own the Bithumb PAPER runtime as one restart-safe process.

    The normal Windows launcher disables the legacy in-process local_app demo worker
    and starts this supervisor instead. Any constructor error, runtime exception, or
    unexpected clean return is retried without affecting the dashboard or research
    supervisor. This remains PAPER-only and cannot place real orders.
    """

    def __init__(
        self,
        demo_factory: Callable[[], PaperDemoRunner] = AutoPaperDemo,
        *,
        restart_delay_seconds: float = RESTART_DELAY_SECONDS,
        status_path: Path = STATUS_PATH,
    ) -> None:
        self.demo_factory = demo_factory
        self.restart_delay_seconds = max(0.1, float(restart_delay_seconds))
        self.status_path = status_path
        self.stop_event = threading.Event()
        self.started_at = time.time()
        self.attempts = 0
        self.restarts = 0
        self.last_started_at = 0.0
        self.last_finished_at = 0.0
        self.last_error = ""
        self.last_error_at = 0.0

    def _write_status(self, *, running: bool) -> None:
        _atomic_json(
            self.status_path,
            {
                "version": 1,
                "pid": os.getpid(),
                "running": bool(running) and not self.stop_event.is_set(),
                "paper_only": True,
                "can_place_real_orders": False,
                "started_at": self.started_at,
                "updated_at": time.time(),
                "attempts": self.attempts,
                "restarts": self.restarts,
                "last_started_at": self.last_started_at,
                "last_finished_at": self.last_finished_at,
                "last_error": self.last_error,
                "last_error_at": self.last_error_at,
            },
        )

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        self._write_status(running=True)
        try:
            while not self.stop_event.is_set():
                self.attempts += 1
                self.last_started_at = time.time()
                self._write_status(running=True)
                unexpected_return = False
                try:
                    demo = self.demo_factory()
                    demo.run(stop_event=self.stop_event)
                    unexpected_return = not self.stop_event.is_set()
                    if unexpected_return:
                        self.last_error = "AutoPaperDemo.run returned without a stop request"
                        self.last_error_at = time.time()
                except Exception as exc:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    self.last_error_at = time.time()
                finally:
                    self.last_finished_at = time.time()
                    self._write_status(running=True)

                if self.stop_event.is_set():
                    break

                self.restarts += 1
                if not unexpected_return and not self.last_error:
                    self.last_error = "PAPER runtime exited unexpectedly"
                    self.last_error_at = time.time()
                self._write_status(running=True)
                if self.stop_event.wait(self.restart_delay_seconds):
                    break
        finally:
            self._write_status(running=False)


def main() -> None:
    supervisor = PaperRuntimeSupervisor()

    def _stop(_signum, _frame) -> None:
        supervisor.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _stop)
        except (ValueError, OSError):
            pass

    supervisor.run()


if __name__ == "__main__":
    main()
