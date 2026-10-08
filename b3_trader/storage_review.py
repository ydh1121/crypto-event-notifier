"""Bounded storage inventory. No deletion, backup, checkpoint or database rewrite."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import stat
import time

BACKUP_FOLDERS = ('backups', 'maintenance-backups', 'recovery-backups',
                  'holding-management-backups', 'holding-registration-backups',
                  'manual-planning-backups', 'managed-backups')
DATA_FOLDERS = ('research-warehouse', 'research-platform', 'local-process-logs')


def linked(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def file_info(path):
    if linked(path):
        return {'status': 'linked_path_skipped'}
    info = path.stat()
    return {'status': 'read', 'bytes': info.st_size, 'mtime': info.st_mtime}


def database_info(path):
    if path is None:
        return {'status': 'unresolved'}
    path = Path(path).absolute()
    try:
        result = {'path': str(path), **file_info(path)}
        if result['status'] != 'read':
            return result
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=.2)) as conn:
            conn.execute('PRAGMA query_only=ON')
            page_size = conn.execute('PRAGMA page_size').fetchone()[0]
            page_count = conn.execute('PRAGMA page_count').fetchone()[0]
            free = conn.execute('PRAGMA freelist_count').fetchone()[0]
            result.update(page_size=page_size, page_count=page_count, reusable_bytes=free*page_size,
                          allocated_bytes=page_count*page_size,
                          tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])
        result['sidecars'] = {}
        for suffix in ('-wal', '-shm'):
            sidecar = Path(str(path)+suffix)
            result['sidecars'][suffix] = file_info(sidecar) if sidecar.exists() else {'status': 'absent'}
        return result
    except (OSError, sqlite3.Error) as exc:
        return {'path': str(path), 'status': 'unavailable', 'error_type': type(exc).__name__}


def folder_info(path, *, deadline, now, backup=False):
    result = {'name': path.name, 'status': 'read', 'bytes': 0, 'files': 0, 'skipped_links': 0}
    if backup:
        result.update(backup_files=[], files_older_than_48h=0, bytes_older_than_48h=0)
    try:
        if not path.exists():
            return {**result, 'status': 'absent'}
        if linked(path):
            return {**result, 'status': 'linked_path_skipped'}
        pending = [path]
        seen = 0
        while pending:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    seen += 1
                    if seen > 50000 or time.monotonic() > deadline:
                        return {**result, 'status': 'partial_limit'}
                    child = Path(entry.path)
                    if linked(child):
                        result['skipped_links'] += 1
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(child)
                    elif entry.is_file(follow_symlinks=False):
                        info = entry.stat(follow_symlinks=False)
                        result['files'] += 1
                        result['bytes'] += info.st_size
                        if backup:
                            if info.st_mtime < now-2*86400:
                                result['files_older_than_48h'] += 1
                                result['bytes_older_than_48h'] += info.st_size
                            if len(result['backup_files']) < 200:
                                result['backup_files'].append({'path': child.relative_to(path).as_posix(),
                                                              'bytes': info.st_size, 'mtime': info.st_mtime})
        if backup:
            result['listed_all_files'] = result['files'] == len(result['backup_files'])
        return result
    except OSError as exc:
        return {**result, 'status': 'partial_error', 'error_type': type(exc).__name__}


def read_storage(paper, holdings=None, *, seconds=5):
    directory = Path(paper).absolute().parent
    now = time.time()
    # A large archive must not prevent observing all later folders.
    budget = seconds / (len(BACKUP_FOLDERS)+len(DATA_FOLDERS))
    return {'observed_at': now, 'mode': 'read_only', 'data_directory': str(directory),
            'sqlite_version': sqlite3.sqlite_version,
            'paper': database_info(paper), 'holdings': database_info(holdings),
            'folders': [folder_info(directory/name, deadline=time.monotonic()+budget, now=now, backup=name in BACKUP_FOLDERS)
                        for name in (*BACKUP_FOLDERS, *DATA_FOLDERS)],
            'requested_backup_retention_hours': 48, 'cleanup_applied': False,
            'last_cleanup': read_status(directory/'storage-cleanup-result.json'),
            'maintenance': read_status(directory/'storage-maintenance.json'),
            'wal_startup': read_status(directory/'storage-wal-result.json'),
            'limitations': ['Folder ages do not establish that a backup is safe to delete.',
                            'No full table scan or database integrity scan was run.',
                            'Active files may change during this observation.']}


def read_status(path):
    import json
    try:
        if not path.exists():
            return {'status': 'absent'}
        if linked(path) or path.stat().st_size > 1_000_000:
            return {'status': 'unavailable'}
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'status': 'unavailable'}
