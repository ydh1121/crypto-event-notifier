from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import threading

import pytest

from b3_trader import paper_recovery as recovery
from b3_trader import research_supervisor as research
from b3_trader.auto_demo_v2 import AutoPaperDemo
from b3_trader.local_process_host import LocalProcessHost
from b3_trader.research_control import default_control, COMPONENT_DEFINITIONS
from b3_trader.runtime_process_contract import RECOVERY_COMPONENTS, RECOVERY_ROLES


def make_db(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute('PRAGMA journal_mode=WAL')
    for table in recovery.BACKUP_TABLES:
        db.execute(f'CREATE TABLE {table}(id INTEGER PRIMARY KEY, value REAL)')
        db.executemany(f'INSERT INTO {table}(value) VALUES(?)', [(0,), (13.5,), (-4.25,)])
    db.commit()
    return db


def test_backup_includes_wal_and_does_not_change_source(tmp_path):
    path = tmp_path/'original.sqlite3'
    with make_db(path) as source:
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (path, Path(str(path)+'-wal'))}
        result = recovery.backup_database(path, tmp_path/'backup')
        assert result['quick_check'] == 'ok'
        assert all(v == 3 for v in result['ledger_counts'].values())
        with sqlite3.connect(result['path']) as copied:
            assert copied.execute('SELECT value FROM strategy_lab_trades ORDER BY id').fetchall() == [(0,), (13.5,), (-4.25,)]
        assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (path, Path(str(path)+'-wal'))}
    source.close()


def test_backup_never_creates_missing_source_or_overwrites_destination(tmp_path):
    missing = tmp_path/'missing.sqlite3'
    with pytest.raises(recovery.RecoveryBlocked, match='existing_database_missing'):
        recovery.backup_database(missing, tmp_path/'backup')
    assert not missing.exists()
    db = make_db(missing); db.close()
    destination = tmp_path/'already'; destination.mkdir()
    (destination/'auto_demo.sqlite3').write_bytes(b'keep me')
    with pytest.raises(FileExistsError):
        recovery.backup_database(missing, destination)
    assert (destination/'auto_demo.sqlite3').read_bytes() == b'keep me'


def test_event_backup_checks_existing_rows_and_does_not_create_absent_archive(tmp_path):
    path = tmp_path/'events.sqlite3'; source = make_db(path)
    for table in recovery.EVENT_BACKUP_TABLES[:2]:
        source.execute(f'CREATE TABLE {table}(id INTEGER PRIMARY KEY)')
        source.execute(f'INSERT INTO {table} VALUES(1)')
    source.commit()
    result = recovery.backup_database(path,tmp_path/'backup')
    assert result['event_counts'] == {t: 1 for t in recovery.EVENT_BACKUP_TABLES[:2]}
    assert source.execute("SELECT name FROM sqlite_master WHERE name=?",
                          (recovery.EVENT_BACKUP_TABLES[2],)).fetchone() is None
    with sqlite3.connect(result['path']) as copied:
        assert copied.execute('SELECT id FROM research_intelligence_event_responses').fetchall() == [(1,)]
    source.close()


def test_low_disk_space_leaves_existing_db_intact(tmp_path, monkeypatch):
    path = tmp_path/'original.sqlite3'; db = make_db(path); db.close()
    before = path.read_bytes()
    class Disk: free = 0
    monkeypatch.setattr(recovery.shutil, 'disk_usage', lambda _: Disk())
    with pytest.raises(recovery.RecoveryBlocked, match='insufficient_backup_space'):
        recovery.backup_database(path, tmp_path/'backup')
    assert path.read_bytes() == before
    assert not (tmp_path/'backup/auto_demo.sqlite3').exists()


