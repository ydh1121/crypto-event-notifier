import json
import os
from pathlib import Path
import sqlite3
import time

import pytest

from b3_trader import managed_backup as backup, storage_cleanup as cleanup
from b3_trader.journal_backup import backup_journal
from b3_trader.research_work_lock import ResearchWorkLock
from b3_trader.storage_maintenance import cycle


def database(path, table='manual_holdings'):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(f'CREATE TABLE {table}(id INTEGER PRIMARY KEY, value TEXT)')
        conn.execute(f"INSERT INTO {table} VALUES(1,'precious')")
    return path


def age(path, timestamp):
    os.utime(path, (timestamp, timestamp))


def aged_copy(source, role, stamp):
    result = backup.ensure_backup(source, role=role, now=stamp)
    group = Path(result['path']).parent
    age(Path(result['path']), stamp)
    receipt = json.loads((group/'receipt.json').read_text())
    receipt['fingerprint'] = backup.fingerprint(Path(result['path']))
    backup.atomic_json(group/'receipt.json', receipt)
    age(group/'receipt.json', stamp)
    return result


def test_wal_rows_survive_reopen_and_journal_owners_share_one_copy(tmp_path):
    source = database(tmp_path/'crypto_trader.sqlite3')
    writer = sqlite3.connect(source)
    writer.execute('PRAGMA journal_mode=WAL')
    writer.execute("INSERT INTO manual_holdings VALUES(2,'WAL only')")
    writer.commit()
    before = source.read_bytes()
    wal = Path(str(source)+'-wal').read_bytes()
    first = backup.ensure_backup(source, role='journal')
    with sqlite3.connect(source) as conn:
        assert backup_journal(conn, tmp_path/'old-feature-folder', 'unused-') == Path(first['path'])
    restarted = backup.ensure_backup(source, role='journal')
    assert not restarted['created'] and restarted['path'] == first['path']
    assert len(list((tmp_path/backup.FOLDER).iterdir())) == 1
    assert source.read_bytes() == before and Path(str(source)+'-wal').read_bytes() == wal
    with sqlite3.connect(first['path']) as conn:
        assert conn.execute('PRAGMA journal_mode').fetchone() == ('delete',)
        assert conn.execute('SELECT value FROM manual_holdings ORDER BY id').fetchall() == [('precious',), ('WAL only',)]
    assert {p.name for p in Path(first['path']).parent.iterdir()} == {'data.sqlite3','receipt.json'}
    writer.close()


def test_48h_boundary_unknowns_other_database_and_future_copy_are_preserved(tmp_path):
    now = time.time()
    source = database(tmp_path/'crypto_trader.sqlite3')
    old = aged_copy(source, 'journal', now-backup.RETENTION-1)
    yesterday = aged_copy(source, 'journal', now-backup.INTERVAL)
    other = database(tmp_path/'other.sqlite3')
    other_copy = aged_copy(other, 'journal', now-3*backup.INTERVAL)
    future = aged_copy(source, 'journal', now+backup.INTERVAL)
    unknown = tmp_path/backup.FOLDER/'keep.txt'; unknown.write_text('keep')
    result = backup.maintain(source, role='journal', now=now)
    assert result['retention']['removed'] == 1
    assert not Path(old['path']).exists()
    assert Path(yesterday['path']).exists() and Path(other_copy['path']).exists()
    assert Path(future['path']).exists() and unknown.exists()
    assert backup.maintain(source, role='journal', now=now)['retention']['removed'] == 0


def test_exact_48h_copy_is_kept_until_expired(tmp_path):
    source = database(tmp_path/'crypto_trader.sqlite3'); now = time.time()
    old = aged_copy(source, 'journal', now-backup.RETENTION)
    assert backup.maintain(source, role='journal', now=now)['retention']['removed'] == 0
    assert backup.maintain(source, role='journal', now=now+.1)['retention']['removed'] == 1
    assert not Path(old['path']).exists()


