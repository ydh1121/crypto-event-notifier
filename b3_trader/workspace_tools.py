"""Stable user entrypoints. No Git update, installation or automatic restart."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from .runtime_process_contract import RECOVERY_ENV
from .runtime_review import _processes
from .workspace_packages import cleanup_old_packages, verified_manifest

DEFAULT_REPO = Path(r'C:\Users\Administrator\Desktop\crypto-event-notifier-live')
ROOT = Path(__file__).resolve().parents[1]


def start_collection(repo: Path) -> int:
    repo = repo.resolve()
    python = repo/'.venv'/'Scripts'/'python.exe'
    if not all(p.is_file() for p in (python, repo/'b3_trader/local_process_host.py',
                                    repo/'b3_trader/data/auto_demo.sqlite3')):
        raise ValueError('Existing project Python, collector or database was not found.')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True,
                                       stderr=subprocess.DEVNULL, timeout=15).strip()
    if Path(git('rev-parse', '--show-toplevel')).resolve() != repo:
        raise ValueError('The configured path is not the existing project root.')
    if git('status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Tracked project files have local edits; collector was not started.')
    state = _processes(repo)
    if state.get('status') != 'read':
        raise ValueError('Process state could not be verified; collector was not started.')
    if state.get('items'):
        raise ValueError('A collector is already running or its ownership is unresolved. Keep its window open.')
    print('COLLECTION: '+str(repo), flush=True)
    print('SOURCE: '+git('rev-parse', 'HEAD'), flush=True)
    print('Keep this window open. Ctrl+C stops this collection session.', flush=True)
    # Existing checkout and recovery allowlist own collection semantics. The
    # viewer package never supplies or copies collector code into this checkout.
    process = subprocess.Popen([str(python), '-B', '-m', 'b3_trader.local_process_host', '--recovery'],
                               cwd=repo, env={**os.environ, **RECOVERY_ENV})
    while True:
        try:
            return process.wait()
        except KeyboardInterrupt:
            # Both processes receive the same console Ctrl+C. Let the existing
            # host finish its child cleanup instead of killing it after a timeout.
            print('Waiting for the collector to finish stopping...', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start-collection', 'clean-old-folders'))
    parser.add_argument('--repo', type=Path, default=DEFAULT_REPO)
    parser.add_argument('--scan-root', type=Path, action='append')
    args = parser.parse_args()
    try:
        manifest = verified_manifest(ROOT)
        if manifest.get('layout') != 'fixed_workspace_v1':
            raise ValueError('Use the complete CRYPTO folder from the current package.')
        if args.action == 'start-collection':
            return start_collection(args.repo)
        roots = args.scan_root or [ROOT.parent, args.repo.parent, Path.home()/'Downloads']
        result = cleanup_old_packages(ROOT, args.repo, roots,
                                      lambda: _processes(args.repo, include_review=True))
        # Replace the receipt itself; never follow an existing output symlink.
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=ROOT, delete=False) as out:
            json.dump(result, out, indent=2, ensure_ascii=False)
            receipt = Path(out.name)
        try:
            receipt.replace(ROOT/'CLEANUP_RESULT.json')
        finally:
            receipt.unlink(missing_ok=True)
        for row in result:
            print(row['status'].upper()+': '+row['folder']+' '+row.get('reason', ''), flush=True)
        print('Saved results: '+str(ROOT/'reports'/'previous'), flush=True)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print('Not started: '+str(exc), flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
