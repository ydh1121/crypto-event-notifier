"""Real SQLite WAL recovery, ownership refusal and restart/reuse evidence."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest

from b3_trader import storage_wal as wal
from b3_trader.managed_backup import ensure_backup
from b3_trader.research_work_lock import ResearchWorkLock
from b3_trader.runtime_process_contract import HOST_LOCK
from b3_trader.storage_review import read_storage


CREATE = '''
import os,sqlite3,sys
c=sqlite3.connect(sys.argv[1])
c.execute('PRAGMA journal_mode=WAL')
c.execute('PRAGMA wal_autocheckpoint=0')
c.execute('CREATE TABLE IF NOT EXISTS strategy_lab_trades(id INTEGER PRIMARY KEY, krw REAL, reason TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS research_intelligence_events(event_id TEXT, title TEXT)')
for batch in range(3):
    c.executemany('INSERT INTO strategy_lab_trades(krw,reason) VALUES (?,?)', [(123.45, 'preserve '*512)]*20)
    c.execute('INSERT INTO research_intelligence_events VALUES (?,?)', (str(batch),'event'))
    c.commit()
# A stopped process with committed WAL, not a fake file padded with garbage.
os._exit(0)
'''


def leave_wal(path):
    subprocess.run([sys.executable, '-c', CREATE, str(path)], check=True)


@pytest.fixture
def source(tmp_path, monkeypatch):
    directory = tmp_path/'b3_trader/data'
    directory.mkdir(parents=True)
    path = directory/'auto_demo.sqlite3'
    leave_wal(path)
    monkeypatch.setattr(wal, 'MIN_WAL_BYTES', 1)
    return tmp_path, path


def logical(path):
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as conn:
        return {'dump': list(conn.iterdump()), 'mode': conn.execute('PRAGMA journal_mode').fetchone(),
                'integrity': conn.execute('PRAGMA quick_check').fetchall()}


def test_reclaim_preserves_committed_wal_rows_and_backup_without_vacuum(source, monkeypatch):
    root, path = source
    before = logical(path)
    copy = ensure_backup(path, role='paper')
    copy_bytes = Path(copy['path']).read_bytes()
    # The lock must remain exclusive after COMMIT, throughout checkpoint/readback.
    original = wal.signature
    blocked = []
    def signature(conn):
        with closing(sqlite3.connect(path, timeout=0)) as other:
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                other.execute('SELECT COUNT(*) FROM strategy_lab_trades')
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                other.execute('BEGIN IMMEDIATE')
        blocked.append(True)
        return original(conn)
    monkeypatch.setattr(wal, 'signature', signature)
    report = wal.prepare_collection_storage(root)
    entry = report['databases']['paper']
    assert entry['status'] == 'reclaimed' and len(blocked) == 2
    assert entry['wal_bytes_before'] > 0 and entry['wal_bytes_after'] == 0
    assert entry['reclaimed_bytes'] == max(0, entry['database_bytes_before'] +
        entry['wal_bytes_before']-entry['database_bytes_after'])
    assert entry['backup_path'] == copy['path'] and not entry['backup_created']
    assert Path(copy['path']).read_bytes() == copy_bytes
    assert entry['canonical_rows_modified'] is False
    assert logical(path) == before
    # RUN_CHECK consumes the saved receipt, without running cleanup itself.
    files = {p: p.read_bytes() for p in path.parent.rglob('*') if p.is_file()}
    read = read_storage(path)
    assert read['wal_startup'] == report
    assert {p: p.read_bytes() for p in path.parent.rglob('*') if p.is_file()} == files


@pytest.mark.parametrize('owner', ['reader', 'idle_connection', 'writer'])
def test_any_other_database_owner_defers_without_waiting_or_truncating(source, owner):
    root, path = source
    ensure_backup(path, role='paper')
    with closing(sqlite3.connect(path, timeout=0)) as other:
        if owner == 'reader': other.execute('BEGIN')
        if owner == 'writer': other.execute('BEGIN IMMEDIATE')
        other.execute('SELECT COUNT(*) FROM strategy_lab_trades').fetchone()
        before = {p: p.read_bytes() for p in path.parent.glob('auto_demo.sqlite3*')}
        start = time.monotonic()
        result = wal.prepare_collection_storage(root)
        assert time.monotonic()-start < 2
        assert result['databases']['paper']['status'] == 'deferred_busy'
        assert {p: p.read_bytes() for p in path.parent.glob('auto_demo.sqlite3*')} == before
        other.rollback()


@pytest.mark.parametrize('lock_name', [HOST_LOCK, 'b3_trader/data/storage-backup.lock'])
def test_existing_host_or_backup_ownership_skips_all_database_work(source, lock_name):
    root, path = source
    before = logical(path)
    with ResearchWorkLock(root/lock_name):
        result = wal.prepare_collection_storage(root)
    assert result['status'].startswith('deferred_')
    assert result['databases'] == {}
    assert not (path.parent/'managed-backups').exists()
    assert logical(path) == before


def test_backup_failure_leaves_wal_and_records_untouched(source, monkeypatch):
    root, path = source
    before = {p: p.read_bytes() for p in path.parent.glob('auto_demo.sqlite3*')}
    def fail(*args, **kwargs): raise ValueError('copy verification failed')
    monkeypatch.setattr(wal, 'ensure_locked', fail)
    result = wal.prepare_collection_storage(root)
    assert result['databases']['paper']['status'] == 'deferred_error'
    assert {p: p.read_bytes() for p in path.parent.glob('auto_demo.sqlite3*')} == before


def test_small_wal_missing_database_and_daily_success_do_not_copy_or_repeat(source, monkeypatch):
    root, path = source
    monkeypatch.setattr(wal, 'MIN_WAL_BYTES', 1024**3)
    first = wal.prepare_collection_storage(root)
    assert first['databases']['paper']['status'] == 'below_threshold'
    assert first['databases']['journal']['status'] == 'missing_database'
    assert not (path.parent/'crypto_trader.sqlite3').exists()
    assert not (path.parent/'managed-backups').exists()
    monkeypatch.setattr(wal, 'MIN_WAL_BYTES', 1)
    first_cleanup = wal.prepare_collection_storage(root)['databases']['paper']
    assert first_cleanup['status'] == 'reclaimed' and first_cleanup['backup_created']
    assert logical(Path(first_cleanup['backup_path']))['dump'] == logical(path)['dump']
    leave_wal(path)
    size = wal.wal_bytes(path)
    expected = logical(path)
    for _ in range(2):
        result = wal.prepare_collection_storage(root)
        assert result['databases']['paper']['status'] == 'daily_limit'
        assert result['last_success']['paper']['source']['path'] == str(path)
        assert wal.wal_bytes(path) == size
    assert logical(path) == expected
    receipt = json.loads((path.parent/wal.RESULT).read_text())
    receipt['last_success']['paper']['at'] -= 86401
    (path.parent/wal.RESULT).write_text(json.dumps(receipt))
    assert wal.prepare_collection_storage(root)['databases']['paper']['status'] == 'reclaimed'
    assert len(list((path.parent/'managed-backups').iterdir())) == 1


@pytest.mark.parametrize('kind', ['database', 'wal', 'shm'])
def test_linked_canonical_files_are_preserved(source, tmp_path, monkeypatch, kind):
    root, path = source
    target = path if kind == 'database' else path.with_name(path.name+'-'+kind)
    original = tmp_path/('original-'+kind)
    target.rename(original)
    before = original.read_bytes()
    target.symlink_to(original)
    def fail(*args, **kwargs): raise AssertionError('linked path must not reach backup')
    monkeypatch.setattr(wal, 'ensure_locked', fail)
    report = wal.prepare_collection_storage(root)
    assert report['databases']['paper']['status'] == 'deferred_error'
    assert target.is_symlink() and original.read_bytes() == before


def test_unverified_receipt_cannot_authorize_checkpoint(source):
    _, path = source
    copy = ensure_backup(path, role='paper')
    receipt = Path(copy['path']).parent/'receipt.json'
    value = json.loads(receipt.read_text()); value['quick_check'] = 'failed'
    receipt.write_text(json.dumps(value))
    before = wal.wal_bytes(path)
    with pytest.raises(ValueError, match='verified backup'):
        wal.checkpoint_exclusive(path, 'paper', copy)
    assert wal.wal_bytes(path) == before