def test_wal_writer_can_advance_while_backup_keeps_one_consistent_snapshot(tmp_path):
    source=database(tmp_path/'crypto_trader.sqlite3')
    writer=sqlite3.connect(source)
    writer.execute('PRAGMA journal_mode=WAL')
    updated=[]
    def concurrent(*_):
        if not updated:
            writer.execute("INSERT INTO manual_holdings VALUES(2,'new commit')")
            writer.commit();updated.append(True)
    result=backup.ensure_backup(source,role='journal',progress=concurrent)
    assert updated and result['counts']['manual_holdings']==1
    assert writer.execute('SELECT COUNT(*) FROM manual_holdings').fetchone()[0]==2
    with sqlite3.connect(result['path']) as saved:
        assert saved.execute('SELECT COUNT(*) FROM manual_holdings').fetchone()[0]==1
    writer.close()


@pytest.mark.parametrize('failure', ['space','integrity','copy'])
def test_failed_replacement_keeps_old_and_canonical_bytes(tmp_path, monkeypatch, failure):
    source = database(tmp_path/'crypto_trader.sqlite3'); now = time.time()
    old = aged_copy(source, 'journal', now-3*backup.INTERVAL)
    before = source.read_bytes()
    if failure=='space':
        monkeypatch.setattr(backup.shutil, 'disk_usage', lambda _: type('Space',(),{'free':0})())
    elif failure=='integrity':
        monkeypatch.setattr(backup, 'verify_copy', lambda *a, **k: (_ for _ in ()).throw(ValueError('corrupt')))
    def fail(*args):
        raise OSError('interrupted')
    with pytest.raises((ValueError,OSError)):
        backup.maintain(source, role='journal', now=now, progress=fail if failure=='copy' else None)
    assert source.read_bytes()==before and Path(old['path']).exists()
    assert not list((tmp_path/backup.FOLDER).glob('.pending-*'))


def test_linked_paths_missing_sources_and_busy_lock_do_not_write(tmp_path):
    source = database(tmp_path/'crypto_trader.sqlite3')
    elsewhere = tmp_path/'elsewhere'; elsewhere.mkdir()
    (tmp_path/backup.FOLDER).symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError, match='Linked'):
        backup.ensure_backup(source, role='journal')
    assert list(elsewhere.iterdir())==[]
    (tmp_path/backup.FOLDER).unlink()
    with pytest.raises(FileNotFoundError):
        backup.ensure_backup(tmp_path/'missing', role='paper')
    assert not (tmp_path/'missing').exists()
    with ResearchWorkLock(tmp_path/'storage-backup.lock'):
        with pytest.raises(ValueError, match='owns storage'):
            backup.maintain(source, role='journal')


def test_corrupt_reused_copy_is_not_selected(tmp_path):
    source=database(tmp_path/'crypto_trader.sqlite3')
    first=backup.ensure_backup(source,role='journal')
    Path(first['path']).write_bytes(b'broken')
    second=backup.ensure_backup(source,role='journal')
    assert second['created'] and second['path'] != first['path']
    assert Path(first['path']).read_bytes()==b'broken'  # unknown state retained


def test_crashed_owned_staging_is_removed_but_unknown_staging_is_preserved(tmp_path):
    source=database(tmp_path/'crypto_trader.sqlite3')
    folder=tmp_path/backup.FOLDER;folder.mkdir()
    owned=folder/'.pending-journal-20261001T000000Z-01234567';owned.mkdir()
    backup.atomic_json(owned/'pending.json',{'version':1,'source':backup.source_identity(source)})
    (owned/'data.sqlite3').write_bytes(b'incomplete')
    unknown=folder/'.pending-journal-20261001T000000Z-abcdef01';unknown.mkdir()
    (unknown/'data.sqlite3').write_bytes(b'unknown')
    backup.ensure_backup(source,role='journal')
    assert not owned.exists() and unknown.exists()


