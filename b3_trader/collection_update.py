"""Explicit fast-forward of an idle existing collector checkout, never a reset."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

from .runtime_review import _processes

BRANCH = 'agent/crypto-product-data-recovery-20260921'


def _git(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args], text=True,
                            capture_output=True, timeout=120,
                            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'})
    if result.returncode:
        # Git stderr may include a credential-bearing remote URL.
        raise ValueError('Git '+args[0]+' failed. No reset or forced update was attempted.')
    return result.stdout.strip()


def _idle(repo):
    state = _processes(repo, include_review=True)
    if state.get('status') != 'read' or state.get('items'):
        raise ValueError('Close the review window and stop collection with Ctrl+C first. Wait for clean shutdown, then run UPDATE_COLLECTION.cmd again.')


def _clean(repo):
    if _git(repo, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Tracked files have local edits. The existing files were kept; update was not applied.')
    if _git(repo, 'symbolic-ref', '--short', 'HEAD') != BRANCH:
        raise ValueError('The checkout is not on the recovery branch. No branch was switched or merged.')


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
    _clean(repo)
    before = _git(repo, 'rev-parse', 'HEAD')
    if before == target:
        print('COLLECTION SOURCE ALREADY CURRENT: '+target, flush=True)
        return
    remote = _git(repo, 'remote', 'get-url', 'origin')
    if not re.fullmatch(r'(?:https://(?:[^/@]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)ydh1121/crypto-event-notifier(?:\.git)?/?', remote):
        raise ValueError('The existing origin is not the expected GitHub repository. Remote configuration was kept.')
    print('FETCHING COLLECTION UPDATE...', flush=True)
    _git(repo, 'fetch', '--no-tags', 'origin', 'refs/heads/'+BRANCH)
    # Pin to the package revision, even if newer documents/source were pushed.
    _git(repo, 'merge-base', '--is-ancestor', before, target)
    _git(repo, 'merge-base', '--is-ancestor', target, 'FETCH_HEAD')
    _idle(repo)
    _clean(repo)
    if _git(repo, 'rev-parse', 'HEAD') != before:
        raise ValueError('The checkout changed during update. Retry after other Git work finishes.')
    _git(repo, 'merge', '--ff-only', target)
    if _git(repo, 'rev-parse', 'HEAD') != target:
        raise ValueError('Source revision verification failed; collection was not started.')
    _clean(repo)
    print('COLLECTION UPDATED: '+target, flush=True)