def test_bundle_requires_exact_pinned_file_bytes(tmp_path):
    path = tmp_path/'code.py'; path.write_text('original')
    manifest = {'source_commit':'a'*40, 'mode':'collection_recovery',
                'files':{'code.py':hashlib.sha256(path.read_bytes()).hexdigest()}}
    (tmp_path/'SOURCE_MANIFEST.json').write_text(json.dumps(manifest))
    assert recovery.verify_bundle(tmp_path) == 'a'*40
    path.write_text('modified')
    with pytest.raises(recovery.RecoveryBlocked, match='bundle_file_mismatch'):
        recovery.verify_bundle(tmp_path)


@pytest.mark.parametrize('observation', [
    {'status':'read_failed','items':[]}, {'status':'partial_read','items':[]},
    {'status':'read','items':[{'role':'paper','pid':123,'scope':'unresolved_checkout'}]},
    {'status':'read','items':[{'role':'host','pid':os.getppid(),'scope':'checkout'}]},
])
def test_process_uncertainty_and_existing_runners_block_recovery(tmp_path, monkeypatch, observation):
    monkeypatch.setattr(recovery, '_processes', lambda _: observation)
    with pytest.raises(recovery.RecoveryBlocked):
        recovery.require_stopped(tmp_path)


def test_only_current_recovery_and_its_redirector_are_ignored(tmp_path, monkeypatch):
    processes = {'status':'read','items':[{'role':'recovery','pid':os.getpid()}, {'role':'recovery','pid':os.getppid()}]}
    monkeypatch.setattr(recovery, '_processes', lambda _: processes)
    assert recovery.require_stopped(tmp_path)['items'] == []
    processes['items'].append({'role':'recovery','pid':999999})
    with pytest.raises(recovery.RecoveryBlocked): recovery.require_stopped(tmp_path)


def test_recovery_host_excludes_mutations_and_keeps_safety_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('LIVE_TRADING_ENABLED', 'true')
    monkeypatch.setenv('AUTO_GIT_SYNC', 'true')
    host = LocalProcessHost(tmp_path, recovery=True)
    assert set(host.commands) == RECOVERY_ROLES
    assert host.commands['research'][-1] == '--recovery'
    assert host.child_env['LIVE_TRADING_ENABLED'] == 'false'
    assert host.child_env['AUTO_GIT_SYNC'] == 'false'
    assert host.child_env['TELEGRAM_ENABLED'] == 'false'
    with pytest.raises(ValueError): LocalProcessHost(tmp_path, recovery=True, commands={'app':[]})


def test_research_recovery_never_constructs_publishers_and_control_cannot_enable_them(monkeypatch):
    class Allowed:
        def export_once(self): return {}
        def run_once(self): return {}
        def close(self): pass
    def forbidden(): raise AssertionError('Disallowed recovery service constructed')
    for name in ('ResearchWarehouse','MarketNoticeCollector','UpbitPaperResearchRunner','ConfiguredStrategyLabRunner'):
        monkeypatch.setattr(research, name, Allowed)
    for name in ('ReferenceComponentWatcher','CloudflareSnapshotPublisher','CloudflareMarketDetailPublisher','CoinProfileResearchCycleV36','CloudflarePagesDeployer'):
        monkeypatch.setattr(research, name, forbidden)
    control = default_control()
    control['components']['market-ohlcv-history']['enabled'] = False
    original = deepcopy(control)
    monkeypatch.setattr(research, 'load_control', lambda: control)
    monkeypatch.setattr(research, 'load_dotenv', lambda: None)
    monkeypatch.setattr(research, '_log', lambda _: None)
    supervisor = research.ResearchSupervisor(recovery=True)
    assert set(supervisor.runners) == RECOVERY_COMPONENTS
    assert control == original
    assert not supervisor.states['market-ohlcv-history'].enabled
    control = deepcopy(control); control['revision'] = int(control['revision']) + 1
    for name in COMPONENT_DEFINITIONS:
        control['components'][name].update(enabled=True, run_nonce=1)
    supervisor._apply_control()
    for name in COMPONENT_DEFINITIONS:
        assert supervisor.states[name].enabled is (name in RECOVERY_COMPONENTS)
    control = deepcopy(control); control['revision'] += 1; control['enabled'] = False
    supervisor._apply_control()
    assert not any(state.enabled for state in supervisor.states.values())


