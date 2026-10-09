"""Explicit fast-forward of an idle existing collector checkout, never a reset."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

from .runtime_review import _processes

BRANCH = 'agent/crypto-product-data-recovery-20260921'
PRIMARY_BRANCH = 'b3-auto-trader-phase1'


class _GitFailure(ValueError):
    def __init__(self, command, returncode):
        self.returncode = returncode
        # Git stderr may contain a credential-bearing remote URL.
        super().__init__(f'Git {command} returned {returncode}. No reset or forced update was attempted.')


class _HistoryMismatch(ValueError):
    pass


def _git(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args], text=True,
                            capture_output=True, timeout=120,
                            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'})
    if result.returncode:
        raise _GitFailure(args[0], result.returncode)
    return result.stdout.strip()


def _ancestor(repo, older, newer):
    try:
        _git(repo, 'merge-base', '--is-ancestor', older, newer)
    except _GitFailure as exc:
        if exc.returncode == 1:
            return False  # A negative ancestry answer is not a Git command error.
        raise
    return True


def _documentation_only(repo, target, candidate):
    paths = _git(repo, 'diff', '--name-only', '--no-renames', '--no-ext-diff',
                 target, candidate, '--').splitlines()
    # Do not use a collector-file allowlist: an unknown runtime/config change
    # must also block accepting a newer checkout with an older tool package.
    return all(path.endswith('.md') and ('/' not in path or path.startswith('docs/'))
               for path in paths)


def _compatible_target(repo, before, target, published, recovery):
    if not _ancestor(repo, target, published):
        raise _HistoryMismatch('Package revision is not verified on the fetched recovery branch. Existing source was kept.')
    selected = target
    for label, head in (('Local checkout', before), ('Local recovery branch', recovery)):
        if not head or _ancestor(repo, head, selected):
            continue
        if not _ancestor(repo, selected, head):
            raise _HistoryMismatch(label+' has diverged from the package revision. Existing commits were kept.')
        if not _ancestor(repo, head, published):
            raise _HistoryMismatch(label+' has unpublished commits. Existing commits were kept.')
        if not _documentation_only(repo, target, head):
            raise ValueError(label+' contains newer collector code or configuration. Use the matching newer CRYPTO.zip; no downgrade was attempted.')
        selected = head
    return selected


def _resolve_target(repo, before, target, recovery):
    published = _git(repo, 'rev-parse', 'FETCH_HEAD')
    shallow = _git(repo, 'rev-parse', '--is-shallow-repository') == 'true'
    print('LOCAL SOURCE: '+before+'\nPACKAGE SOURCE: '+target+'\nFETCHED SOURCE: '+published+
          '\nHISTORY: '+('shallow' if shallow else 'complete'), flush=True)
    try:
        return _compatible_target(repo, before, target, published, recovery)
    except (_GitFailure, _HistoryMismatch):
        if not shallow:
            raise
    # Fetch ancestry only, once and with a bounded history size. No checkout,
    # reset, database copy, or unbounded unshallow operation is performed.
    print('FETCHING MISSING HISTORY (one bounded deepen: 256)...', flush=True)
    _git(repo, 'fetch', '--no-tags', '--deepen=256', 'origin', 'refs/heads/'+BRANCH)
    published = _git(repo, 'rev-parse', 'FETCH_HEAD')
    print('FETCHED SOURCE: '+published, flush=True)
    try:
        return _compatible_target(repo, before, target, published, recovery)
    except (_GitFailure, _HistoryMismatch) as exc:
        if _git(repo, 'rev-parse', '--is-shallow-repository') == 'true':
            raise ValueError('Git history is still incomplete after bounded history recovery. Existing source was kept; send the source versions printed above.') from exc
        raise


def _idle(repo):
    state = _processes(repo, include_review=True)
    if state.get('status') != 'read' or state.get('items'):
        raise ValueError('Close the review window and stop collection with Ctrl+C first. Wait for clean shutdown, then run UPDATE_COLLECTION.cmd again.')


def _clean(repo):
    if _git(repo, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Tracked files have local edits. The existing files were kept; update was not applied.')
    branch = _git(repo, 'symbolic-ref', '--short', 'HEAD')
    # Names emitted by paper_recovery.py. Ancestry is still verified after
    # fetching, before switching; unrelated or diverged work is never reset.
    if branch not in {BRANCH, PRIMARY_BRANCH} and not re.fullmatch(r'recovery/paper-\d{8}-\d{6}-[0-9a-f]{8}', branch):
        raise ValueError('Unrecognized working branch. Existing files and branches were kept.')
    return branch


def update_collection(repo: Path, target: str):
    if not re.fullmatch('[0-9a-f]{40}', str(target)):
        raise ValueError('A complete verified source revision is required.')
    repo = repo.resolve()
    if not all((repo/p).is_file() for p in ('.venv/Scripts/python.exe',
            'b3_trader/local_process_host.py', 'b3_trader/data/auto_demo.sqlite3')):
        raise ValueError('The existing project, Python and database must be kept.')
    if Path(_git(repo, 'rev-parse', '--show-toplevel')).resolve() != repo:
        raise ValueError('The configured folder is not the existing project root.')
    _idle(repo)
    branch = _clean(repo)
    before = _git(repo, 'rev-parse', 'HEAD')
    if before == target and branch == BRANCH:
        print('COLLECTION SOURCE ALREADY CURRENT: '+target, flush=True)
        return
    remote = _git(repo, 'remote', 'get-url', 'origin')
    if not re.fullmatch(r'(?:https://(?:[^/@]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)ydh1121/crypto-event-notifier(?:\.git)?/?', remote):
        raise ValueError('The existing origin is not the expected GitHub repository. Remote configuration was kept.')
    print('FETCHING COLLECTION UPDATE...', flush=True)
    _git(repo, 'fetch', '--no-tags', 'origin', 'refs/heads/'+BRANCH)
    recovery = _git(repo, 'for-each-ref', '--format=%(objectname)', 'refs/heads/'+BRANCH)
    # Keep package code pinned, but preserve already-applied published docs when
    # every non-document file is identical. Never move an existing branch back.
    selected = _resolve_target(repo, before, target, recovery)
    _idle(repo)
    if _clean(repo) != branch or _git(repo, 'rev-parse', 'HEAD') != before:
        raise ValueError('The checkout changed during update. Retry after other Git work finishes.')
    if branch != BRANCH:
        # Preserve the primary branch reference. Explicit UPDATE switches only to
        # the verified recovery line; no reset, primary merge or forced checkout.
        if _git(repo, 'for-each-ref', '--format=%(objectname)', 'refs/heads/'+BRANCH) != recovery:
            raise ValueError('The recovery branch changed during update. Retry after other Git work finishes.')
        _git(repo, 'switch', BRANCH) if recovery else _git(repo, 'switch', '-c', BRANCH, before)
        _clean(repo)
    if _git(repo, 'rev-parse', 'HEAD') != selected:
        _git(repo, 'merge', '--ff-only', selected)
    if _git(repo, 'rev-parse', 'HEAD') != selected:
        raise ValueError('Source revision verification failed; collection was not started.')
    _clean(repo)
    print('COLLECTION UPDATED: '+selected, flush=True)
    if selected != target:
        print('Package collector code matches; newer published documentation was preserved.', flush=True)
