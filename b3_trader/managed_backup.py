"""One verified local snapshot per database per day, shared across restart/owners.

Only copies are written. Canonical databases are opened read-only. SQLite's
online backup API includes committed WAL contents (sqlite.org/backup.html).
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import time
import uuid

from .research_work_lock import ResearchWorkLock

INTERVAL = 24 * 3600
RETENTION = 48 * 3600
FOLDER = 'managed-backups'
GROUP = re.compile(r'^(paper|journal)-\d{8}T\d{6}Z-[0-9a-f]{8}$')
COUNTS = ('manual_holdings', 'holding_mutation_receipts', 'manual_strategy_records',
          'research_accounts_mx', 'research_profiles_mx', 'research_fills_mx',
          'research_feedback_mx', 'strategy_lab_accounts', 'strategy_lab_learning',
          'strategy_lab_trades', 'strategy_lab_metrics', 'research_intelligence_events',
          'research_intelligence_event_responses', 'research_intelligence_event_prices')


def safe_path(path):
    """Reject symlinks, Windows junctions, and hard-linked files before use."""
    path = Path(path).absolute()
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400
                or (stat.S_ISREG(info.st_mode) and info.st_nlink > 1)):
            raise ValueError('Linked storage path refused: '+item.name)
    return path


def fingerprint(path):
    info = safe_path(path).stat()
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]


def source_identity(path):
    path = safe_path(path)
    info = path.stat()
    if not path.is_file():
        raise ValueError('Existing database file required')
    return {'path': str(path), 'device': info.st_dev, 'inode': info.st_ino}


def atomic_json(path, value):
    safe_path(path)
    temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('x', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(',', ':'))
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def signature(conn):
    rows = [tuple(r) for r in conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def ledger_counts(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in COUNTS if name in tables}


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def read_receipt(group):
    """Cheap reuse gate. No multi-GB hashing or SQLite scan on each user save."""
    try:
        safe_path(group)
        if not GROUP.fullmatch(group.name) or not group.is_dir():
            return None
        if {p.name for p in group.iterdir()} != {'data.sqlite3', 'receipt.json'}:
            return None
        receipt_path = safe_path(group/'receipt.json')
        if receipt_path.stat().st_size > 100_000:
            return None
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if (receipt.get('version') != 1 or receipt.get('quick_check') != 'ok'
                or receipt.get('fingerprint') != fingerprint(group/'data.sqlite3')
                or receipt.get('role') != group.name.split('-')[0]
                or not isinstance(receipt.get('source'), dict)
                or set(receipt['source']) != {'path', 'device', 'inode'}
                or not isinstance(receipt.get('snapshot_at'), (float, int))
                or not math.isfinite(receipt['snapshot_at'])
                or not re.fullmatch('[0-9a-f]{64}', str(receipt.get('sha256', '')))):
            return None
        return receipt
    except (OSError, ValueError, TypeError):
        return None


def verified_groups(folder):
    if not folder.exists():
        return []
    safe_path(folder)
    result = []
    for group in folder.iterdir():
        receipt = read_receipt(group)
        if receipt:
            result.append((group, receipt))
    return result


def clear_interrupted(folder, identity):
    """The OS lock proves no managed writer owns these uncommitted copies."""
    for group in folder.iterdir():
        if not group.name.startswith('.pending-') or not GROUP.fullmatch(group.name[9:]):
            continue
        try:
            safe_path(group)
            marker = safe_path(group/'pending.json')
            if not marker.is_file() or marker.stat().st_size > 100_000:
                continue
            value = json.loads(marker.read_text(encoding='utf-8'))
            if value != {'version': 1, 'source': identity}:
                continue
            files = list(group.iterdir())
            if not {p.name for p in files} <= {'pending.json', 'receipt.json', 'data.sqlite3',
                                               'data.sqlite3-wal', 'data.sqlite3-shm', 'data.sqlite3-journal'}:
                continue
            if any(not safe_path(p).is_file() for p in files):
                continue
            for path in files:
                path.unlink()
            group.rmdir()
        except (OSError, ValueError, TypeError):
            # Unknown or externally changed artifacts stay untouched.
            continue


def verify_copy(path, expected, *, timeout=1800):
    deadline = time.monotonic()+timeout
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1', uri=True)) as conn:
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        if (conn.execute('PRAGMA quick_check').fetchall() != [('ok',)]
                or signature(conn) != expected['schema'] or ledger_counts(conn) != expected['counts']):
            raise ValueError('Backup integrity or ledger readback failed')


def ensure_backup(source, *, role, connection=None, now=None, progress=None, timeout=1800):
    """Return an existing <24h verified copy or atomically publish a new copy."""
    source = safe_path(source)
    folder = source.parent/FOLDER
    safe_path(folder)
    lock_path = safe_path(source.parent/'storage-backup.lock')
    with ResearchWorkLock(lock_path) as lock:
        until = time.monotonic()+5
        while not lock.acquired and time.monotonic() < until:
            time.sleep(.05)
            lock.acquire()
        if not lock.acquired:
            raise ValueError('Another verified backup is in progress; retry shortly')
        return ensure_locked(source, role=role, connection=connection, now=now,
                             progress=progress, timeout=timeout)


def ensure_locked(source, *, role, connection=None, now=None, progress=None, timeout=1800):
    if role not in {'paper', 'journal'}:
        raise ValueError('Unknown database role')
    now = time.time() if now is None else now
    identity = source_identity(source)
    folder = safe_path(source.parent/FOLDER)
    folder.mkdir(exist_ok=True)
    clear_interrupted(folder, identity)
    own = connection is None
    conn = connection or sqlite3.connect(source.as_uri()+'?mode=ro', uri=True, timeout=5)
    started_transaction = not conn.in_transaction
    staging = None
    try:
        conn.execute('PRAGMA query_only=ON')
        if started_transaction:
            conn.execute('BEGIN')
        schema = signature(conn)
        copies = [(group, receipt) for group, receipt in verified_groups(folder)
                  if receipt['source'] == identity and receipt['role'] == role
                  and 0 <= now-receipt['snapshot_at'] < INTERVAL]
        # Additive schema changes do not force repeated full copies in one day.
        # The receipt records the exact earlier schema; no false "current" claim.
        if copies:
            group, receipt = max(copies, key=lambda item: item[1]['snapshot_at'])
            return {**receipt, 'path': str(group/'data.sqlite3'), 'created': False}
        size = conn.execute('PRAGMA page_count').fetchone()[0]*conn.execute('PRAGMA page_size').fetchone()[0]
        if shutil.disk_usage(folder).free < size + 512*1024*1024:
            raise ValueError('Insufficient free space for a verified copy; old backups retained')
        # Counts and copy belong to one source read transaction, including WAL.
        deadline = time.monotonic()+timeout
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        counts = ledger_counts(conn)
        token = uuid.uuid4().hex[:8]
        name = f'{role}-{datetime.fromtimestamp(now, timezone.utc):%Y%m%dT%H%M%SZ}-{token}'
        staging = folder/('.pending-'+name)
        staging.mkdir()
        atomic_json(staging/'pending.json', {'version': 1, 'source': identity})
        target_path = staging/'data.sqlite3'
        def copying(status, remaining, total):
            if time.monotonic() > deadline:
                raise TimeoutError('Backup time limit reached; old backups retained')
            if progress:
                progress(status, remaining, total)
        with closing(sqlite3.connect(target_path)) as target:
            conn.backup(target, pages=2048, progress=copying, sleep=.05)
            # Only the completed copy changes journal mode; never the source.
            if target.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
                raise ValueError('Backup cannot be made self-contained')
        expected = {'schema': schema, 'counts': counts}
        verify_copy(target_path, expected, timeout=timeout)
        with target_path.open('rb') as handle:
            os.fsync(handle.fileno())
        receipt = {'version': 1, 'role': role, 'source': identity, 'snapshot_at': now,
                   'completed_at': time.time(), 'quick_check': 'ok', **expected,
                   'sha256': digest(target_path), 'fingerprint': fingerprint(target_path)}
        atomic_json(staging/'receipt.json', receipt)
        (staging/'pending.json').unlink()
        destination = folder/name
        staging.rename(destination)
        staging = None
        return {**receipt, 'path': str(destination/'data.sqlite3'), 'created': True}
    finally:
        conn.set_progress_handler(None, 0)
        if started_transaction:
            conn.rollback()
        if own:
            conn.close()
        if staging is not None:
            # Only this attempt's private temporary copy is removed on failure.
            shutil.rmtree(staging)


def prune_managed(source, current, *, now=None):
    """Called under storage-backup.lock. Never removes an unverified/unknown group."""
    now = time.time() if now is None else now
    current_group = Path(current['path']).parent
    receipt = read_receipt(current_group)
    identity = source_identity(source)
    if (not receipt or receipt['source'] != identity
            or not 0 <= now-receipt['snapshot_at'] < INTERVAL):
        raise ValueError('Recent verified backup required before pruning')
    removed, removed_bytes = [], 0
    for group, old in verified_groups(source.parent/FOLDER):
        if old['source'] != identity or old['role'] != receipt['role'] or group == current_group:
            continue
        # Age of the newest group member also guards copied/touched artifacts.
        if (old['snapshot_at'] >= now-RETENTION
                or max(p.stat().st_mtime for p in group.iterdir()) >= now-RETENTION):
            continue
        if read_receipt(group) != old:
            raise ValueError('Backup changed during cleanup')
        files = [group/'data.sqlite3', group/'receipt.json']
        size = sum(p.stat().st_size for p in files)
        for path in files:
            safe_path(path).unlink()
        group.rmdir()
        removed.append(group.name)
        removed_bytes += size
    return {'policy': 'verified-local-48h', 'removed': len(removed),
            'removed_bytes': removed_bytes, 'groups': removed}


def maintain(source, *, role, now=None, progress=None):
    source = safe_path(source)
    with ResearchWorkLock(safe_path(source.parent/'storage-backup.lock')) as lock:
        if not lock.acquired:
            raise ValueError('Another backup owns storage; retry shortly')
        current = ensure_locked(source, role=role, now=now, progress=progress)
        retention = prune_managed(source, current, now=now)
        return {'backup': current, 'retention': retention}
