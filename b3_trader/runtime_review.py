"""Bounded, read-only PC process and data evidence. No runner is imported."""
from __future__ import annotations

import base64
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time

from .runtime_process_contract import APP_MODULE, HOST_LOGS, HOST_STATUS, SIDECARS

STATUS_FILES = {
    "host": HOST_STATUS,
    "research": "b3_trader/data/research-platform/status.json",
    "paper": "b3_trader/data/paper-runtime-supervisor.json",
    "market_flow": "b3_trader/data/research-platform/market-flow-stream.json",
    "forward": "b3_trader/data/research-platform/dex-forward-pipeline-scheduler-build69.json",
}
ACTIVITY = {
    "paper": ("research_accounts_mx", "updated_ts"),
    "market_memory": ("research_market_memory_mx", "ts"),
    "strategy_lab": ("strategy_lab_metrics", "updated_ts"),
    "trade_flow": ("research_market_trade_flow_mx", "received_at"),
    "ohlcv": ("research_market_ohlcv_mx", "received_at"),
    "events": ("research_intelligence_events", "observed_at"),
    "event_responses": ("research_intelligence_event_responses", "captured_at"),
}
ERROR_PATTERNS = {
    "missing_module": r"ModuleNotFoundError|No module named",
    "import_error": r"ImportError|cannot import name",
    "database_locked": r"database (?:table is |is )?locked",
    "database_unavailable": r"unable to open database|readonly database|disk I/O error",
    "disk_full": r"No space left|database or disk is full|not enough space on the disk",
    "permission_denied": r"PermissionError|Permission denied|Access is denied",
    "timeout": r"TimeoutError|ReadTimeout|ConnectionTimeout|timed out",
    "rate_limited": r"Too Many Requests|status(?:_code)?[=: ]+429",
    "process_crash": r"HOST child_exited.*reason=unexpected_exit",
}


def _processes(root):
    if os.name != "nt":
        return {"status": "unsupported_host", "items": []}
    roles = {module: role for role, module, _, _ in SIDECARS}
    roles.update({APP_MODULE: "app", "b3_trader.local_process_host": "host"})
    # Command lines are inspected inside PowerShell, never returned or saved.
    script = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$roles = ConvertFrom-Json $env:CRYPTO_REVIEW_PROCESS_ROLES
