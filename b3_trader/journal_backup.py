"""Journal writes share the daily verified backup, including after restart."""
from pathlib import Path
from .managed_backup import ensure_backup
from .manual_trading import PlanningError


def backup_journal(source, folder=None, prefix=None):
    # Legacy caller arguments remain compatible; no new per-feature folders.
    path = next((r[2] for r in source.execute('PRAGMA database_list') if r[1]=='main'), '')
    if not path:
        raise PlanningError('기존 보유정보 DB 경로를 확인하세요.', 503)
    try:
        return Path(ensure_backup(Path(path), role='journal', connection=source)['path'])
    except (ValueError, TimeoutError) as exc:
        raise PlanningError('백업 확인을 마치지 못했습니다. 잠시 후 다시 저장하세요.', 503) from exc
