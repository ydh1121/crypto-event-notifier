"""Verify removable historical tool packages; never treat a checkout as one."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import uuid

LEGACY = re.compile(r'CRYPTO_(STRATEGY_REVIEW|PAPER_RECOVERY)_[0-9a-f]{7,40}')
REPORT = re.compile(r'CRYPTO_(B3_REVIEW|CHECK|RECOVERY)_RESULT(?:\(\d+\))?\.json')
ROOT_FILES = {'RUN_REVIEW.cmd', 'RUN_CHECK.cmd', 'RUN_RECOVERY.cmd', 'START_COLLECTION.cmd',
              'CLEAN_OLD_FOLDERS.cmd', 'README.txt', 'HELP.txt'}


def linked(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, 'st_file_attributes', 0) & 1024)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_manifest(folder: Path) -> dict:
    if linked(folder):
        raise ValueError('linked_folder')
    file = folder/'SOURCE_MANIFEST.json'
    if linked(file) or file.stat().st_size > 1024*1024:
        raise ValueError('unsafe_manifest')
    manifest = json.loads(file.read_text(encoding='utf-8'))
    if (not isinstance(manifest, dict)
            or not re.fullmatch(r'[0-9a-f]{40}', str(manifest.get('source_commit', '')))
            or manifest.get('mode') not in {'read_only', 'local_planning', 'collection_recovery'}):
        raise ValueError('unknown_package')
    files = manifest.get('files')
    if not isinstance(files, dict) or not 1 <= len(files) <= 500:
        raise ValueError('invalid_file_list')
    for name, checksum in files.items():
        p = PurePosixPath(name)
        if (p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name
                or p.as_posix() != name or not re.fullmatch(r'[0-9a-f]{64}', str(checksum))):
            raise ValueError('unsafe_manifest_path')
        code = len(p.parts) == 2 and p.parts[0] == 'b3_trader' and p.suffix == '.py'
        web = p.parts[:3] == ('cloudflare-pages', 'public', 'modules') and p.suffix in {'.js', '.css'}
        if not (code or web or name in ROOT_FILES):
            raise ValueError('not_a_tool_file')
        target = folder.joinpath(*p.parts)
        if any(linked(x) for x in (target, *list(target.parents)[:len(p.parts)-1])):
            raise ValueError('linked_package_file')
        if not target.is_file() or target.stat().st_size > 8*1024*1024 or digest(target) != checksum:
            raise ValueError('modified_package')
    return manifest


def legacy_contents(folder: Path, manifest: dict) -> list[Path]:
    allowed = set(manifest['files']) | {'SOURCE_MANIFEST.json'}
    directories = {str(p) for name in allowed for p in PurePosixPath(name).parents if str(p) != '.'}
    reports = []
    for parent, dirs, files in os.walk(folder, followlinks=False):
        for name in dirs:
            p = Path(parent)/name
            if linked(p) or p.relative_to(folder).as_posix() not in directories:
                raise ValueError('unmanaged_directory')
        for name in files:
            p = Path(parent)/name
            if linked(p):
                raise ValueError('linked_package_file')
            relative = p.relative_to(folder).as_posix()
            if relative in allowed:
                continue
            if p.parent == folder and REPORT.fullmatch(name):
                reports.append(p)
            else:
                raise ValueError('unmanaged_file')
    return reports


def legacy_bundle(candidate: Path) -> Path:
    if linked(candidate):
        raise ValueError('linked_folder')
    if (candidate/'SOURCE_MANIFEST.json').is_file():
        return candidate
    children = list(candidate.iterdir())
    # Windows Extract All can create a seven-character ZIP wrapper around the
    # twelve-character package folder. Accept only that otherwise-empty wrapper.
    if len(children) == 1 and children[0].is_dir() and LEGACY.fullmatch(children[0].name):
        return children[0]
    raise ValueError('not_a_verified_package')


def idle_for(mode: str, observation: dict) -> bool:
    if observation.get('status') != 'read':
        return False
    roles = {row.get('role') for row in observation.get('items', [])}
    # Only the old recovery parent imports code from a recovery package. Its
    # children (and the fixed launcher's host) execute from the canonical repo.
    return not (roles & {'recovery'} if mode == 'collection_recovery' else roles & {'review'})


def cleanup_old_packages(workspace: Path, repo: Path, roots: list[Path], observe) -> list[dict]:
    """Only user-requested cleanup; preserve reports, skip active/modified tools."""
    workspace, repo = workspace.resolve(), repo.resolve()
    results, seen = [], set()
    for root in roots:
        if not root.is_dir() or linked(root):
            continue
        for candidate in sorted(root.iterdir()):
            if not candidate.is_dir() or not LEGACY.fullmatch(candidate.name):
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            record = {'folder': str(candidate), 'status': 'kept'}
            results.append(record)
            quarantine = None
            try:
                if any(resolved == p or resolved in p.parents or p in resolved.parents for p in (repo, workspace)):
                    raise ValueError('protected_location')
                bundle = legacy_bundle(candidate)
                manifest = verified_manifest(bundle)
                reports = legacy_contents(bundle, manifest)
                report_hashes = {p.name: digest(p) for p in reports}
                if not idle_for(manifest['mode'], observe()):
                    raise ValueError('running_or_process_state_unknown')
                archive = workspace/'reports'/'previous'
                if any(p.is_symlink() or (p.exists() and linked(p)) for p in (archive.parent, archive)):
                    raise ValueError('linked_report_archive')
                archive.mkdir(parents=True, exist_ok=True)
                if linked(archive) or linked(archive.parent):
                    raise ValueError('linked_report_archive')
                for report in reports:
                    saved = archive/(candidate.name+'__'+digest(report)[:16]+'__'+report.name)
                    if not saved.exists():
                        with saved.open('xb') as out:
                            out.write(report.read_bytes())
                    if linked(saved) or digest(saved) != digest(report):
                        raise ValueError('report_preservation_failed')
                # Rename prevents a new launch through the old path. Recheck
                # processes and contents after the rename before deleting code.
                quarantine = candidate.with_name('CRYPTO_CLEANUP_PENDING_'+uuid.uuid4().hex)
                candidate.rename(quarantine)
                moved = legacy_bundle(quarantine)
                if moved.relative_to(quarantine) != bundle.relative_to(candidate) or verified_manifest(moved) != manifest:
                    raise ValueError('package_changed_during_cleanup')
                moved_reports = legacy_contents(moved, manifest)
                if {p.name: digest(p) for p in moved_reports} != report_hashes:
                    raise ValueError('report_changed_during_cleanup')
                if not idle_for(manifest['mode'], observe()):
                    raise ValueError('process_started_during_cleanup')
                shutil.rmtree(quarantine)
                quarantine = None
                record.update(status='removed', reports_preserved=len(reports))
            except (OSError, ValueError, TypeError, KeyError) as exc:
                record['reason'] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                if quarantine is not None and quarantine.exists():
                    if not candidate.exists():
                        try:
                            quarantine.rename(candidate)
                        except OSError:
                            record['recovery_folder'] = str(quarantine)
                    else:
                        record['recovery_folder'] = str(quarantine)
    return results