$root = $env:CRYPTO_REVIEW_RUNTIME_ROOT.TrimEnd('\') + '\'
$items = @()
foreach ($p in @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'")) {
  foreach ($entry in $roles.PSObject.Properties) {
    if ($p.CommandLine -match ('(?<![\w.])' + [regex]::Escape($entry.Name) + '(?![\w.])')) {
      $scope = 'unresolved_checkout'
      if ($p.ExecutablePath -and $p.ExecutablePath.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { $scope = 'checkout' }
      $items += @{role=$entry.Value; pid=$p.ProcessId; parent_pid=$p.ParentProcessId; scope=$scope;
                  created_at=([DateTimeOffset]$p.CreationDate).ToUnixTimeSeconds()}
    }
  }
}
@{status='read'; items=$items} | ConvertTo-Json -Depth 5 -Compress
'''
    env = dict(os.environ, CRYPTO_REVIEW_RUNTIME_ROOT=str(root),
               CRYPTO_REVIEW_PROCESS_ROLES=json.dumps(roles))
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
             base64.b64encode(script.encode("utf-16-le")).decode("ascii")],
            capture_output=True, timeout=15, env=env, encoding="utf-8", errors="replace")
        if result.returncode:
            return {"status": "read_failed", "exit_code": result.returncode, "items": []}
        value = json.loads(result.stdout.lstrip("\ufeff"))
        if not isinstance(value, dict) or not isinstance(value.get("items"), list):
            raise ValueError("Invalid process observation")
        return value
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"status": "read_failed", "items": []}


def _json_file(path):
    try:
        with path.open("rb") as stream:
            raw = stream.read(2_000_001)
        if len(raw) > 2_000_000:
            return {"status": "too_large"}, {}
        value = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError()
        return {"status": "read", "mtime": path.stat().st_mtime}, value
    except FileNotFoundError:
        return {"status": "missing"}, {}
    except (OSError, ValueError):
        return {"status": "unreadable"}, {}


def _error_kinds(value):
    return [kind for kind, pattern in ERROR_PATTERNS.items() if re.search(pattern, str(value), re.I)]


def _log_kinds(path):
    try:
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 65_536))
            tail = stream.read(65_536).decode("utf-8", errors="replace")
        return {"status": "read", "mtime": path.stat().st_mtime,
                "recent_error_kinds": _error_kinds(tail)}
    except OSError:
        return {"status": "unavailable"}


def _status(root, role, processes):
    meta, value = _json_file(root / STATUS_FILES[role])
    saved = {k: value[k] for k in ("pid", "started_at", "updated_at", "running", "stop_reason") if k in value}
    matches = [p for p in processes.get("items", []) if p.get("role") == role and p.get("scope") == "checkout"]
    uncertain = any(p.get("role") == role and p.get("scope") != "checkout" for p in processes.get("items", []))
    observation = "present" if matches else "unknown" if uncertain or processes.get("status") != "read" else "absent"
    owner_match = any(p.get("pid") == saved.get("pid") and
                      isinstance(saved.get("started_at"), (int, float)) and
                      abs(p.get("created_at", 0) - saved["started_at"]) <= 30 for p in matches)
    summary = {"file": STATUS_FILES[role], **meta, "saved": saved,
               "process_observation": observation, "saved_owner_matches": owner_match,
               "error_kinds": _error_kinds(value.get("last_error", ""))}
    if role == "host":
        children = value.get("children")
        children = children if isinstance(children, dict) else {}
        summary["children"] = {name: {k: row[k] for k in
            ("pid", "state", "starts", "last_started_at", "last_exit_code", "last_exit_at",
             "last_exit_reason", "last_failure", "restart_at") if k in row}
            for name, row in children.items() if isinstance(row, dict)}
    if role == "research":
        components = value.get("components", [])
        rows = components.values() if isinstance(components, dict) else components if isinstance(components, list) else []
        summary["components"] = [{**{k: row[k] for k in ("name", "enabled", "status", "last_started_at", "last_success_at", "last_finished_at") if k in row},
                                  "error_kinds": _error_kinds(row.get("last_error", ""))}
                                 for row in rows if isinstance(row, dict)]
    return summary


def read_activity(db):
    result = {}
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        conn.execute("PRAGMA query_only=ON")
        for name, (table, clock) in ACTIVITY.items():
            # All-market latest timestamps can require scans on older databases;
            # cap each query and preserve unknown instead of blocking the viewer.
            deadline = time.monotonic() + 1
            conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
            try:
                row = conn.execute(f'SELECT MAX({clock}) FROM "{table}"').fetchone()
                latest = row[0] if row else None
                result[name] = {"status": "read", "latest": latest if isinstance(latest, (int, float)) and math.isfinite(latest) else None}
            except sqlite3.OperationalError as exc:
                kind = "query_timeout" if str(exc) == "interrupted" else "unavailable"
                result[name] = {"status": kind, "latest": None}
    finally:
        conn.close()
    return result


def read_runtime(db: Path):
    result = {"observed_at": time.time(), "activity": read_activity(db)}
    if db.name != "auto_demo.sqlite3" or db.parent.name != "data" or db.parent.parent.name != "b3_trader":
        return {**result, "status": "runtime_root_unresolved", "processes": {"status": "not_read", "items": []}}
    root = db.resolve().parents[2]
    processes = _processes(root)
    result.update(status="observed", processes=processes,
                  saved_statuses={role: _status(root, role, processes) for role in STATUS_FILES})
    result["research_log"] = _log_kinds(root / "b3_trader/data/research-platform/supervisor.log")
    result["process_logs"] = {role: _log_kinds(root / HOST_LOGS / f"{role}.log")
                              for role in [*(row[0] for row in SIDECARS), "app"]}
    return result


def compare_activity(before, after):
    compared = {}
    for name in ACTIVITY:
        first = before.get("activity", {}).get(name, {})
        last = after.get("activity", {}).get(name, {})
        a, b = first.get("latest"), last.get("latest")
        outcome = "unknown"
        if first.get("status") == last.get("status") == "read" and a is not None and b is not None:
            outcome = "advanced" if b > a else "unchanged" if b == a else "latest_regressed"
        compared[name] = {"observation": outcome, "before": a, "after": b}
    return compared
