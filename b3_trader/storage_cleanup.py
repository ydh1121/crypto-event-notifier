"""Explicit, idle-only cleanup of known expired backup files. No DB row deletion."""
import json
from pathlib import Path
import re
import time

from .managed_backup import (RETENTION, atomic_json, digest, ensure_locked, fingerprint,
                             prune_managed, read_receipt, safe_path, source_identity, verify_copy)
from .research_work_lock import ResearchWorkLock
from .runtime_process_contract import HOST_LOCK
from .runtime_review import _processes

LEGACY = {
    'backups': ('journal', re.compile(r'^crypto-trader-\d{8}-\d{6}\.sqlite3$')),
    'maintenance-backups': ('paper', re.compile(r'^auto-demo-before-retention-\d{8}-\d{6}\.sqlite3$')),
    'holding-management-backups': ('journal', re.compile(r'^before-manage-holding-[0-9a-f]{32}\.sqlite3$')),
    'holding-registration-backups': ('journal', re.compile(r'^before-add-holding-[0-9a-f]{32}\.sqlite3$')),
    'manual-planning-backups': ('journal', re.compile(r'^before-manual-plans-[0-9a-f]{32}\.sqlite3$')),
}
RECOVERY = re.compile(r'^\d{8}-\d{6}-[0-9a-f]{8}$')


def candidate(database, role, now, *, receipt=None):
    """Zero-byte inactive backup WAL may be removed as part of that copy only."""
    files = [database]
    for suffix in ('-wal', '-shm', '-journal'):
        item = Path(str(database)+suffix)
        if item.exists():
            safe_path(item)
            if suffix in ('-wal', '-journal') and item.stat().st_size:
                return None
            files.append(item)
    if receipt:
        files.append(receipt)
    for path in files:
        safe_path(path)
        if not path.is_file() or path.stat().st_mtime >= now-RETENTION:
            return None
    return {'role': role, 'database': str(database),
            'files': [{'path': str(p), 'fingerprint': fingerprint(p)} for p in files],
            'bytes': sum(p.stat().st_size for p in files)}


def inventory(directory, *, now=None):
    """Strict one-level ownership patterns, never a recursive age-based delete."""
    now = time.time() if now is None else now
    directory = safe_path(directory)
    candidates, skipped = [], []
    for name, (role, pattern) in LEGACY.items():
        folder = directory/name
        try:
            safe_path(folder)
            if not folder.exists():
                continue
            for path in folder.iterdir():
                if not pattern.fullmatch(path.name):
                    continue
                try:
                    item = candidate(path, role, now)
                    if item:
                        candidates.append(item)
                except (OSError, ValueError):
                    skipped.append(str(path))
        except (OSError, ValueError):
            skipped.append(str(folder))
    recovery = directory/'recovery-backups'
    try:
        safe_path(recovery)
        for group in recovery.iterdir() if recovery.exists() else ():
            if not RECOVERY.fullmatch(group.name):
                continue
            try:
                safe_path(group)
                expected = {'auto_demo.sqlite3', 'backup-receipt.json',
                            'auto_demo.sqlite3-wal', 'auto_demo.sqlite3-shm'}
                if not {p.name for p in group.iterdir()} <= expected:
                    continue
                receipt = safe_path(group/'backup-receipt.json')
                if not receipt.is_file() or receipt.stat().st_size > 100_000:
                    continue
                value = json.loads(receipt.read_text(encoding='utf-8'))
                if (value.get('quick_check') != 'ok'
                        or value.get('bytes') != (group/'auto_demo.sqlite3').stat().st_size):
                    continue
                item = candidate(group/'auto_demo.sqlite3', 'paper', now, receipt=receipt)
                if item:
                    candidates.append(item)
            except (OSError, ValueError, TypeError):
                skipped.append(str(group))
    except (OSError, ValueError):
        skipped.append(str(recovery))
    return {'candidates': candidates, 'bytes': sum(c['bytes'] for c in candidates),
            'skipped_paths': skipped, 'retention_hours': 48}


def require_idle(repo):
    state = _processes(repo, include_review=True)
    if state.get('status') != 'read' or state.get('items'):
        raise ValueError('Close RUN_REVIEW and stop collection with Ctrl+C; wait for shutdown, then run CLEAN_STORAGE.cmd.')


def apply_candidates(plan, current, *, now=None, result=None):
    """Caller owns host/storage locks. Refuse changed paths and changed scope."""
    now = time.time() if now is None else now
    result = result if result is not None else {'removed_copies': 0, 'removed_bytes': 0, 'removed': []}
    for item in plan['candidates']:
        role = item['role']
        if role not in current:
            raise ValueError('No verified replacement for '+role)
        copy = current[role]
        proof = read_receipt(Path(copy['path']).parent)
        if (not proof or proof['source'] != source_identity(Path(copy['source']['path']))
                or not 0 <= now-proof['snapshot_at'] < 24*3600):
            raise ValueError('Recent verified replacement required')
        for entry in item['files']:
            path = Path(entry['path'])
            if fingerprint(path) != entry['fingerprint'] or path.stat().st_mtime >= now-RETENTION:
                raise ValueError('Backup changed after inventory; cleanup stopped')
        # Recheck expected sidecar set as well as metadata; a newly active backup
        # must not lose its main file between the inventory and this operation.
        db = Path(item['database'])
        receipt = next((Path(f['path']) for f in item['files'] if Path(f['path']).name=='backup-receipt.json'), None)
        if candidate(db, role, now, receipt=receipt) != item:
            raise ValueError('Backup file set changed; cleanup stopped')
        for entry in sorted(item['files'], key=lambda f: f['path']==str(db)):
            safe_path(entry['path']).unlink()
            result['removed_bytes'] += entry['fingerprint'][2]
            result['removed'].append(entry['path'])
        result['removed_copies'] += 1
        if receipt:
            db.parent.rmdir()
    return result