def legacy_fixture(tmp_path):
    repo=tmp_path/'repo';directory=repo/'b3_trader/data'
    paper=database(directory/'auto_demo.sqlite3','strategy_lab_trades')
    journal=database(directory/'crypto_trader.sqlite3')
    now=time.time()
    old=directory/'backups/crypto-trader-20260901-010101.sqlite3';old.parent.mkdir();old.write_bytes(journal.read_bytes());age(old,now-3*backup.INTERVAL)
    recent=directory/'holding-management-backups'/('before-manage-holding-'+'a'*32+'.sqlite3');recent.parent.mkdir();recent.write_bytes(journal.read_bytes())
    recovery=directory/'recovery-backups/20260924-110445-3a82105c';recovery.mkdir(parents=True)
    copied=recovery/'auto_demo.sqlite3';copied.write_bytes(paper.read_bytes())
    (recovery/'backup-receipt.json').write_text(json.dumps({'quick_check':'ok','bytes':copied.stat().st_size}))
    (recovery/'auto_demo.sqlite3-wal').write_bytes(b'');(recovery/'auto_demo.sqlite3-shm').write_bytes(b'x')
    for p in recovery.iterdir():age(p,now-3*backup.INTERVAL)
    evidence=old.parent/'v16b-e2e-evidence.json';evidence.write_text('keep');age(evidence,now-3*backup.INTERVAL)
    warehouse=directory/'research-warehouse';warehouse.mkdir();(warehouse/'learning.parquet').write_bytes(b'keep')
    return repo,paper,journal,old,recent,recovery,evidence


def test_idle_cleanup_preserves_live_dbs_warehouse_unknown_and_recent_then_queue_expires(tmp_path,monkeypatch):
    repo,paper,journal,old,recent,recovery,evidence=legacy_fixture(tmp_path)
    monkeypatch.setattr(cleanup,'_processes',lambda *a,**k:{'status':'read','items':[]})
    before={p:p.read_bytes() for p in (paper,journal,evidence,paper.parent/'research-warehouse/learning.parquet')}
    report=cleanup.clean_storage(repo,tmp_path/'RESULT.json')
    assert report['status']=='complete' and report['cleanup']['removed_copies']==2
    assert not old.exists() and not recovery.exists() and recent.exists()
    assert {p:p.read_bytes() for p in before}==before
    again=cleanup.clean_storage(repo,tmp_path/'RESULT.json')
    assert again['cleanup']['removed_copies']==0
    assert all(not v['created'] for v in again['current_backups'].values())
    # Reproduce 49h passing; new daily verified replacements must precede removal.
    future=time.time()+49*3600
    current={role:backup.ensure_backup(path,role=role,now=future) for role,path in [('paper',paper),('journal',journal)]}
    result=cleanup.retire_queued(paper.parent,current,now=future)
    assert result['removed_copies']==1 and not recent.exists()
    assert evidence.exists()


def test_running_or_unknown_process_state_never_starts_copy_or_delete(tmp_path,monkeypatch):
    repo,paper,journal,old,*_=legacy_fixture(tmp_path)
    for state in ({'status':'read','items':[{'role':'paper'}]}, {'status':'read_failed','items':[]}):
        monkeypatch.setattr(cleanup,'_processes',lambda *a,**k:state)
        with pytest.raises(ValueError,match='Close RUN_REVIEW'):
            cleanup.clean_storage(repo,tmp_path/'RESULT.json')
        assert old.exists() and not (paper.parent/backup.FOLDER).exists()


def test_active_wal_links_future_dates_and_changed_plan_refuse_removal(tmp_path):
    repo,paper,journal,old,*_=legacy_fixture(tmp_path)
    current={'journal':backup.ensure_backup(journal,role='journal')}
    plan=cleanup.inventory(paper.parent)
    entry=next(i for i in plan['candidates'] if i['role']=='journal')
    wal=Path(str(old)+'-wal');wal.write_bytes(b'active')
    age(wal,time.time()-4*backup.INTERVAL)
    assert not any(i['database']==str(old) for i in cleanup.inventory(paper.parent)['candidates'])
    with pytest.raises(ValueError,match='file set changed'):
        cleanup.apply_candidates({'candidates':[entry]},current)
    assert old.exists()
    wal.unlink();age(old,time.time()+1)
    assert not any(i['database']==str(old) for i in cleanup.inventory(paper.parent)['candidates'])
    old.unlink();old.symlink_to(journal)
    assert not any(i['database']==str(old) for i in cleanup.inventory(paper.parent)['candidates'])
    assert journal.exists()


def test_worker_restart_reuses_daily_copies_and_records_real_status(tmp_path):
    database(tmp_path/'auto_demo.sqlite3','strategy_lab_trades')
    database(tmp_path/'crypto_trader.sqlite3')
    first=cycle(tmp_path);second=cycle(tmp_path)
    assert all(v['created'] for v in first['databases'].values())
    assert all(v['status']=='verified' and not v['created'] for v in second['databases'].values())
    assert len(list((tmp_path/backup.FOLDER).iterdir()))==2