def test_initial_status_permission_error_closes_paper_store():
    class Store:
        closed = False
        def close(self): self.closed = True
    demo = AutoPaperDemo.__new__(AutoPaperDemo)
    demo.store = Store()
    def fail(**_): raise PermissionError('fixture')
    demo._write_status = fail
    with pytest.raises(PermissionError): demo.run()
    assert demo.store.closed


def init_repo(root):
    root.mkdir()
    def command(*args):
        return subprocess.check_output(['git', *args], cwd=root, text=True).strip()
    command('init','-q','-b','original')
    command('config','user.email','fixture@example.invalid')
    command('config','user.name','Fixture')
    (root/'.gitignore').write_text('b3_trader/data/\n.venv/\n')
    (root/'source').write_text('original')
    command('add','.'); command('commit','-qm','fixture')
    return command


def test_clean_preflight_preserves_dirty_work_and_detects_head_change(tmp_path):
    root = tmp_path/'repo'; command = init_repo(root)
    head = recovery.require_clean(root)
    (root/'source').write_text('unfinished user work')
    with pytest.raises(recovery.RecoveryBlocked, match='local_changes'): recovery.require_clean(root)
    assert (root/'source').read_text() == 'unfinished user work'
    command('add','.'); command('commit','-qm','newer')
    with pytest.raises(recovery.RecoveryBlocked, match='changed_during'): recovery.require_clean(root, head)


@pytest.mark.parametrize('backup_fails', [False, True])
def test_recovery_activates_only_after_verified_backup(tmp_path, monkeypatch, backup_fails):
    root=tmp_path/'repo'; command=init_repo(root); original=command('rev-parse','HEAD')
    (root/'source').write_text('pinned'); command('add','.');command('commit','-qm','pinned')
    pinned=command('rev-parse','HEAD'); command('switch','-q','-c','runtime',original)
    db=make_db(root/recovery.DB_RELATIVE); db.close()
    package=tmp_path/'package'; package.mkdir(); output=package/'result.json'
    monkeypatch.setattr(recovery,'verify_bundle',lambda _:pinned)
    monkeypatch.setattr(recovery,'verify_dependencies',lambda _:None)
    monkeypatch.setattr(recovery,'fetch_source',lambda *_:None)
    monkeypatch.setattr(recovery.sys,'executable',str(root/'.venv/Scripts/python.exe'))
    monkeypatch.setattr(recovery,'_processes',lambda _: {'status':'read','items':[]})
    monkeypatch.setattr(recovery,'read_runtime',lambda _: {'activity':{}})
    calls=[]; actual_backup=recovery.backup_database
    def backup(*args):
        assert command('rev-parse','HEAD') == original
        calls.append('backup')
        if backup_fails: raise recovery.RecoveryBlocked('backup_readback_failed')
        return actual_backup(*args)
    monkeypatch.setattr(recovery,'backup_database',backup)
    class Host:
        def __init__(self, checkout, *, recovery):
            assert recovery is True and checkout == root
            assert calls == ['backup'] and command('rev-parse','HEAD') == pinned
            self.stop_event=threading.Event(); self.stop_reason='fixture_stop'
        def run(self): calls.append('collectors'); return 0
    monkeypatch.setattr(recovery,'LocalProcessHost',Host)
    assert recovery.recover(root,package,output,seconds=60) == (2 if backup_fails else 0)
    result=json.loads(output.read_text())
    assert command('rev-parse','runtime') == original
    assert calls == (['backup'] if backup_fails else ['backup','collectors'])
    assert command('rev-parse','HEAD') == (original if backup_fails else pinned)
    assert result['status'] == ('blocked' if backup_fails else 'stopped')
