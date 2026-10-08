"""Research-stage boundaries: release failed writes before another DB owner runs."""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

from .research_control import atomic_json


class ResearchStage:
    def __init__(self, path: Path, connections: dict[str, sqlite3.Connection]) -> None:
        self.path = path
        self.connections = connections
        self.last_failure: dict[str, Any] | None = None

    def _open_transactions(self) -> list[str]:
        return [name for name, conn in self.connections.items() if conn.in_transaction]

    def _rollback(self) -> list[str]:
        opened = self._open_transactions()
        for name in opened:
            self.connections[name].rollback()
        return opened

    def _publish(self, value: dict[str, Any]) -> None:
        # One small, overwritten status file; no new database rows or log archive.
        try:
            atomic_json(self.path, {"version": 1, "pid": os.getpid(),
                                   "updated_at": time.time(), "last_failure": self.last_failure,
                                   **value})
        except OSError:
            # Failure to write diagnostics must not stop market collection.
            pass

    def run(self, stage: str, operation: Callable, *args, **kwargs):
        started = time.time()
        value = {"stage": stage, "status": "running", "started_at": started}
        self._publish({**value, "open_transactions": self._open_transactions()})
        try:
            if self._open_transactions():
                raise RuntimeError("uncommitted_research_stage_before_call")
            result = operation(*args, **kwargs)
            if self._open_transactions():
                raise RuntimeError("uncommitted_research_stage_after_call")
        except BaseException as exc:
            opened = self._open_transactions()
            try:
                self._rollback()
            finally:
                # Preserve evidence even if rollback itself fails; no later stage
                # may silently commit a previous owner's abandoned transaction.
                self.last_failure = {"stage": stage, "failed_at": time.time(),
                                     "error_type": type(exc).__name__,
                                     "sqlite_errorcode": getattr(exc, "sqlite_errorcode", None),
                                     "sqlite_errorname": getattr(exc, "sqlite_errorname", None),
                                     "transactions_before_rollback": opened,
                                     "open_transactions": self._open_transactions()}
                self._publish({**value, "status": "failed", "finished_at": time.time(),
                               "open_transactions": self._open_transactions()})
            raise
        finished = time.time()
        degraded = isinstance(result, dict) and result.get("ok") is False
        if degraded:
            self.last_failure = {"stage": stage, "failed_at": finished,
                                 "error_type": "stage_result", "result_status": result.get("status"),
                                 "open_transactions": []}
        self._publish({**value, "status": "degraded" if degraded else "completed",
                       "finished_at": finished, "elapsed_seconds": round(finished - started, 3),
                       "open_transactions": []})
        return result
