from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

BACKUP_NAME_RE = re.compile(r"^crypto-trader-(\d{8})-(\d{6})\.sqlite3$")
RECENT_BACKUPS = 8
DAILY_BACKUPS = 7
WEEKLY_BACKUPS = 4


def _backup_timestamp(path: Path) -> datetime | None:
    match = BACKUP_NAME_RE.match(path.name)
    if not match:
        return None
    try:
        return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def select_generational_backups(
    paths: Iterable[Path],
    *,
    recent: int = RECENT_BACKUPS,
    daily: int = DAILY_BACKUPS,
    weekly: int = WEEKLY_BACKUPS,
) -> tuple[set[Path], list[Path]]:
    """Return recognized backups to keep/delete using overlapping generations.

    Safety rule: files that do not match the canonical backup filename are never
    returned for deletion. Within recognized backups we keep the newest ``recent``
    copies, the newest copy from ``daily`` distinct local calendar days, and the
    newest copy from ``weekly`` distinct ISO weeks. A file may satisfy more than
    one generation, so the retained count is normally lower than recent+daily+weekly.
    """
    recent = max(0, int(recent))
    daily = max(0, int(daily))
    weekly = max(0, int(weekly))

    recognized: list[tuple[datetime, Path]] = []
    for raw_path in paths:
        path = Path(raw_path)
        stamp = _backup_timestamp(path)
        if stamp is not None:
            recognized.append((stamp, path))

    recognized.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    keep: set[Path] = {path for _, path in recognized[:recent]}

    seen_days: set[tuple[int, int, int]] = set()
    for stamp, path in recognized:
        day_key = (stamp.year, stamp.month, stamp.day)
        if day_key in seen_days:
            continue
        seen_days.add(day_key)
        if len(seen_days) <= daily:
            keep.add(path)
        if len(seen_days) >= daily:
            break

    seen_weeks: set[tuple[int, int]] = set()
    for stamp, path in recognized:
        iso = stamp.isocalendar()
        week_key = (iso.year, iso.week)
        if week_key in seen_weeks:
            continue
        seen_weeks.add(week_key)
        if len(seen_weeks) <= weekly:
            keep.add(path)
        if len(seen_weeks) >= weekly:
            break

    remove = [path for _, path in recognized if path not in keep]
    return keep, remove


def prune_local_backups(
    local_dir: Path,
    *,
    recent: int = RECENT_BACKUPS,
    daily: int = DAILY_BACKUPS,
    weekly: int = WEEKLY_BACKUPS,
) -> dict[str, int | str]:
    """Apply local-only backup retention and return compact observability data."""
    directory = Path(local_dir)
    candidates = list(directory.glob("*.sqlite3")) if directory.exists() else []
    canonical = [path for path in candidates if _backup_timestamp(path) is not None]
    ignored = [path for path in candidates if _backup_timestamp(path) is None]
    keep, remove = select_generational_backups(
        canonical,
        recent=recent,
        daily=daily,
        weekly=weekly,
    )

    removed_bytes = 0
    removed_count = 0
    for path in remove:
        try:
            removed_bytes += path.stat().st_size
        except OSError:
            pass
        try:
            path.unlink()
            removed_count += 1
        except FileNotFoundError:
            pass

    return {
        "policy": f"recent={recent},daily={daily},weekly={weekly}",
        "recognized_before": len(canonical),
        "retained": len(keep),
        "removed": removed_count,
        "removed_bytes": removed_bytes,
        "ignored_unrecognized": len(ignored),
    }
