"""Own the normal launcher children for exactly one local-server session.

No database, credential, strategy or exchange module is imported here. A live
process is only a process observation, never proof of successful collection.
"""
from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from .research_work_lock import ResearchWorkLock
from .runtime_process_contract import APP_MODULE, HOST_LOCK, HOST_LOGS, HOST_STATUS, SIDECARS


class LocalProcessHost:
    def __init__(self, root: Path, *, commands=None, retry_seconds=5.0, tick_seconds=1.0):
        self.root = root.resolve()
        self.commands = commands if commands is not None else {
            **{role: [sys.executable, "-u", "-m", module, *args]
               for role, module, args, _ in SIDECARS},
            "app": [sys.executable, "-u", "-m", APP_MODULE],
        }
        self.retry_roles = {role for role, _, _, retry in SIDECARS if retry} | {"app"}
        self.retry_seconds = retry_seconds
        self.tick_seconds = tick_seconds
        self.stop_event = threading.Event()
        self.children = {}
        self.states = {role: {"pid": None, "state": "not_started", "starts": 0,
                             "last_exit_code": None, "last_exit_at": None,
                             "restart_at": None} for role in self.commands}
        self.retry_at = {}
        self.loggers = {}
        self.readers = {}
        self.lock = ResearchWorkLock(self.root / HOST_LOCK)
        self.started_at = time.time()
        self.stop_reason = None
        self.status_error = None

    def _logger(self, role):
        if role not in self.loggers:
            folder = self.root / HOST_LOGS
            folder.mkdir(parents=True, exist_ok=True)
            logger = logging.Logger(f"local-process-{role}-{os.getpid()}")
            handler = RotatingFileHandler(folder / f"{role}.log", maxBytes=1_048_576,
                                          backupCount=2, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            logger.addHandler(handler)
            self.loggers[role] = logger
        return self.loggers[role]

    def _output(self, role, pipe):
        try:
            while True:
                # Bound one unterminated output record as well as total log size.
                line = pipe.readline(8192)
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                self._logger(role).info("%s", text)
                if role == "app":
                    try:
                        print(text, flush=True)
                    except (OSError, UnicodeError):
                        pass
        finally:
            pipe.close()

    def _schedule_retry(self, role):
        if role in self.retry_roles and not self.stop_event.is_set():
            self.retry_at[role] = time.monotonic() + self.retry_seconds
            self.states[role]["restart_at"] = time.time() + self.retry_seconds

    def _start(self, role):
        if self.stop_event.is_set():
            return
        state = self.states[role]
        state["restart_at"] = None
        self.retry_at.pop(role, None)
        try:
            logger = self._logger(role)
            kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            process = subprocess.Popen(self.commands[role], cwd=self.root,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
            self.children[role] = process
            state.update(pid=process.pid, state="process_started", starts=state["starts"] + 1,
                         last_started_at=time.time(), spawn_error=None)
            logger.info("HOST child_started pid=%s attempt=%s", process.pid, state["starts"])
            thread = threading.Thread(target=self._output, args=(role, process.stdout), daemon=True)
            self.readers[role] = thread
            thread.start()
        except OSError as exc:
            state.update(pid=None, state="start_failed", spawn_error=type(exc).__name__)
            state["last_failure"] = {"at": time.time(), "kind": "start_failed", "error_type": type(exc).__name__}
            self._schedule_retry(role)

    def _record_exit(self, role, process, code, reason):
        self.states[role].update(pid=None, state="exited", last_exit_code=code,
                                 last_exit_at=time.time(), last_exit_reason=reason)
        if reason == "unexpected_exit":
            self.states[role]["last_failure"] = {"at": time.time(), "kind": reason, "exit_code": code}
        logger = self.loggers.get(role)
        if logger:
            logger.info("HOST child_exited pid=%s code=%s reason=%s", process.pid, code, reason)
        self.children.pop(role, None)
        reader = self.readers.pop(role, None)
        if reader:
            reader.join(timeout=1)

    def _write_status(self, running):
        payload = {"version": 1, "pid": os.getpid(), "repo": str(self.root),
                   "started_at": self.started_at, "updated_at": time.time(),
                   "running": running, "stop_reason": self.stop_reason,
                   "collection_verified": False, "children": self.states}
        path = self.root / HOST_STATUS
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".json.tmp")
            temp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            temp.replace(path)
            self.status_error = None
        except OSError as exc:
            # Diagnostic storage trouble must not kill otherwise running collectors.
            self.status_error = type(exc).__name__

    def _stop_children(self):
        # Only terminate handles created by this host; never discover/kill by name.
        for process in self.children.values():
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
        for role, process in list(self.children.items()):
            try:
                try:
                    code = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    code = process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                self.states[role]["state"] = "stop_failed"
                continue
            self._record_exit(role, process, code, self.stop_reason or "host_stop")
        return not self.children

    def run(self):
        if not self.lock.acquire():
            print("Another local process host owns this checkout; no child was started.", flush=True)
            return 2
        result = 0
        try:
            for role in self.commands:
                self._start(role)
            while not self.stop_event.is_set():
                # Observe app shutdown before retrying any sidecar. Exit 75 goes
                # back to PowerShell so updated host source is loaded as well.
                app = self.children.get("app")
                app_code = app.poll() if app else None
                if app_code in (0, 75):
                    self.stop_reason = "app_clean_exit" if app_code == 0 else "code_update"
                    self._record_exit("app", app, app_code, self.stop_reason)
                    result = app_code
                    break
                for role, process in list(self.children.items()):
                    code = process.poll()
                    if code is not None:
                        self._record_exit(role, process, code, "unexpected_exit")
                        self._schedule_retry(role)
                    else:
                        self.states[role]["state"] = "process_running"
                for role, due in list(self.retry_at.items()):
                    if time.monotonic() >= due:
                        self._start(role)
                self._write_status(True)
                self.stop_event.wait(self.tick_seconds)
        except KeyboardInterrupt:
            self.stop_reason = "user_interrupt"
        except Exception as exc:
            self.stop_reason = "host_error"
            result = 1
            print(f"Process host failed: {type(exc).__name__}", flush=True)
        finally:
            self.stop_event.set()
            self.stop_reason = self.stop_reason or "stop_requested"
            self.retry_at.clear()
            for state in self.states.values():
                state["restart_at"] = None
            try:
                if not self._stop_children():
                    # PowerShell must not retry the host and duplicate children
                    # when ownership could not be completely released.
                    self.stop_reason = "child_cleanup_failed"
                    result = 2
                self._write_status(False)
            finally:
                for logger in self.loggers.values():
                    for handler in logger.handlers:
                        handler.close()
                self.lock.release()
        return result


def main():
    host = LocalProcessHost(Path(__file__).resolve().parents[1])

    def stop(_signum, _frame):
        host.stop_reason = "signal_stop"
        host.stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    return host.run()


if __name__ == "__main__":
    sys.exit(main())
