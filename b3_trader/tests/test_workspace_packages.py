import json
from pathlib import Path

import pytest

from b3_trader import workspace_packages as packages


def bundle(path, mode='local_planning'):
    path.mkdir(parents=True)
    source = path/'b3_trader'/'strategy_journal_review.py'
    source.parent.mkdir()
    source.write_text('print("review")\n')
    manifest = {'source_commit': 'a'*40, 'mode': mode,
                'files': {'b3_trader/strategy_journal_review.py': packages.digest(source)}}
    (path/'SOURCE_MANIFEST.json').write_text(json.dumps(manifest))
    return path


def observation(*roles):
    return {'status': 'read', 'items': [{'role': role} for role in roles]}


@pytest.fixture
def layout(tmp_path):
    workspace = tmp_path/'CRYPTO'
    workspace.mkdir()
    repo = tmp_path/'crypto-event-notifier-live'
    repo.mkdir()
    (repo/'auto_demo.sqlite3').write_bytes(b'canonical database unchanged')
    return workspace, repo, tmp_path


@pytest.mark.parametrize('wrapped', [False, True])
def test_verified_tools_removed_and_exact_results_preserved(layout, wrapped):
    workspace, repo, root = layout
    old = root/'CRYPTO_STRATEGY_REVIEW_abcdef0'
    inner = bundle(old/'CRYPTO_STRATEGY_REVIEW_abcdef012345' if wrapped else old)
    receipt = b'{"result": "actual user evidence"}\n'
    (inner/'CRYPTO_B3_REVIEW_RESULT(3).json').write_bytes(receipt)
    before = packages.digest(repo/'auto_demo.sqlite3')
    result = packages.cleanup_old_packages(workspace, repo, [root, root], lambda: observation('paper'))
    assert len(result) == 1 and result[0]['status'] == 'removed'
    assert not old.exists()
    assert [p.read_bytes() for p in (workspace/'reports/previous').iterdir()] == [receipt]
    assert packages.digest(repo/'auto_demo.sqlite3') == before


@pytest.mark.parametrize('mode,roles,status', [
    ('local_planning', ('review',), 'kept'),
    ('read_only', ('review',), 'kept'),
    ('collection_recovery', ('recovery', 'paper'), 'kept'),
    ('collection_recovery', ('host', 'paper', 'market_flow'), 'removed'),
])
def test_running_package_preserved_but_canonical_host_does_not_use_old_code(layout, mode, roles, status):
    workspace, repo, root = layout
    old = bundle(root/'CRYPTO_PAPER_RECOVERY_abcdef0', mode)
    result = packages.cleanup_old_packages(workspace, repo, [root], lambda: observation(*roles))
    assert result[0]['status'] == status
    assert old.exists() == (status == 'kept')


@pytest.mark.parametrize('extra', ['data/auto_demo.sqlite3', 'user-notes.txt', '.git/config', 'empty/'])
def test_never_delete_unknown_user_material(layout, extra):
    workspace, repo, root = layout
    old = bundle(root/'CRYPTO_STRATEGY_REVIEW_abcdef0')
    target = old/extra
    if extra.endswith('/'):
        target.mkdir()
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('keep me')
    result = packages.cleanup_old_packages(workspace, repo, [root], lambda: observation())
    assert result[0]['status'] == 'kept' and target.exists()


@pytest.mark.parametrize('problem', ['modified', 'manifest_list', 'traversal', 'code_link', 'archive_link', 'unknown_processes'])
def test_unverified_packages_or_observations_are_preserved(layout, problem):
    workspace, repo, root = layout
    old = bundle(root/'CRYPTO_STRATEGY_REVIEW_abcdef0')
    source = old/'b3_trader/strategy_journal_review.py'
    manifest = old/'SOURCE_MANIFEST.json'
    state = observation()
    if problem == 'modified':
        source.write_text('user changes')
    elif problem == 'manifest_list':
        manifest.write_text('[]')
    elif problem == 'traversal':
        value = json.loads(manifest.read_text())
        value['files']['../private'] = 'a'*64
        manifest.write_text(json.dumps(value))
    elif problem == 'code_link':
        source.unlink()
        source.symlink_to(repo/'auto_demo.sqlite3')
    elif problem == 'archive_link':
        (workspace/'reports').symlink_to(repo, target_is_directory=True)
    else:
        state = {'status': 'partial_read', 'items': []}
    result = packages.cleanup_old_packages(workspace, repo, [root], lambda: state)
    assert result[0]['status'] == 'kept' and old.exists()
    assert not (repo/'previous').exists()


@pytest.mark.parametrize('protected', ['repo', 'workspace', 'repo_parent', 'workspace_parent'])
def test_protect_canonical_paths_even_when_named_like_old_package(tmp_path, protected):
    old = bundle(tmp_path/'CRYPTO_STRATEGY_REVIEW_abcdef0')
    repo, workspace = tmp_path/'repo', tmp_path/'CRYPTO'
    if protected == 'repo': repo = old
    if protected == 'workspace': workspace = old
    if protected == 'repo_parent': repo = old/'nested_repo'
    if protected == 'workspace_parent': workspace = old/'nested_workspace'
    result = packages.cleanup_old_packages(workspace, repo, [tmp_path], lambda: observation())
    assert result[0]['reason'] == 'protected_location' and old.exists()


@pytest.mark.parametrize('race', ['process', 'report', 'wrapper_file', 'manifest'])
def test_revalidate_after_rename_and_restore_on_concurrent_change(layout, monkeypatch, race):
    workspace, repo, root = layout
    old = root/'CRYPTO_STRATEGY_REVIEW_abcdef0'
    inner = bundle(old/'CRYPTO_STRATEGY_REVIEW_abcdef012345')
    report = inner/'CRYPTO_B3_REVIEW_RESULT.json'
    report.write_text('first result')
    calls = []
    def observe():
        calls.append(1)
        return observation('review') if race == 'process' and len(calls) > 1 else observation()
    rename = Path.rename
    def racing_rename(path, target):
        result = rename(path, target)
        if path == old:
            moved = target/inner.name
            if race == 'report':
                (moved/report.name).write_text('new result')
            elif race == 'wrapper_file':
                (target/'user-file.txt').write_text('new file')
            elif race == 'manifest':
                mf = moved/'SOURCE_MANIFEST.json'
                value = json.loads(mf.read_text()); value['source_commit'] = 'b'*40
                mf.write_text(json.dumps(value))
        return result
    monkeypatch.setattr(Path, 'rename', racing_rename)
    result = packages.cleanup_old_packages(workspace, repo, [root], observe)
    assert result[0]['status'] == 'kept' and old.exists()
    assert not list(root.glob('CRYPTO_CLEANUP_PENDING_*'))
    assert list((workspace/'reports/previous').iterdir())[0].read_text() == 'first result'
    if race == 'report': assert report.read_text() == 'new result'
    if race == 'wrapper_file': assert (old/'user-file.txt').exists()