def retire_queued(directory, current, *, now=None):
    """Only backups recorded while idle by CLEAN_STORAGE may age out later."""
    path = safe_path(directory/'storage-retirement.json')
    if not path.exists():
        return {'status': 'not_configured'}
    if path.stat().st_size > 1_000_000:
        raise ValueError('Unexpected retirement queue size')
    queue = json.loads(path.read_text(encoding='utf-8'))
    if queue.get('sources') != {role: value['source'] for role, value in current.items()}:
        raise ValueError('Database identity changed; legacy backups kept')
    eligible = inventory(directory, now=now)
    eligible['candidates'] = [item for item in eligible['candidates'] if item in queue['candidates']]
    result = apply_candidates(eligible, current, now=now)
    if result['removed_copies']:
        queue['candidates'] = [item for item in queue['candidates'] if item not in eligible['candidates']]
        atomic_json(path, queue)
    return result


def clean_storage(repo, report_path):
    repo = safe_path(repo)
    directory = safe_path(repo/'b3_trader/data')
    sources = {'paper': directory/'auto_demo.sqlite3', 'journal': directory/'crypto_trader.sqlite3'}
    report = {'version': 1, 'started_at': time.time(), 'status': 'started',
              'canonical_rows_modified': False, 'warehouse_modified': False}
    try:
        require_idle(repo)
        with ResearchWorkLock(safe_path(repo/HOST_LOCK)) as host:
            if not host.acquired:
                raise ValueError('Collection host is still running')
            with ResearchWorkLock(safe_path(directory/'storage-backup.lock')) as lock:
                if not lock.acquired:
                    raise ValueError('Another backup is running')
                require_idle(repo)
                report['plan'] = inventory(directory)
                atomic_json(report_path, report)
                print(f"Expired recognized backups: {len(report['plan']['candidates'])} copies / {report['plan']['bytes']/1024**3:.2f} GiB", flush=True)
                current = {}
                for role, source in sources.items():
                    if not source.is_file():
                        raise ValueError('Canonical '+role+' database missing; old backups kept')
                    print('Verifying current '+role+' backup...', flush=True)
                    band = [-1]
                    def progress(_status, remaining, total):
                        value = int((total-remaining)*10/total) if total else 10
                        if value != band[0]:
                            band[0] = value
                            print(f'  {value*10}%', flush=True)
                    copy = ensure_locked(source, role=role, progress=progress)
                    if not copy['created']:
                        verify_copy(Path(copy['path']), copy)
                        if digest(Path(copy['path'])) != copy['sha256']:
                            raise ValueError('Backup hash mismatch; old backups kept')
                    current[role] = copy
                report['current_backups'] = current
                atomic_json(report_path, report)
                require_idle(repo)
                # Discover anew after the long copy, then delete only that plan.
                report['plan'] = inventory(directory)
                report['cleanup'] = {'removed_copies': 0, 'removed_bytes': 0, 'removed': []}
                apply_candidates(report['plan'], current, result=report['cleanup'])
                report['managed_retention'] = {role: prune_managed(sources[role], copy)
                                               for role, copy in current.items()}
                report['remaining_expired'] = inventory(directory)
                # Recent legacy copies remain until their own 48h expiry. Later
                # automatic cleanup is limited to these exact idle-time files.
                queue = inventory(directory, now=time.time()+RETENTION)
                atomic_json(directory/'storage-retirement.json', {
                    'sources': {role: value['source'] for role, value in current.items()},
                    'candidates': queue['candidates']})
                report['pending_legacy_copies'] = len(queue['candidates'])
                report['status'] = 'complete'
                print(f"Removed: {report['cleanup']['removed_bytes']/1024**3:.2f} GiB. Current databases and research warehouse preserved.", flush=True)
                print('Next: UPDATE_COLLECTION.cmd (keep open), then RUN_REVIEW.cmd and RUN_CHECK.cmd.', flush=True)
    except Exception as exc:
        report.update(status='stopped', error_type=type(exc).__name__, message=str(exc))
        raise ValueError('Storage cleanup stopped: '+str(exc)) from exc
    finally:
        report['finished_at'] = time.time()
        atomic_json(report_path, report)
        # Bounded last-result pointer is included by RUN_CHECK, never raw data.
        if directory.is_dir():
            atomic_json(directory/'storage-cleanup-result.json', report)
    return report
