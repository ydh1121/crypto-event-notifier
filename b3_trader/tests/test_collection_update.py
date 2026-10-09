import subprocess

import pytest

from b3_trader import collection_update as update


def git(repo,*args):
    return subprocess.check_output(['git','-C',str(repo),*args],text=True,stderr=subprocess.DEVNULL).strip()


@pytest.fixture
def checkout(tmp_path,monkeypatch):
    repo=tmp_path/'repo'; repo.mkdir()
    git(repo,'init','-b',update.BRANCH)
    git(repo,'config','user.name','Fixture');git(repo,'config','user.email','fixture@example.test')
    git(repo,'config','commit.gpgsign','false')
    for name,content in (('.gitignore','.venv/\nb3_trader/data/\n.env\n'),('b3_trader/local_process_host.py','existing')):
        file=repo/name; file.parent.mkdir(parents=True,exist_ok=True);file.write_text(content)
    git(repo,'add','.');git(repo,'commit','-m','base')
    base=git(repo,'rev-parse','HEAD')
    for name in ('.venv/Scripts/python.exe','b3_trader/data/auto_demo.sqlite3','.env'):
        file=repo/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('existing user data')
    (repo/'b3_trader/fix.py').write_text('new collector')
    git(repo,'add','.');git(repo,'commit','-m','fix')
    target=git(repo,'rev-parse','HEAD')
    git(repo,'branch','fixture-published',target)
    git(repo,'reset','--hard',base)  # Isolated fixture only; updater never resets.
    git(repo,'remote','add','origin','https://github.com/ydh1121/crypto-event-notifier.git')
    original=update._git
    calls=[]
    def local_git(path,*args):
        calls.append(args)
        if args[0]=='fetch':
            return git(path,'fetch','--no-tags',str(repo),'refs/heads/fixture-published')
        return original(path,*args)
    monkeypatch.setattr(update,'_git',local_git)
    monkeypatch.setattr(update,'_processes',lambda *a,**kw:{'status':'read','items':[]})
    return repo,base,target,calls


def test_update_pins_package_revision_even_when_remote_has_newer_docs_and_preserves_data(checkout):
    repo,base,target,calls=checkout
    git(repo,'checkout','fixture-published')
    (repo/'HANDOFF.md').write_text('newer docs')
    git(repo,'add','.');git(repo,'commit','-m','docs')
    git(repo,'checkout',update.BRANCH)
    update.update_collection(repo,target)
    assert git(repo,'rev-parse','HEAD')==target
    assert (repo/'b3_trader/fix.py').read_text()=='new collector'
    assert not (repo/'HANDOFF.md').exists()
    assert (repo/'b3_trader/data/auto_demo.sqlite3').read_text()=='existing user data'
    assert (repo/'.env').read_text()=='existing user data'
    assert not any(c[0] in {'reset','checkout','clean','config'} for c in calls)
    calls.clear();update.update_collection(repo,target)
    assert not any(c[0] in {'fetch','merge'} for c in calls)


@pytest.mark.parametrize('problem',['running','unknown','dirty','wrong_branch','wrong_origin','diverged','backward','changed_during_fetch'])
def test_unsafe_update_stops_without_overwriting_checkout(checkout,monkeypatch,problem):
    repo,base,target,calls=checkout
    if problem in {'running','unknown'}:
        monkeypatch.setattr(update,'_processes',lambda *a,**kw:{'status':'read' if problem=='running' else 'partial_read',
                                                              'items':[{'role':'paper'}] if problem=='running' else []})
    elif problem=='dirty': (repo/'b3_trader/local_process_host.py').write_text('user edit')
    elif problem=='wrong_branch': git(repo,'checkout','-b','unrelated-work')
    elif problem=='wrong_origin': git(repo,'remote','set-url','origin','https://example.test/other.git')
    elif problem=='diverged':
        (repo/'own.txt').write_text('own change');git(repo,'add','.');git(repo,'commit','-m','own')
    elif problem=='backward':
        git(repo,'merge','--ff-only',target);target=base
    elif problem=='changed_during_fetch':
        original=update._git
        def mutate(path,*args):
            result=original(path,*args)
            if args[0]=='fetch': (repo/'b3_trader/local_process_host.py').write_text('concurrent edit')
            return result
        monkeypatch.setattr(update,'_git',mutate)
    before=git(repo,'rev-parse','HEAD')
    with pytest.raises(ValueError): update.update_collection(repo,target)
    assert git(repo,'rev-parse','HEAD')==before
    assert (repo/'b3_trader/data/auto_demo.sqlite3').read_text()=='existing user data'
    assert not any(c[0]=='merge' for c in calls)


@pytest.mark.parametrize('existing_recovery',[True,False])
def test_primary_checkout_switches_to_verified_recovery_preserving_primary(checkout,existing_recovery):
    repo,base,target,calls=checkout
    git(repo,'switch','-c',update.PRIMARY_BRANCH)
    if not existing_recovery:git(repo,'branch','-d',update.BRANCH)
    update.update_collection(repo,target)
    assert git(repo,'symbolic-ref','--short','HEAD')==update.BRANCH
    assert git(repo,'rev-parse',update.PRIMARY_BRANCH)==base
    assert git(repo,'rev-parse','HEAD')==target
    assert (repo/'b3_trader/data/auto_demo.sqlite3').read_text()=='existing user data'
    assert (repo/'.env').read_text()=='existing user data'
    assert not any(c[0] in {'reset','clean'} for c in calls)


