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

# Static dashboard assets are served directly from disk. Updating them does not need
# to kill/restart Uvicorn; the browser reload watcher handles those changes. Only
# Python runtime code needs the supervised exit-code-75 restart path.
CONTROL_PATHS = ("control/assets.json", "control/runtime.json")


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

    def _git_available(self) -> tuple[bool, str]:
        if shutil.which("git") is None:
            return False, "git_not_installed"
        if not (self.repo_dir / ".git").exists():
            return False, "not_a_git_clone"
        completed = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=self.repo_dir,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if completed.returncode != 0 or completed.stdout.strip().lower() != "true":
            return False, "not_a_git_clone"
        return True, "ok"

    def _disabled_payload(self, reason: str) -> dict:
        payload = {"status": "disabled", "reason": reason, "ts": time.time()}
        self.state.set_sync(payload)
        return payload

    def _git(self, *args: str, check: bool = True) -> str:
        completed = subprocess.run(["git", *args], cwd=self.repo_dir, text=True, capture_output=True, timeout=60, check=False)
        if check and completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        return completed.stdout.strip()

    def _is_ancestor(self, older: str, newer: str) -> bool:
        completed = subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer],
            cwd=self.repo_dir,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if completed.returncode == 0:
            return True
        if completed.returncode == 1:
            return False
        raise RuntimeError(completed.stderr.strip() or "git merge-base failed")

    def _merge_base(self, left: str, right: str) -> str:
        return self._git("merge-base", left, right)

    @staticmethod
    def _control_only(paths: list[str]) -> bool:
        return bool(paths) and all(path in CONTROL_PATHS for path in paths)

    @staticmethod
    def _restart_required(paths: list[str]) -> bool:
        return any(path.startswith("b3_trader/") and path.endswith(".py") for path in paths)

    def _changed_from_base(self, base: str, ref: str) -> list[str]:
        return [line for line in self._git("diff", "--name-only", f"{base}..{ref}").splitlines() if line]

    def _preserve_control(self) -> dict[str, bytes]:
        preserved: dict[str, bytes] = {}
        for relative in CONTROL_PATHS:
            path = self.repo_dir / relative
            if path.exists():
                preserved[relative] = path.read_bytes()
        return preserved

    def _restore_control(self, preserved: dict[str, bytes]) -> None:
        for relative, content in preserved.items():
            path = self.repo_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    def _restart_if_needed(self, code_changed: bool) -> None:
        if not code_changed:
            return
        self.state.restart_required = True
        if self.on_restart_required:
            self.on_restart_required()

    def publish_control(self, message: str = "Update local trader control state") -> dict:
        if not self.push_control_changes:
            return {"status": "push_disabled"}
        available, reason = self._git_available()
        if not available:
            return self._disabled_payload(reason)

        with self._lock:
            preserved = self._preserve_control()
            self._git("fetch", "origin", self.branch)
            local = self._git("rev-parse", "HEAD")
            remote = self._git("rev-parse", f"origin/{self.branch}")
            remote_changed: list[str] = []

            if local != remote:
                if self._is_ancestor(local, remote):
                    remote_changed = [line for line in self._git("diff", "--name-only", f"{local}..{remote}").splitlines() if line]
                    self._git("reset", "--hard", f"origin/{self.branch}")
                    self._restore_control(preserved)
                elif self._is_ancestor(remote, local):
                    base = remote
                    local_only = self._changed_from_base(base, local)
                    if not self._control_only(local_only):
                        payload = {"status": "blocked_local_commits", "ts": time.time(), "changed": local_only}
                        self.state.set_sync(payload)
                        return payload
                else:
                    base = self._merge_base(local, remote)
                    local_only = self._changed_from_base(base, local)
                    remote_changed = self._changed_from_base(base, remote)
                    if not self._control_only(local_only):
                        payload = {
                            "status": "blocked_diverged_local_commits",
                            "ts": time.time(),
                            "local_changed": local_only,
                            "remote_changed": remote_changed,
                        }
                        self.state.set_sync(payload)
                        return payload
                    self._git("reset", "--hard", f"origin/{self.branch}")
                    self._restore_control(preserved)

            self._git("add", *CONTROL_PATHS)
            staged = self._git("diff", "--cached", "--name-only")
            if staged:
                self._git("commit", "-m", message)
            self._git("push", "origin", f"HEAD:{self.branch}")
            commit = self._git("rev-parse", "HEAD")
            code_changed = self._restart_required(remote_changed)
            payload = {
                "status": "published" if staged else "up_to_date",
                "commit": commit,
                "files": staged.splitlines() if staged else [],
                "changed": remote_changed,
                "remote_changed": remote_changed,
                "restart_required": code_changed,
                "ts": time.time(),
            }
            self.state.set_sync(payload)
            self._restart_if_needed(code_changed)
            return payload

    def check_once(self) -> dict:
        if not self.enabled:
            return self._disabled_payload("config_disabled")
        available, reason = self._git_available()
        if not available:
            return self._disabled_payload(reason)

        with self._lock:
            dirty = self._git("status", "--porcelain")
            if dirty:
                dirty_paths = [line[3:] for line in dirty.splitlines() if len(line) >= 4]
                if self._control_only(dirty_paths) and self.push_control_changes:
                    return self.publish_control()
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

            if self._is_ancestor(local, remote):
                changed = [line for line in self._git("diff", "--name-only", f"{local}..{remote}").splitlines() if line]
                code_changed = self._restart_required(changed)
                if code_changed and self.block_code_updates:
                    payload = {"status": "blocked_live_code_update", "ts": time.time(), "local": local, "remote": remote, "changed": changed}
                    self.state.set_sync(payload)
                    return payload
                self._git("merge", "--ff-only", f"origin/{self.branch}")
                payload = {"status": "updated", "ts": time.time(), "from": local, "to": remote, "changed": changed, "restart_required": code_changed}
                self.state.set_sync(payload)
                self._restart_if_needed(code_changed)
                return payload

            if self._is_ancestor(remote, local):
                local_only = self._changed_from_base(remote, local)
                if self._control_only(local_only) and self.push_control_changes:
                    self._git("push", "origin", f"HEAD:{self.branch}")
                    payload = {"status": "published", "ts": time.time(), "commit": local, "files": local_only, "changed": []}
                    self.state.set_sync(payload)
                    return payload
                payload = {"status": "blocked_local_commits", "ts": time.time(), "changed": local_only}
                self.state.set_sync(payload)
                return payload

            base = self._merge_base(local, remote)
            local_only = self._changed_from_base(base, local)
            remote_changed = self._changed_from_base(base, remote)
            if not self._control_only(local_only):
                payload = {
                    "status": "blocked_diverged_local_commits",
                    "ts": time.time(),
                    "local_changed": local_only,
                    "remote_changed": remote_changed,
                }
                self.state.set_sync(payload)
                return payload

            if self.block_code_updates and self._restart_required(remote_changed):
                payload = {"status": "blocked_live_code_update", "ts": time.time(), "local": local, "remote": remote, "changed": remote_changed}
                self.state.set_sync(payload)
                return payload

            preserved = self._preserve_control()
            self._git("reset", "--hard", f"origin/{self.branch}")
            self._restore_control(preserved)
            result = self.publish_control("Reconcile local trader control state")
            result["status"] = "reconciled"
            result["changed"] = remote_changed
            result["remote_changed"] = remote_changed
            result["restart_required"] = self._restart_required(remote_changed)
            self.state.set_sync(result)
            self._restart_if_needed(bool(result["restart_required"]))
            return result

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.check_once()
            except Exception as exc:
                self.state.set_error(exc, scope="git_sync")
                self.state.set_sync({"status": "error", "ts": time.time(), "message": str(exc)})

    def start(self) -> None:
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return
        available, reason = self._git_available()
        if not available:
            self._disabled_payload(reason)
            return
        try:
            self.check_once()
        except Exception as exc:
            self.state.set_error(exc, scope="git_sync")
            self.state.set_sync({"status": "error", "ts": time.time(), "message": str(exc)})
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
            target.close()
            source.close()
        backups = sorted(self.local_dir.glob("crypto-trader-*.sqlite3"), reverse=True)
        for old in backups[48:]:
            old.unlink(missing_ok=True)
        drive_status = "disabled"
        if self.rclone_remote:
            if shutil.which("rclone") is None:
                drive_status = "rclone_not_installed"
            else:
                self._rclone("copyto", str(destination), f"{self.rclone_remote}/{destination.name}")
                base = self.rclone_remote.rsplit("/", 1)[0] if "/" in self.rclone_remote else self.rclone_remote
                control_dir = self.repo_dir / "control"
                dashboard_dir = self.repo_dir / "dashboard"
                if control_dir.exists():
                    self._rclone("sync", str(control_dir), f"{base}/control")
                if dashboard_dir.exists():
                    self._rclone("sync", str(dashboard_dir), f"{base}/dashboard")
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
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="backup-manager", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
