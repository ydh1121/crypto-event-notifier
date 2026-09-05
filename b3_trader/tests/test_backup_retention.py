from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from b3_trader.backup_retention import prune_local_backups, select_generational_backups


def _name(stamp: datetime) -> str:
    return f"crypto-trader-{stamp:%Y%m%d-%H%M%S}.sqlite3"


def test_generational_selection_keeps_recent_daily_and_weekly_representatives(tmp_path: Path) -> None:
    newest = datetime(2026, 9, 6, 4, 0, 0)
    paths: list[Path] = []
    for index in range(60):
        stamp = newest - timedelta(hours=12 * index)
        path = tmp_path / _name(stamp)
        path.write_bytes(b"x")
        paths.append(path)

    keep, remove = select_generational_backups(paths, recent=8, daily=7, weekly=4)

    ordered = sorted(paths, reverse=True)
    assert set(ordered[:8]).issubset(keep)
    assert keep.isdisjoint(remove)
    assert len(keep) < 19  # generations overlap by design
    assert len(keep) + len(remove) == len(paths)

    kept_days = {path.name[14:22] for path in keep}
    assert len(kept_days) >= 7


def test_unrecognized_sqlite_files_are_never_deleted(tmp_path: Path) -> None:
    newest = datetime(2026, 9, 6, 4, 0, 0)
    for index in range(24):
        stamp = newest - timedelta(hours=index)
        (tmp_path / _name(stamp)).write_bytes(b"abcd")

    manual = tmp_path / "manual-before-maintenance.sqlite3"
    manual.write_bytes(b"important")

    result = prune_local_backups(tmp_path, recent=8, daily=7, weekly=4)

    assert manual.exists()
    assert result["ignored_unrecognized"] == 1
    assert result["removed"] > 0


def test_prune_reports_reclaimed_bytes_and_keeps_newest(tmp_path: Path) -> None:
    newest = datetime(2026, 9, 6, 4, 0, 0)
    paths: list[Path] = []
    for index in range(20):
        stamp = newest - timedelta(hours=index)
        path = tmp_path / _name(stamp)
        path.write_bytes(b"1234567890")
        paths.append(path)

    result = prune_local_backups(tmp_path, recent=8, daily=1, weekly=1)

    newest_path = tmp_path / _name(newest)
    assert newest_path.exists()
    assert result["recognized_before"] == 20
    assert result["retained"] == 8
    assert result["removed"] == 12
    assert result["removed_bytes"] == 120
    assert len(list(tmp_path.glob("crypto-trader-*.sqlite3"))) == 8