@pytest.mark.parametrize('diverged', [False, True])
def test_generated_paper_recovery_branch_is_preserved_and_requires_ancestry(checkout, diverged):
    repo, base, target, calls = checkout
    branch = 'recovery/paper-20260924-110445-3a82105c'
    git(repo, 'switch', '-c', branch)
    if diverged:
        (repo/'user.txt').write_text('user work')
        git(repo, 'add', '.'); git(repo, 'commit', '-m', 'own work')
    before = git(repo, 'rev-parse', 'HEAD')
    if diverged:
        with pytest.raises(ValueError): update.update_collection(repo, target)
        assert git(repo, 'symbolic-ref', '--short', 'HEAD') == branch
    else:
        update.update_collection(repo, target)
        assert git(repo, 'symbolic-ref', '--short', 'HEAD') == update.BRANCH
        assert git(repo, 'rev-parse', 'HEAD') == target
    assert git(repo, 'rev-parse', branch) == before
    assert (repo/'b3_trader/data/auto_demo.sqlite3').read_text() == 'existing user data'


@pytest.mark.parametrize('start_primary', [False, True])
def test_published_docs_ahead_of_package_are_preserved(checkout, start_primary):
    repo, base, target, calls = checkout
    git(repo, 'switch', 'fixture-published')
    (repo/'HANDOFF.md').write_text('newer handoff')
    git(repo, 'add', '.'); git(repo, 'commit', '-m', 'docs')
    docs = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'switch', update.BRANCH)
    git(repo, 'merge', '--ff-only', docs)
    if start_primary:
        git(repo, 'switch', '-c', update.PRIMARY_BRANCH, base)
    update.update_collection(repo, target)
    assert git(repo, 'rev-parse', 'HEAD') == docs
    assert git(repo, 'symbolic-ref', '--short', 'HEAD') == update.BRANCH
    assert (repo/'HANDOFF.md').read_text() == 'newer handoff'
    if start_primary:
        assert git(repo, 'rev-parse', update.PRIMARY_BRANCH) == base
    assert (repo/'b3_trader/data/auto_demo.sqlite3').read_text() == 'existing user data'
    assert not any(c[0] in {'reset', 'clean', 'checkout'} for c in calls)


def test_newer_collector_code_is_not_accepted_as_docs(checkout):
    repo, base, target, calls = checkout
    git(repo, 'switch', 'fixture-published')
    (repo/'b3_trader/fix.py').write_text('different runtime')
    git(repo, 'add', '.'); git(repo, 'commit', '-m', 'new runtime')
    newer = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'switch', update.BRANCH); git(repo, 'merge', '--ff-only', newer)
    with pytest.raises(ValueError, match='newer collector code'):
        update.update_collection(repo, target)
    assert git(repo, 'rev-parse', 'HEAD') == newer
    assert not any(c[0] == 'merge' for c in calls)


def test_shallow_history_is_deepened_without_reset(checkout, tmp_path, monkeypatch):
    remote, base, target, calls = checkout
    git(remote, 'switch', 'fixture-published')
    (remote/'HANDOFF.md').write_text('published docs')
    git(remote, 'add', '.'); git(remote, 'commit', '-m', 'docs')
    docs = git(remote, 'rev-parse', 'HEAD')
    local = tmp_path/'shallow'
    subprocess.run(['git','clone','--depth=1','--branch','fixture-published',remote.as_uri(),str(local)],
                   check=True, capture_output=True)
    git(local, 'switch', '-c', update.BRANCH)
    git(local, 'remote', 'set-url', 'origin', 'https://github.com/ydh1121/crypto-event-notifier.git')
    for name in ('.venv/Scripts/python.exe', 'b3_trader/data/auto_demo.sqlite3'):
        p=local/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('existing user data')
    original=update._git
    def fetch_local(path, *args):
        if args[0] == 'fetch':
            calls.append(args)
            return git(path, 'fetch', *[x for x in args[1:] if x.startswith('--')],
                       remote.as_uri(), 'refs/heads/fixture-published')
        return original(path, *args)
    monkeypatch.setattr(update, '_git', fetch_local)
    assert git(local, 'rev-parse', '--is-shallow-repository') == 'true'
    update.update_collection(local, target)
    assert git(local, 'rev-parse', 'HEAD') == docs
    assert any('--deepen=256' in c for c in calls)
    assert not any(c[0] in {'reset','clean','checkout'} for c in calls)
    assert (local/'b3_trader/data/auto_demo.sqlite3').read_text() == 'existing user data'


def test_unpublished_document_commits_are_not_silently_accepted(checkout):
    repo, base, target, calls = checkout
    git(repo, 'merge', '--ff-only', target)
    (repo/'HANDOFF.md').write_text('unpublished user notes')
    git(repo, 'add', '.');git(repo, 'commit', '-m', 'private docs')
    before = git(repo, 'rev-parse', 'HEAD')
    with pytest.raises(ValueError, match='unpublished commits'):
        update.update_collection(repo, target)
    assert git(repo, 'rev-parse', 'HEAD') == before
    assert (repo/'HANDOFF.md').read_text() == 'unpublished user notes'
    assert not any(c[0] == 'merge' for c in calls)
