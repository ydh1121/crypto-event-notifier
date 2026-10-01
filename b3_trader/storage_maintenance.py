"""Collector-owned daily backup service; no market or strategy writes."""
from pathlib import Path
import signal
import threading
import time

from .managed_backup import atomic_json, maintain, safe_path
from .research_work_lock import ResearchWorkLock
from .storage_cleanup import retire_queued


def cycle(directory):
    status = {'observed_at': time.time(), 'retention_hours': 48, 'interval_hours': 24,
              'canonical_rows_modified': False, 'databases': {}}
    current = {}
    for role, name in (('paper', 'auto_demo.sqlite3'), ('journal', 'crypto_trader.sqlite3')):
        try:
            result = maintain(directory/name, role=role)
            backup = result['backup']
            current[role] = backup
            status['databases'][role] = {'status': 'verified', 'path': backup['path'],
                'snapshot_at': backup['snapshot_at'], 'created': backup['created'],
                'bytes': backup['fingerprint'][2], 'retention': result['retention']}
        except Exception as exc:
            status['databases'][role] = {'status': 'error', 'error_type': type(exc).__name__,
                                         'message': str(exc)}
    if len(current) == 2:
        try:
            with ResearchWorkLock(safe_path(directory/'storage-backup.lock')) as lock:
                if lock.acquired:
                    status['legacy_retention'] = retire_queued(directory, current)
        except Exception as exc:
            status['legacy_retention'] = {'status': 'error', 'error_type': type(exc).__name__}
    atomic_json(directory/'storage-maintenance.json', status)
    return status


def main():
    directory = safe_path(Path(__file__).absolute().parent/'data')
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        result = cycle(directory)
        print('Storage backup: '+', '.join(f'{k}={v["status"]}' for k, v in result['databases'].items()), flush=True)
        # Metadata-only reuse checks, no repeated copying or whole-DB scanning.
        stop.wait(15*60)


if __name__ == '__main__':
    main()
