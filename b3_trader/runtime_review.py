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
    "strategy_lab": ("strategy_lab_accounts", "updated_ts"),
    "strategy_lab_metrics": ("strategy_lab_metrics", "updated_ts"),
    "trade_flow": ("research_market_trade_flow_mx", "trade_ts"),
    "ohlcv": ("research_market_ohlcv_mx", "received_at"),
    "events": ("research_intelligence_events", "received_at"),
    "event_responses": ("research_intelligence_event_responses", "captured_at"),
    "event_prices": ("research_intelligence_event_prices", "archived_at"),
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


def _processes(root, *, include_review=False):
    if os.name != "nt":
        return {"status": "unsupported_host", "items": []}
    roles = {module: role for role, module, _, _ in SIDECARS}
    roles.update({APP_MODULE: "app", "b3_trader.local_process_host": "host"})
    roles.update({"b3_trader.paper_recovery": "recovery", "b3_trader.auto_demo": "legacy_paper",
                  "b3_trader.auto_demo_v2": "legacy_paper", "b3_trader.multi_exchange_demo": "legacy_paper"})
    if include_review:
        roles['b3_trader.strategy_journal_review'] = 'review'
    # Command lines are inspected inside PowerShell, never returned or saved.
    script = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$roles = ConvertFrom-Json $env:CRYPTO_REVIEW_PROCESS_ROLES
$root = $env:CRYPTO_REVIEW_RUNTIME_ROOT.TrimEnd('\') + '\'
$items = @()
$unreadable = $false
foreach ($p in @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'")) {
  if (-not $p.CommandLine) { $unreadable = $true }
  foreach ($entry in $roles.PSObject.Properties) {
    if ($p.CommandLine -match ('(?<![\w.])' + [regex]::Escape($entry.Name) + '(?![\w.])')) {
      $scope = 'unresolved_checkout'
      if ($p.ExecutablePath -and $p.ExecutablePath.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { $scope = 'checkout' }
      $items += @{role=$entry.Value; pid=$p.ProcessId; parent_pid=$p.ParentProcessId; scope=$scope;
                  created_at=([DateTimeOffset]$p.CreationDate).ToUnixTimeSeconds()}
    }
  }
}
$status = if ($unreadable) { 'partial_read' } else { 'read' }
@{status=$status; items=$items} | ConvertTo-Json -Depth 5 -Compress
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
        value["items"] = resolve_process_scopes(value["items"])
        return value
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"status": "read_failed", "items": []}


def resolve_process_scopes(items):
    """Recognize a Windows venv interpreter through its observed launcher.

    Only one direct parent hop, the same module role and a near-simultaneous
    creation time qualify. Unrelated base-Python processes stay unresolved.
    """
    parents = {p.get("pid"): p for p in items if p.get("scope") == "checkout"}
    resolved = []
    for source in items:
        row = dict(source)
        parent = parents.get(row.get("parent_pid"))
        created = _positive_clock(row.get("created_at"))
        parent_created = _positive_clock(parent.get("created_at")) if parent else None
        if (row.get("scope") == "unresolved_checkout" and parent
                and row.get("role") == parent.get("role") and created and parent_created
                and 0 <= created - parent_created <= 10):
            row.update(scope="checkout_child", scope_parent_pid=parent["pid"])
        resolved.append(row)
    return resolved


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
    saved = {k: value[k] for k in ("pid", "started_at", "updated_at", "running", "stop_reason", "profile") if k in value}
    identities = {"host", "recovery"} if role == "host" else {role}
    verified_scopes = {"checkout", "checkout_child"}
    matches = [p for p in processes.get("items", []) if p.get("role") in identities and p.get("scope") in verified_scopes]
    uncertain = any(p.get("role") in identities and p.get("scope") not in verified_scopes for p in processes.get("items", []))
    observation = "present" if matches else "unknown" if uncertain or processes.get("status") != "read" else "absent"
    owner_match = any(p.get("pid") == saved.get("pid") and
                      _positive_clock(saved.get("started_at")) and _positive_clock(p.get("created_at")) and
                      p["created_at"] <= saved["started_at"] + 1 for p in matches)
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
        summary["components"] = [{**{k: row[k] for k in ("name", "enabled", "status", "last_started_at", "last_success_at", "last_finished_at", "interval_seconds", "deferred_runs", "consecutive_deferrals", "next_due_at") if k in row},
                                  "error_kinds": _error_kinds(row.get("last_error", "")),
                                  "last_result": _result_evidence(row.get("last_result"))}
                                 for row in rows if isinstance(row, dict)]
    return summary


def _result_evidence(result, *, include_response=True):
    if not isinstance(result, dict):
        return {}
    evidence = {}
    status = result.get("status")
    if isinstance(status, str) and re.fullmatch(r"[A-Za-z0-9_:-]{1,96}", status):
        evidence["status"] = status
    for key in ("ok", "network_fetches", "database_mutation"):
        if isinstance(result.get(key), bool):
            evidence[key] = result[key]
    for key in ("source_rows", "trades", "inserted", "received", "sources_ok", "sources_failed",
                "candles_written", "markets_processed", "markets_considered", "rows_written", "source_failures",
                "event_response_failures", "events_considered", "events_excluded_imprecise",
                "due_observations", "future_observations", "samples_inserted", "already_captured",
                "missing_baseline", "missing_target", "saved_baseline_used", "anchor_conflicts",
                "prices_archived", "archived_baseline_used", "archived_target_used"):
        value = result.get(key)
        if type(value) in (int, float) and math.isfinite(value) and value >= 0:
            evidence[key] = value
    if result.get("market_selection") in ("observed_krw_markets", "explicit_benchmarks"):
        evidence["market_selection"] = result["market_selection"]
    if include_response and isinstance(result.get("event_response_capture"), dict):
        evidence["event_response_capture"] = _result_evidence(result["event_response_capture"], include_response=False)
    return evidence


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
                scope = "all_rows"
                if name == "trade_flow":
                    # Use the existing (exchange,market,trade_ts DESC) index.
                    # This measures only the four benchmark streams, not all coins.
                    scope = "bithumb,upbit / KRW-BTC,KRW-ETH"
                    streams = {}
                    for exchange in ("bithumb", "upbit"):
                        for market in ("KRW-BTC", "KRW-ETH"):
                            row = conn.execute(f'SELECT trade_ts FROM "{table}" WHERE exchange=? AND market=? ORDER BY trade_ts DESC LIMIT 1', (exchange, market)).fetchone()
                            streams[f"{exchange}|{market}"] = _positive_clock(row[0] if row else None)
                    latest = max((v for v in streams.values() if v is not None), default=None)
                else:
                    row = conn.execute(f'SELECT MAX({clock}) FROM "{table}"').fetchone()
                    latest = _positive_clock(row[0] if row else None)
                result[name] = {"status": "read", "latest": latest, "table": table, "clock": clock, "scope": scope}
                if name == "trade_flow":
                    result[name]["streams"] = streams
            except sqlite3.OperationalError as exc:
                kind = "query_timeout" if str(exc) == "interrupted" else "unavailable"
                result[name] = {"status": kind, "latest": None}
    finally:
        conn.close()
    return result


def _positive_clock(value):
    return value if isinstance(value, (int, float)) and math.isfinite(value) and value > 0 else None


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
