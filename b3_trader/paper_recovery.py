"""User-started, backup-first recovery of the existing local PAPER collectors.

This module ships separately from the read-only review. It never installs
dependencies, kills discovered processes, rewrites controls, or publishes data.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

from .local_process_host import LocalProcessHost
from .research_work_lock import ResearchWorkLock
from .runtime_review import _processes, read_runtime, compare_activity
from .strategy_journal_review import read_detail, write_report

SOURCE_BRANCH = "agent/crypto-product-data-recovery-20260921"
DB_RELATIVE = Path("b3_trader/data/auto_demo.sqlite3")
BACKUP_TABLES = (
    "research_accounts_mx", "research_fills_mx", "research_feedback_mx",
    "strategy_lab_accounts", "strategy_lab_trades", "strategy_lab_metrics",
)


class RecoveryBlocked(RuntimeError):
    pass


def git(root, *args):
    # Never echo Git stderr: a configured remote can contain credentials.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"}
    env.setdefault("GIT_SSH_COMMAND", "ssh -oBatchMode=yes")
    try:
        result = subprocess.run(["git", *args], cwd=root, env=env,
                                capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecoveryBlocked("git_unavailable_or_timeout") from exc
    if result.returncode:
        raise RecoveryBlocked("git_" + args[0] + "_failed")
    return result.stdout.strip()


def verify_bundle(folder):
    manifest = json.loads((folder / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    commit = manifest.get("source_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or manifest.get("mode") != "collection_recovery":
        raise RecoveryBlocked("invalid_source_manifest")
    for name, expected in manifest["files"].items():
        path = (folder / name).resolve()
        if folder.resolve() not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RecoveryBlocked("bundle_file_mismatch")
    return commit


def require_stopped(root):
    observed = _processes(root)
    # The current helper and its Windows venv redirector are not collectors.
    own = {os.getpid(), os.getppid()}
    others = [p for p in observed.get("items", [])
              if not (p.get("role") == "recovery" and p.get("pid") in own)]
    if observed.get("status") != "read":
        raise RecoveryBlocked("process_observation_unavailable")
    if others:
        raise RecoveryBlocked("existing_or_unresolved_processes")
    return {"status": "read", "items": []}


def require_clean(root, expected=None):
    if Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root.resolve():
        raise RecoveryBlocked("wrong_checkout_root")
    if git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise RecoveryBlocked("checkout_has_local_changes")
    head = git(root, "rev-parse", "HEAD")
    if expected and head != expected:
        raise RecoveryBlocked("checkout_changed_during_preparation")
    return head


def fetch_source(root, commit):
    remote = git(root, "remote", "get-url", "origin")
    if not re.fullmatch(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)ydh1121/crypto-event-notifier(?:\.git)?/?", remote):
        raise RecoveryBlocked("unexpected_origin")
    git(root, "fetch", "--no-tags", "origin", SOURCE_BRANCH)
    git(root, "merge-base", "--is-ancestor", commit, "FETCH_HEAD")
    # Never replace newer/divergent local implementation with this package.
    git(root, "merge-base", "--is-ancestor", "HEAD", commit)


def backup_database(source, folder):
    if not source.is_file():
        raise RecoveryBlocked("existing_database_missing")
    folder.mkdir(parents=True, exist_ok=False)
    destination = folder / "auto_demo.sqlite3"
    conn = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        required = conn.execute("PRAGMA page_count").fetchone()[0] * conn.execute("PRAGMA page_size").fetchone()[0]
        if shutil.disk_usage(folder).free < required + 512 * 1024 * 1024:
            raise RecoveryBlocked("insufficient_backup_space")
        counts = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in BACKUP_TABLES}
        deadline = time.monotonic() + 1800
        progress_band = [-1]

        def progress(_status, remaining, total):
            if time.monotonic() > deadline:
                raise RecoveryBlocked("backup_timeout")
            band = int((total - remaining) * 10 / total) if total else 10
            if band > progress_band[0]:
                print(f"Database backup: {band * 10}%", flush=True)
                progress_band[0] = band

        with closing(sqlite3.connect(destination)) as target:
            conn.backup(target, pages=2048, progress=progress, sleep=.05)
        print("Checking backup integrity and account/trade counts...", flush=True)
        with closing(sqlite3.connect(destination.as_uri() + "?mode=ro", uri=True)) as verify:
            verify.execute("PRAGMA query_only=ON")
            integrity = verify.execute("PRAGMA quick_check").fetchall()
            copied = {t: verify.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in BACKUP_TABLES}
        if integrity != [("ok",)] or counts != copied:
            raise RecoveryBlocked("backup_readback_failed")
        receipt = {"path": str(destination), "bytes": destination.stat().st_size,
                   "quick_check": "ok", "ledger_counts": counts, "completed_at": time.time()}
        write_report(folder / "backup-receipt.json", receipt)
        return receipt
    finally:
        conn.close()


def verify_dependencies(root):
    # Imports only; no dotenv load, constructors, database connection or install.
    result = subprocess.run([sys.executable, "-B", "-c",
        "import dotenv, requests, websocket, jwt, duckdb, pypdf"], cwd=root,
        capture_output=True, timeout=30)
    if result.returncode:
        raise RecoveryBlocked("existing_python_dependencies_missing")


def observe(db, output, report, guard, stop, seconds):
    if stop.wait(seconds):
        return
    try:
        after = read_runtime(db)
        detail = read_detail(db, "bithumb", "KRW-B3")["data"]["strategy_lab"]
        account = next((e for e in detail["experiments"] if e["style"] == "aggressive"), None)
        with guard:
            report["runtime_review"].update(status="complete", after=after,
                changes=compare_activity(report["runtime_review"]["before"], after))
            report["advancing_series"] = [name for name, change in report["runtime_review"]["changes"].items()
                                           if change["observation"] == "advanced"]
            report["account_review"] = {"scope": "bithumb|KRW-B3|aggressive", "account": account}
            write_report(output, report)
        print("Database observation saved: CRYPTO_RECOVERY_RESULT.json", flush=True)
        print("Collection continues. Keep this window open; press Ctrl+C to stop.", flush=True)
    except Exception as exc:
        with guard:
            report["observation_error_type"] = type(exc).__name__
            write_report(output, report)
        print("Observation could not finish; collection is still supervised.", flush=True)


def observe_session(db, output, report, guard, stop, seconds):
    while not stop.is_set():
        observe(db, output, report, guard, stop, seconds)


def recover(root, folder, output, seconds=60):
    report = {"version": 1, "started_at": time.time(), "profile": "collection_recovery",
              "status": "preparing", "phase": "preflight", "paper_only": True,
              "production_publication": False, "holdings_consumer": False}
    guard = threading.RLock()
    try:
        commit = verify_bundle(folder)
        if not root.is_dir() or not (root / DB_RELATIVE).is_file():
            raise RecoveryBlocked("existing_checkout_or_database_missing")
        if root == folder or root in folder.parents:
            raise RecoveryBlocked("extract_recovery_package_outside_checkout")
        if Path(sys.executable).resolve() != (root / ".venv/Scripts/python.exe").resolve():
            raise RecoveryBlocked("use_existing_project_python")
        with ResearchWorkLock(root / "b3_trader/data/recovery-preparation.lock") as lock:
            if not lock.acquired:
                raise RecoveryBlocked("another_recovery_is_preparing")
            require_stopped(root)
            original = require_clean(root)
            original_branch = git(root, "symbolic-ref", "--short", "HEAD")
            report["source"] = {"original_head": original, "original_branch": original_branch,
                                "pinned_commit": commit}
            verify_dependencies(root)
            print("Checking the pinned source revision...", flush=True)
            report["phase"] = "source_fetch"
            fetch_source(root, commit)
            require_stopped(root)
            require_clean(root, original)
            report["phase"] = "database_backup"
            stamp = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
            backup_folder = root / "b3_trader/data/recovery-backups" / stamp
            report["backup"] = backup_database(root / DB_RELATIVE, backup_folder)
            write_report(output, report)
            require_stopped(root)
            require_clean(root, original)
            report["phase"] = "local_source_activation"
            branch = "recovery/paper-" + stamp
            git(root, "switch", "-c", branch, commit)
            report["source"]["active_branch"] = branch
            require_clean(root, commit)
            require_stopped(root)
            db = root / DB_RELATIVE
            report["runtime_review"] = {"status": "waiting_for_second_observation", "before": read_runtime(db)}
            report.update(status="collecting", phase="collection", collection_verified=False)
            write_report(output, report)
            host = LocalProcessHost(root, recovery=True)
            stop = threading.Event()
            worker = threading.Thread(target=observe_session, args=(db, output, report, guard, stop, seconds), daemon=True)
            worker.start()

            def request_stop(_signum, _frame):
                host.stop_reason = "user_stop"
                host.stop_event.set()

            previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
            print("Backup verified. Starting existing PAPER and market/event collectors.", flush=True)
            print("No live orders, holdings consumer, website publication or automatic Git sync.", flush=True)
            print("Keep this window open. Ctrl+C stops this collection session.", flush=True)
            try:
                code = host.run()
            finally:
                stop.set()
                worker.join(timeout=15)
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
            with guard:
                after_stop = _processes(root)
                remaining = [p for p in after_stop.get("items", []) if not (
                    p.get("role") == "recovery" and p.get("pid") in {os.getpid(), os.getppid()})]
                cleanup_verified = after_stop.get("status") == "read" and not remaining
                if not cleanup_verified:
                    code = 2
                report.update(status="stopped" if code == 0 else "host_failed", host_exit_code=code,
                              stop_reason=host.stop_reason, cleanup_verified=cleanup_verified, finished_at=time.time())
                report["after_stop_processes"] = after_stop
                write_report(output, report)
            return code
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status="blocked", finished_at=time.time(),
                      error=str(exc) if isinstance(exc, RecoveryBlocked) else type(exc).__name__)
        write_report(output, report)
        print(f"Recovery stopped at {report['phase']}: {report['error']}", flush=True)
        print("No discovered process was stopped. See CRYPTO_RECOVERY_RESULT.json.", flush=True)
        return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(r"C:\Users\Administrator\Desktop\crypto-event-notifier-live"))
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This launcher targets the existing Windows PC only.")
    folder = Path(__file__).resolve().parents[1]
    return recover(args.repo.resolve(), folder, folder / "CRYPTO_RECOVERY_RESULT.json")


if __name__ == "__main__":
    sys.exit(main())
