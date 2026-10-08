import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from b3_trader import runtime_review, workspace_tools as tools
from b3_trader.workspace_packages import verified_manifest


@pytest.fixture
def collector(tmp_path, monkeypatch):
    for name in ('.venv/Scripts/python.exe', 'b3_trader/local_process_host.py', 'b3_trader/data/auto_demo.sqlite3'):
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('existing')
    calls = []
    def git(args, **kwargs):
        calls.append(args)
        return {('rev-parse', '--show-toplevel'): str(tmp_path),
                ('status', '--porcelain', '--untracked-files=no'): '',
                ('rev-parse', 'HEAD'): 'a'*40}[tuple(args[3:])]
    monkeypatch.setattr(tools.subprocess, 'check_output', git)
    monkeypatch.setattr(tools, '_processes', lambda _: {'status': 'read', 'items': []})
    def unexpected_start(*args, **kwargs):
        raise AssertionError('must not start')
    monkeypatch.setattr(tools.subprocess, 'Popen', unexpected_start)
    return tmp_path, calls


def test_start_existing_canonical_host_and_wait_for_clean_ctrl_c_stop(collector, monkeypatch):
    repo, git_calls = collector
    starts, waits = [], []
    def wait():
        waits.append(1)
        if len(waits) == 1: raise KeyboardInterrupt
        return 0
    def start(command, **kwargs):
        receipt = json.loads((repo/'b3_trader/data/storage-wal-result.json').read_text())
        assert receipt['phase'] == 'before_collection_start'
        assert receipt['databases']['paper']['status'] == 'below_threshold'
        starts.append((command, kwargs))
        return SimpleNamespace(wait=wait)
    monkeypatch.setattr(tools.subprocess, 'Popen', start)
    assert tools.start_collection(repo, confirmed_exchange='bithumb') == 0
    command, kwargs = starts[0]
    assert command == [str(repo/'.venv/Scripts/python.exe'), '-B', '-m', 'b3_trader.local_process_host', '--recovery']
    assert kwargs['cwd'] == repo
    assert kwargs['env']['LIVE_TRADING_ENABLED'] == 'false'
    assert kwargs['env']['AUTO_GIT_SYNC'] == 'false'
    assert kwargs['env']['AUTO_GIT_PUSH_CONTROL'] == 'false'
    assert kwargs['env']['MARKET_FLOW_HOLDINGS_EXCHANGE'] == 'bithumb'
    assert len(starts) == 1 and len(waits) == 2
    assert {row[3] for row in git_calls} == {'rev-parse', 'status'}
    assert (repo/'b3_trader/data/auto_demo.sqlite3').read_text() == 'existing'


@pytest.mark.parametrize('problem', ['missing_db', 'dirty', 'wrong_root', 'unknown', 'running'])
def test_refuse_start_without_existing_clean_idle_project(collector, monkeypatch, problem):
    repo, calls = collector
    if problem == 'missing_db':
        (repo/'b3_trader/data/auto_demo.sqlite3').unlink()
    elif problem in {'dirty', 'wrong_root'}:
        original = tools.subprocess.check_output
        def git(args, **kwargs):
            if problem == 'dirty' and args[3] == 'status': return ' M user.py'
            if problem == 'wrong_root' and args[3:] == ['rev-parse', '--show-toplevel']: return str(repo.parent)
            return original(args, **kwargs)
        monkeypatch.setattr(tools.subprocess, 'check_output', git)
    else:
        state = {'status': 'partial_read', 'items': []} if problem == 'unknown' else {
            'status': 'read', 'items': [{'role': 'paper', 'scope': 'unresolved_checkout'}]}
        monkeypatch.setattr(tools, '_processes', lambda _: state)
    with pytest.raises(ValueError): tools.start_collection(repo)


