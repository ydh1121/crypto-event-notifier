from __future__ import annotations

import argparse
import json
import os
import signal
import threading
import time
from pathlib import Path

from .paper_strategy_v2_forward_shadow import PaperV2ForwardShadowRunner

STATUS_PATH = Path("b3_trader/data/paper-v2-forward-supervisor.json")
DEFAULT_INTERVAL_SECONDS = 60.0
RESTART_DELAY_SECONDS = 5.0


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)


class PaperV2ForwardSupervisor:
    def __init__(self, *, interval_seconds: float = DEFAULT_INTERVAL_SECONDS, status_path: Path = STATUS_PATH) -> None:
        self.interval_seconds = max(15.0, float(interval_seconds))
        self.status_path = status_path
        self.stop_event = threading.Event()
        self.started_at = time.time()
        self.runs = 0
        self.last_success_at = 0.0
        self.last_error_at = 0.0
        self.last_error = ""
        self.last_result: dict = {}

    def stop(self) -> None:
        self.stop_event.set()

    def _write(self, running: bool) -> None:
        _atomic_json(
            self.status_path,
            {
                "version": 1,
                "pid": os.getpid(),
                "running": bool(running) and not self.stop_event.is_set(),
                "paper_only": True,
                "shadow_only": True,
                "can_place_real_orders": False,
                "preset": "balanced_60_25_r2_agg5",
                "started_at": self.started_at,
                "updated_at": time.time(),
                "runs": self.runs,
                "last_success_at": self.last_success_at,
                "last_error_at": self.last_error_at,
                "last_error": self.last_error,
                "last_result": self.last_result,
            },
        )

    def run_once(self) -> dict:
        runner = PaperV2ForwardShadowRunner()
        try:
            result = runner.run_once()
        finally:
            runner.close()
        self.runs += 1
        self.last_result = result
        self.last_success_at = time.time()
        self.last_error = ""
        self._write(True)
        return result

    def run(self) -> None:
        self._write(True)
        try:
            while not self.stop_event.is_set():
                try:
                    self.run_once()
                except Exception as exc:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    self.last_error_at = time.time()
                    self._write(True)
                    if self.stop_event.wait(RESTART_DELAY_SECONDS):
                        break
                    continue
                if self.stop_event.wait(self.interval_seconds):
                    break
        finally:
            self._write(False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Balanced shared-portfolio V2 forward PAPER shadow supervisor")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    args = parser.parse_args()
    supervisor = PaperV2ForwardSupervisor(interval_seconds=args.interval)

    def _stop(_signum, _frame) -> None:
        supervisor.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _stop)
        except (ValueError, OSError):
            pass

    if args.once:
        print(json.dumps(supervisor.run_once(), ensure_ascii=False, indent=2))
        return 0
    supervisor.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
