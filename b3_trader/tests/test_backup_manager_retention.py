from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from b3_trader.sync_manager import BackupManager


class _State:
    def __init__(self) -> None:
        self.backup: dict = {}
        self.errors: list[tuple[Exception, str]] = []

    def set_backup(self, payload: dict) -> None:
        self.backup = payload

    def set_error(self, exc: Exception, *, scope: str) -> None:
        self.errors.append((exc, scope))


def _make_sqlite(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO sample(value) VALUES('ok')")
        conn.commit()
    finally:
        conn.close()


def test_backup_manager_applies_local_generational_retention(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    local_dir = tmp_path / "backups"
    local_dir.mkdir()
    _make_sqlite(source)

    newest_old = datetime(2026, 8, 31, 23, 0, 0)
    for index in range(36):
        stamp = newest_old - timedelta(hours=6 * index)
        (local_dir / f"crypto-trader-{stamp:%Y%m%d-%H%M%S}.sqlite3").write_bytes(b"old")

    manual = local_dir / "manual-before-maintenance.sqlite3"
    manual.write_bytes(b"manual")

    state = _State()
    manager = BackupManager(
        sqlite_path=str(source),
        local_dir=str(local_dir),
        interval_seconds=300,
        state=state,
    )

    payload = manager.backup_once()

    assert payload["status"] == "ok"
    assert payload["drive"] == "disabled"
    assert Path(payload["local"]).exists()
    assert manual.exists()
    retention = payload["local_retention"]
    assert retention["policy"] == "recent=8,daily=7,weekly=4"
    assert retention["recognized_before"] == 37
    assert retention["removed"] > 0
    assert retention["retained"] <= 19
    assert retention["ignored_unrecognized"] == 1
    assert state.backup == payload
    assert state.errors == []