def test_process_observation_includes_viewer_only_for_cleanup(tmp_path, monkeypatch):
    envs = []
    monkeypatch.setattr(runtime_review, 'os', SimpleNamespace(name='nt', environ={}))
    def run(*args, **kwargs):
        envs.append(json.loads(kwargs['env']['CRYPTO_REVIEW_PROCESS_ROLES']))
        return SimpleNamespace(returncode=0, stdout='{"status":"read","items":[]}')
    monkeypatch.setattr(runtime_review.subprocess, 'run', run)
    runtime_review._processes(tmp_path)
    runtime_review._processes(tmp_path, include_review=True)
    assert 'b3_trader.strategy_journal_review' not in envs[0]
    assert envs[1]['b3_trader.strategy_journal_review'] == 'review'


def test_two_revisions_overlay_one_folder_preserving_outputs_and_canonical_db(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('builder', root/'scripts/build-strategy-review.py')
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    revision = ['a'*40]
    monkeypatch.setattr(builder.subprocess, 'check_output', lambda args, **kw: '' if 'status' in args else revision[0])
    repo = tmp_path/'crypto-event-notifier-live'; repo.mkdir()
    db = repo/'auto_demo.sqlite3'; db.write_bytes(b'canonical')
    desktop = tmp_path/'Desktop'; desktop.mkdir()
    for head in ('a'*40, 'b'*40):
        revision[0] = head
        archive = tmp_path/'CRYPTO.zip'
        builder.build(archive, holdings_exchange='bithumb', enable_planning=True)
        with ZipFile(archive) as package:
            assert {Path(p).parts[0] for p in package.namelist()} == {'CRYPTO'}
            assert not any(Path(p).suffix in {'.sqlite3', '.db', '.env'} for p in package.namelist())
            package.extractall(desktop)
        workspace = desktop/'CRYPTO'
        manifest = verified_manifest(workspace)
        assert manifest['source_commit'] == head and manifest['layout'] == 'fixed_workspace_v1'
        assert manifest['confirmed_holdings_exchange'] == 'bithumb'
        assert '--enable-planning' in (workspace/'RUN_REVIEW.cmd').read_text()
        assert '--enable-planning' not in (workspace/'RUN_CHECK.cmd').read_text()
        check=(workspace/'RUN_CHECK.cmd').read_text()
        assert check.count('--expected-build '+head)==3
        assert 'explorer.exe /select,"%~dp0CRYPTO_CHECK_RESULT.json"' in check
        assert '@FULL_BUILD@' not in check and '@SUCCESS@' not in check
        assert 'update-collection' in (workspace/'UPDATE_COLLECTION.cmd').read_text()
        if head[0] == 'a':
            (workspace/'CRYPTO_B3_REVIEW_RESULT.json').write_text('actual result')
        else:
            assert (workspace/'CRYPTO_B3_REVIEW_RESULT.json').read_text() == 'actual result'
        assert db.read_bytes() == b'canonical'
    assert list(desktop.iterdir()) == [workspace]
    (workspace/'b3_trader/workspace_tools.py').write_text('mixed update')
    with pytest.raises(ValueError, match='modified_package'): verified_manifest(workspace)


def test_old_source_cannot_silently_start_after_viewer_update(collector,monkeypatch):
    import subprocess
    repo,_=collector
    original=tools.subprocess.check_output
    def git(args,**kw):
        if args[3]=='merge-base':raise subprocess.CalledProcessError(1,args)
        return original(args,**kw)
    monkeypatch.setattr(tools.subprocess,'check_output',git)
    with pytest.raises(ValueError,match='UPDATE_COLLECTION'):
        tools.start_collection(repo,minimum_source='b'*40)


def test_packaged_start_requires_this_build_not_only_the_old_subscription_fix(collector,monkeypatch):
    repo,_=collector
    monkeypatch.setattr(tools,'verified_manifest',lambda _: {'layout':'fixed_workspace_v1',
        'source_commit':'c'*40,'confirmed_holdings_exchange':'bithumb'})
    monkeypatch.setattr('sys.argv',['tools','start-collection','--repo',str(repo)])
    observed=[]
    monkeypatch.setattr(tools,'start_collection',lambda *args,**kwargs:observed.append(kwargs) or 0)
    assert tools.main() == 0
    assert observed[0]['minimum_source'] == 'c'*40
