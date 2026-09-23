from __future__ import annotations

import json
from pathlib import Path
import sys
import subprocess
import threading

from b3_trader.local_process_host import LocalProcessHost
from b3_trader.research_work_lock import ResearchWorkLock
from b3_trader.runtime_process_contract import HOST_LOCK, HOST_LOGS, HOST_STATUS, SIDECARS


def command(source):
    return [sys.executable, "-u", "-c", source]


def run_host(tmp_path, commands):
    host = LocalProcessHost(tmp_path, commands=commands, retry_seconds=.05, tick_seconds=.01)
    watchdog = threading.Timer(5, host.stop_event.set)
    watchdog.start()
    try:
        code = host.run()
    finally:
        watchdog.cancel()
    assert not host.children
    assert host.stop_reason != "stop_requested", "test timed out"
    return host, code, json.loads((tmp_path / HOST_STATUS).read_text())


def test_collector_process_crash_recovers_without_restarting_server(tmp_path):
    paper = command("""
from pathlib import Path
import sys,time
p=Path('attempts'); n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n))
if n==1:
    print('ModuleNotFoundError: simulated startup dependency',file=sys.stderr)
    sys.exit(19)
time.sleep(10)
""")
    app = command("""
from pathlib import Path
import time
while not Path('attempts').exists() or int(Path('attempts').read_text() or '0')<2: time.sleep(.02)
time.sleep(.05)
""")
    host, code, status = run_host(tmp_path, {"paper": paper, "app": app})
    assert code == 0 and status['running'] is False
    assert status['children']['paper']['starts'] == 2
    assert status['children']['paper']['last_failure']['exit_code'] == 19
    assert status['children']['app']['starts'] == 1
    log = (tmp_path / HOST_LOGS / 'paper.log').read_text()
    assert 'simulated startup dependency' in log and 'code=19' in log
    assert host.stop_reason == 'app_clean_exit'


def test_code_update_returns_75_after_stopping_every_owned_child(tmp_path):
    commands = {role: command('import time; time.sleep(10)') for role, *_ in SIDECARS}
    commands['app'] = command('import time,sys; time.sleep(.15); sys.exit(75)')
    _, code, status = run_host(tmp_path, commands)
    assert code == 75 and status['stop_reason'] == 'code_update'
    assert all(s['starts'] == 1 and s['pid'] is None and s['restart_at'] is None
               for s in status['children'].values())
    assert all(s['last_exit_code'] is not None for s in status['children'].values())


def test_app_failure_retries_only_app_and_holdings_has_no_new_retry(tmp_path):
    app = command("""
from pathlib import Path
import sys,time
p=Path('app_attempts'); n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n))
time.sleep(.1)
sys.exit(23 if n==1 else 0)
""")
    _, code, status = run_host(tmp_path, {
        'research': command('import time; time.sleep(10)'),
        'holdings': command('import sys; sys.exit(29)'), 'app': app})
    assert code == 0
    assert status['children']['app']['starts'] == 2
    assert status['children']['app']['last_failure']['exit_code'] == 23
    assert status['children']['research']['starts'] == 1
    assert status['children']['holdings']['starts'] == 1
    assert status['children']['holdings']['last_exit_code'] == 29


def test_signal_stop_cancels_retries_and_releases_checkout_lock(tmp_path):
    host = LocalProcessHost(tmp_path, commands={
        'paper': command('import sys; sys.exit(7)'),
        'app': command('import time; time.sleep(10)')}, retry_seconds=10, tick_seconds=.01)
    timer = threading.Timer(.15, host.stop_event.set)
    timer.start()
    try:
        assert host.run() == 0
    finally:
        timer.cancel()
    assert not host.children and not host.retry_at
    assert host.states['paper']['starts'] == 1
    with ResearchWorkLock(tmp_path / HOST_LOCK) as lock:
        assert lock.acquired


def test_duplicate_host_starts_no_children(tmp_path):
    with ResearchWorkLock(tmp_path / HOST_LOCK) as lock:
        assert lock.acquired
        host = LocalProcessHost(tmp_path, commands={'app': command("raise AssertionError('must not start')")})
        assert host.run() == 2
        assert not host.children and not (tmp_path / HOST_STATUS).exists()


def test_diagnostic_write_failure_does_not_kill_children(tmp_path):
    (tmp_path / HOST_STATUS).mkdir(parents=True)
    host = LocalProcessHost(tmp_path, commands={'app': command('import time; time.sleep(.05)')}, tick_seconds=.01)
    assert host.run() == 0
    assert host.status_error is not None and host.states['app']['starts'] == 1


def test_cleanup_failure_blocks_automatic_host_restart(tmp_path, monkeypatch):
    class Process:
        pid = 12345
        def __init__(self, code): self.code = code
        def poll(self): return self.code
        def terminate(self): raise PermissionError()
        def wait(self, timeout): raise subprocess.TimeoutExpired('test', timeout)
        def kill(self): raise PermissionError()

    host = LocalProcessHost(tmp_path, commands={'paper': [], 'app': []})
    monkeypatch.setattr(host, '_start', lambda role: host.children.update({role: Process(0 if role == 'app' else None)}))
    assert host.run() == 2
    assert host.stop_reason == 'child_cleanup_failed'
    assert host.states['paper']['state'] == 'stop_failed'
