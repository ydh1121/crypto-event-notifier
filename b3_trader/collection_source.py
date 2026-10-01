"""Read-only collector source evidence, separate from the viewer package."""
import subprocess


MIN_COLLECTION_SOURCE = '8d9c97b75d550e758c3a63ada14a823b4d0be5e2'


def read_collection_source(root):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True,
                                       stderr=subprocess.DEVNULL, timeout=10).strip()
    try:
        head, branch = git('rev-parse', 'HEAD'), git('symbolic-ref', '--short', 'HEAD')
        dirty = bool(git('status', '--porcelain', '--untracked-files=no'))
        try:
            git('merge-base', '--is-ancestor', MIN_COLLECTION_SOURCE, 'HEAD')
            ready = True
        except subprocess.CalledProcessError:
            ready = False
        return {'status': 'read', 'head': head, 'branch': branch, 'tracked_changes': dirty,
                'contains_subscription_fix': ready, 'minimum_source': MIN_COLLECTION_SOURCE}
    except (OSError, subprocess.SubprocessError):
        return {'status': 'unavailable'}
