from __future__ import annotations

import shutil
import sqlite3
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .runtime_state import RuntimeState
from .telegram_notify import TelegramNotifier

CODE_SUFFIXES = (".py", ".toml", ".yml", ".yaml", ".txt")
CODE_PREFIXES = ("b3_trader/", "scripts/", ".github/", "Dockerfile", "cloudflare/")


class GitAutoSync:
    def __init__(self, *, repo_dir: str, branch: str, enabled: bool, interval_seconds: float, state: RuntimeState, notifier: TelegramNotifier | None = None, on_restart_required: Callable[[], None] | None = None, block_code_updates: bool = False, push_control_changes: bool = True) -> None:
        self.repo_dir = Path(repo_dir).resolve()
        self.branch = branch
        self.enabled = enabled
        self.interval_seconds = max(15.0, interval_seconds)
        self.state = state
        self.notifier = notifier
        self.on_restart_required = on_restart_required
        self.block_code_updates = block_code_updates
        self.push_control_changes = push_control_changes
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _git(self, *args: str, check: bool = True) -> str:
        completed = subprocess.run(["git", *args], cwd=self.repo_dir, text=True, capture_output=True, timeout=60, check=False)
        if check and completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        return completed.stdout.strip()

    def publish_control(self, message: str = "Update local trader control state") -> dict:
        if not self.push_control_changes:
            return {"status": "push_disabled"}
        with self._lock:
            self._git("add", "control/assets.json", "control/runtime.json")
            staged = self._git("diff", "--cached", "--name-only")
            if not staged:
                return {"status": "nothing_to_publish"}
            self._git("commit", "-m", message)
            self._git("push", "origin", f"HEAD:{self.branch}")
            commit = self._git("rev-parse", "HEAD")
            payload = {"status": "published", "commit": commit, "files": staged.splitlines()}
            self.state.set_sync({**payload, "ts": time.time()})
            return payload

    def check_once(self) -> dict:
        if not self.enabled:
            payload = {"status": "disabled", "ts": time.time()}
            self.state.set_sync(payload)
            return payload
        with self._lock:
            dirty = self._git("status", "--porcelain")
            if dirty:
                only_control = all(line[3:].startswith("control/") for line in dirty.splitlines() if len(line) >= 4)
                if only_control and self.push_control_changes:
                    self.publish_control()
                else:
                    payload = {"status": "blocked_dirty_worktree", "ts": time.time(), "detail": dirty.splitlines()[:10]}
                    self.state.set_sync(payload)
                    return payload
            self._git("fetch", "origin", self.branch)
            local = self._git("rev-parse", "HEAD")
            remote = self._git("rev-parse", f"origin/{self.branch}")
            if local == remote:
                payload = {"status": "up_to_date", "ts": time.time(), "commit": local}
                self.state.set_sync(payload)
                return payload
            changed = [line for line in self._git("diff", "--name-only", f"{local}..{remote}").splitlines() if line]
            code_changed = any(path.startswith(CODE_PREFIXES) or path.endswith(CODE_SUFFIXES) for path in changed)
            if code_changed and self.block_code_updates:
                payload = {"status": "blocked_live_code_update", "ts": time.time(), "local": local, "remote": remote, "changed": changed}
                self.state.set_sync(payload)
                return payload
            self._git("merge", "--ff-only", f"origin/{self.branch}")
            payload = {"status": "updated", "ts": time.time(), "from": local, "to": remote, "changed": changed, "restart_required": code_changed}
            self.state.set_sync(payload)
            if self.notifier:
                self.notifier.safe_send("GitHub 동기화 완료\n" + f"{local[:7]} → {remote[:7]}\n변경 {len(changed)}개" + ("\n프로그램 재시작 예정" if code_changed else ""), event_key=f"git-sync-{remote}")
            if code_changed:
                self.state.restart_required = True
                if self.on_restart_required:
                    self.on_restart_required()
            return payload

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.check_once()
            except Exception as exc:
                self.state.set_error(exc, scope="git_sync")
                self.state.set_sync({"status": "error", "ts": time.time(), "message": str(exc)})

    def start(self) -> None:
        if not self.enabled or (self._thread and self._thread.is_alive()): return
        self._thread = threading.Thread(target=self._loop, name="git-auto-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


class BackupManager:
    def __init__(self, *, sqlite_path: str, local_dir: str, interval_seconds: float, state: RuntimeState, rclone_remote: str = "", repo_dir: str = ".", notifier: TelegramNotifier | None = None) -> None:
        self.sqlite_path = Path(sqlite_path)
        self.local_dir = Path(local_dir)
        self.interval_seconds = max(300.0, interval_seconds)
        self.state = state
        self.rclone_remote = rclone_remote.strip().rstrip("/")
        self.repo_dir = Path(repo_dir).resolve()
        self.notifier = notifier
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _rclone(self, *args: str) -> None:
        completed = subprocess.run(["rclone", *args], text=True, capture_output=True, timeout=240, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())

    def backup_once(self) -> dict:
        self.local_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = self.local_dir / f"crypto-trader-{timestamp}.sqlite3"
        if not self.sqlite_path.exists():
            payload = {"status": "skipped", "ts": time.time(), "reason": "sqlite_not_created_yet"}
            self.state.set_backup(payload)
            return payload
        source = sqlite3.connect(str(self.sqlite_path))
        target = sqlite3.connect(str(destination))
        try:
            source.backup(target)
        finally:
            target.close(); source.close()
        backups = sorted(self.local_dir.glob("crypto-trader-*.sqlite3"), reverse=True)
        for old in backups[48:]: old.unlink(missing_ok=True)
        drive_status = "disabled"
        if self.rclone_remote:
            if shutil.which("rclone") is None:
                drive_status = "rclone_not_installed"
            else:
                self._rclone("copyto", str(destination), f"{self.rclone_remote}/{destination.name}")
                base = self.rclone_remote.rsplit("/", 1)[0] if "/" in self.rclone_remote else self.rclone_remote
                control_dir = self.repo_dir / "control"
                dashboard_dir = self.repo_dir / "dashboard"
                if control_dir.exists(): self._rclone("sync", str(control_dir), f"{base}/control")
                if dashboard_dir.exists(): self._rclone("sync", str(dashboard_dir), f"{base}/dashboard")
                drive_status = "uploaded_and_mirrored"
        payload = {"status": "ok", "ts": time.time(), "local": str(destination), "drive": drive_status}
        self.state.set_backup(payload)
        return payload

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.backup_once()
            except Exception as exc:
                self.state.set_error(exc, scope="backup")
                self.state.set_backup({"status": "error", "ts": time.time(), "message": str(exc)})

    def start(self) -> None:
        if self._thread and self._thread.is_alive(): return
        self._thread = threading.Thread(target=self._loop, name="backup-manager", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
