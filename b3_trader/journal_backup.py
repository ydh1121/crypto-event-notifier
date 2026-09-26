"""Verified SQLite backup shared by explicit local journal writes."""
from contextlib import closing
import sqlite3
import time
import uuid

from .manual_trading import PlanningError


def backup_journal(source, folder, prefix):
    count = source.execute('SELECT COUNT(*) FROM manual_holdings').fetchone()[0]
    folder.mkdir(exist_ok=True)
    destination = folder/(prefix+uuid.uuid4().hex+'.sqlite3')
    deadline = time.monotonic()+60
    def progress(*_):
        if time.monotonic() > deadline:
            raise PlanningError('DB 백업 시간이 초과됐습니다. 저장되지 않았습니다.', 503)
    with closing(sqlite3.connect(destination)) as target:
        source.backup(target, pages=2048, progress=progress, sleep=.02)
    with closing(sqlite3.connect(destination.as_uri()+'?mode=ro', uri=True)) as verify:
        if (verify.execute('PRAGMA quick_check').fetchall() != [('ok',)]
                or verify.execute('SELECT COUNT(*) FROM manual_holdings').fetchone()[0] != count):
            raise PlanningError('DB 백업 대조에 실패했습니다. 저장되지 않았습니다.', 503)
    return destination
