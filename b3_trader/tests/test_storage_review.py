import os
import sqlite3
import time

from b3_trader.storage_review import database_info, folder_info, read_storage


def test_readonly_inventory_preserves_database_backups_archives_and_unknown_files(tmp_path):
    db = tmp_path/'auto_demo.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE strategy_lab_trades(id INTEGER PRIMARY KEY, reason TEXT)')
        conn.execute("INSERT INTO strategy_lab_trades VALUES(1,'preserve')")
    folder = tmp_path/'recovery-backups'/'20260924-110445-3a82105c'
    folder.mkdir(parents=True)
    old = folder/'auto_demo.sqlite3'; old.write_bytes(db.read_bytes())
    os.utime(old, (time.time()-3*86400,)*2)
    (folder/'unknown.txt').write_text('keep')
    warehouse = tmp_path/'research-warehouse'; warehouse.mkdir()
    (warehouse/'learning.parquet').write_bytes(b'precious')
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = read_storage(db)
    assert result['cleanup_applied'] is False
    assert result['paper']['allocated_bytes'] == db.stat().st_size
    assert result['paper']['tables'] == ['strategy_lab_trades']
    backups = next(f for f in result['folders'] if f['name']=='recovery-backups')
    assert backups['files_older_than_48h'] == 1
    assert backups['bytes_older_than_48h'] == old.stat().st_size
    assert backups['listed_all_files']
    assert {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before


def test_missing_db_does_not_create_it_and_links_are_not_followed(tmp_path):
    missing = tmp_path/'missing.sqlite3'
    assert database_info(missing)['status']=='unavailable'
    assert not missing.exists()
    real = tmp_path/'real'; real.mkdir(); (real/'private').write_text('stay')
    linked = tmp_path/'backups'; linked.symlink_to(real, target_is_directory=True)
    assert folder_info(linked, deadline=time.monotonic()+1, now=time.time())['status']=='linked_path_skipped'
    regular = tmp_path/'ordinary'; regular.mkdir(); (regular/'link').symlink_to(real, target_is_directory=True)
    read = folder_info(regular, deadline=time.monotonic()+1, now=time.time())
    assert read['skipped_links']==1 and read['files']==0
    (regular/'a').write_text('a')
    limited = folder_info(regular, deadline=0, now=time.time())
    assert limited['status']=='partial_limit'
