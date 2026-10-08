"""Reclaim oversized WAL files at collection startup, under exclusive ownership.

Never unlink a canonical sidecar or checkpoint alongside another connection.
Exclusive locking is acquired before the first database access and retained
through SQLite's checkpoint. This also avoids the concurrent WAL-reset race
in older SQLite builds. See sqlite.org/wal.html sections 6, 8 and 11.
"""
from contextlib import closing
import math
from pathlib import Path
import shutil
import sqlite3
import time

from .managed_backup import (INTERVAL, atomic_json, ensure_locked, read_receipt,
                             safe_path, signature, source_identity)
from .research_work_lock import ResearchWorkLock
from .runtime_process_contract import HOST_LOCK
from .storage_review import read_status

MIN_WAL_BYTES = 1024**3
RESULT = 'storage-wal-result.json'
SOURCES = {'paper': 'auto_demo.sqlite3', 'journal': 'crypto_trader.sqlite3'}


def wal_bytes(source):
    path = safe_path(str(source)+'-wal')
    return path.stat().st_size if path.exists() else 0


def checked_source(source):
    source = safe_path(source)
    for suffix in ('-wal', '-shm', '-journal'):
        safe_path(str(source)+suffix)
    return source


def checkpoint_exclusive(source, role, backup):
    """Caller holds host/backup locks. SQLite itself must prove sole ownership."""
    source = checked_source(source)
    identity = source_identity(source)
    proof = read_receipt(Path(backup['path']).parent)
    if (not proof or proof['source'] != identity or proof['role'] != role
            or not 0 <= time.time()-proof['snapshot_at'] < INTERVAL):
        raise ValueError('A recent verified backup is required')
    before = wal_bytes(source)
    body_before = source.stat().st_size
    result = {'status': 'deferred_busy', 'wal_bytes_before': before,
              'database_bytes_before': body_before,
              'source': identity, 'backup_path': backup['path'],
              'backup_snapshot_at': proof['snapshot_at'],
              'backup_created': backup['created'], 'sqlite_version': sqlite3.sqlite_version,
              'canonical_rows_modified': False}
    with closing(sqlite3.connect(source.as_uri()+'?mode=rw', uri=True,
                                timeout=0, isolation_level=None)) as conn:
        # Do not first read journal_mode or sqlite_master in NORMAL mode.
        conn.execute('PRAGMA locking_mode=EXCLUSIVE')
        try:
            conn.execute('BEGIN EXCLUSIVE')
        except sqlite3.OperationalError as exc:
            code = getattr(exc, 'sqlite_errorcode', None)
            # Python 3.10 does not expose sqlite_errorcode/constants yet.
            if ((isinstance(code, int) and (code & 255) in (5, 6))
                    or (code is None and str(exc) in ('database is locked', 'database table is locked'))):
                return result
            raise
        conn.execute('COMMIT')  # EXCLUSIVE mode retains the lock until close.
        if conn.execute('PRAGMA journal_mode').fetchone()[0] != 'wal':
            return {**result, 'status': 'not_wal'}
        schema = signature(conn)
        pages = conn.execute('PRAGMA page_count').fetchone()[0]
        page_size = conn.execute('PRAGMA page_size').fetchone()[0]
        free = conn.execute('PRAGMA freelist_count').fetchone()[0]
        needed = max(0, pages*page_size-source.stat().st_size) + 64*1024**2
        if shutil.disk_usage(source.parent).free < needed:
            raise ValueError('Insufficient free space to finish checkpoint')
        checkpoint = tuple(conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone())
        if checkpoint != (0, 0, 0):
            raise ValueError('Exclusive WAL checkpoint did not complete')
        if (signature(conn) != schema or conn.total_changes != 0
                or conn.execute('PRAGMA page_count').fetchone()[0] != pages
                or conn.execute('PRAGMA freelist_count').fetchone()[0] != free
                or conn.execute('PRAGMA journal_mode').fetchone()[0] != 'wal'):
            raise ValueError('Database layout changed during checkpoint')
        after = wal_bytes(source)
        if after != 0:
            raise ValueError('WAL size readback did not match checkpoint')
        body_after = source.stat().st_size
        result.update(status='reclaimed', wal_bytes_after=after, database_bytes_after=body_after,
                      reclaimed_bytes=max(0, before+body_before-after-body_after), checkpoint=list(checkpoint),
                      schema_unchanged=True, page_count=pages, reusable_bytes=free*page_size,
                      completed_at=time.time())
    return result


def prepare_collection_storage(repo):
    """Startup-only; no periodic truncation, forced restarts or extra copies.

Failure to reclaim space must not prevent otherwise healthy collection. A
small saved receipt exposes the result in the read-only RUN_CHECK report.
"""
    directory = safe_path(repo/'b3_trader/data')
    report = {'version': 1, 'phase': 'before_collection_start', 'observed_at': time.time(),
              'minimum_wal_bytes': MIN_WAL_BYTES, 'minimum_interval_hours': 24,
              'canonical_rows_modified': False, 'databases': {}}
    old = read_status(directory/RESULT)
    previous = old.get('last_success', {}) if isinstance(old, dict) else {}
    report['last_success'] = previous if isinstance(previous, dict) else {}
    try:
        with ResearchWorkLock(safe_path(repo/HOST_LOCK)) as host:
            if not host.acquired:
                report['status'] = 'deferred_host_running'
                return report
            with ResearchWorkLock(safe_path(directory/'storage-backup.lock')) as lock:
                if not lock.acquired:
                    report['status'] = 'deferred_backup_running'
                    return report
                for role, name in SOURCES.items():
                    try:
                        source = checked_source(directory/name)
                        if not source.is_file():
                            report['databases'][role] = {'status': 'missing_database'}
                            continue
                        identity = source_identity(source)
                        size = wal_bytes(source)
                        entry = {'source': identity, 'wal_bytes_before': size}
                        report['databases'][role] = entry
                        if size < MIN_WAL_BYTES:
                            entry['status'] = 'below_threshold'
                            continue
                        prior = report['last_success'].get(role, {})
                        at = prior.get('at') if isinstance(prior, dict) else None
                        if (isinstance(prior, dict) and prior.get('source') == identity
                                and isinstance(at, (int, float)) and math.isfinite(at)
                                and time.time()-at < INTERVAL):
                            entry['status'] = 'daily_limit'
                            continue
                        print(f'STORAGE {role}: checking backup before reclaiming {size/1024**3:.2f} GiB WAL; please wait.', flush=True)
                        backup = ensure_locked(source, role=role)
                        entry.update(checkpoint_exclusive(source, role, backup))
                        if entry['status'] == 'reclaimed':
                            report['last_success'][role] = {'source': identity, 'at': entry['completed_at']}
                            print(f"STORAGE {role}: reclaimed {entry['reclaimed_bytes']/1024**3:.2f} GiB; records preserved.", flush=True)
                        else:
                            print(f"STORAGE {role}: {entry['status']}; no forced cleanup.", flush=True)
                    except (OSError, ValueError, sqlite3.Error) as exc:
                        report['databases'].setdefault(role, {}).update(
                            status='deferred_error', error_type=type(exc).__name__)
                        print(f'STORAGE {role}: cleanup deferred ({type(exc).__name__}).', flush=True)
                report['status'] = 'observed'
    finally:
        report['finished_at'] = time.time()
        try:
            atomic_json(directory/RESULT, report)
        except (OSError, ValueError):
            print('STORAGE: result could not be saved; collection can continue.', flush=True)
    return report
