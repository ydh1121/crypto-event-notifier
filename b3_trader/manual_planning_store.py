"""Append-only plans and manual execution records in the existing holdings journal.

Reading never creates a DB/schema. The first explicit save backs up and verifies
the existing journal before adding tables. Legacy holdings/plans/fills are untouched.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

from .manual_trading import PlanningError, identity, clean_draft, clean_fill, replay, compare_journals

TABLES = {'manual_strategy_meta', 'manual_strategy_plans', 'manual_strategy_records'}
SCHEMA = (
    'CREATE TABLE manual_strategy_meta (version INTEGER PRIMARY KEY, backup_name TEXT NOT NULL, created_ts REAL NOT NULL)',
    '''CREATE TABLE manual_strategy_plans (scope TEXT NOT NULL, revision INTEGER NOT NULL,
       request_id TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL, saved_ts REAL NOT NULL,
       draft_json TEXT NOT NULL, paper_json TEXT NOT NULL, PRIMARY KEY(scope,revision))''',
    '''CREATE TABLE manual_strategy_records (sequence INTEGER PRIMARY KEY AUTOINCREMENT,
       scope TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL,
       kind TEXT NOT NULL, payload_json TEXT NOT NULL, created_ts REAL NOT NULL)''',
    'CREATE INDEX idx_manual_strategy_records_scope ON manual_strategy_records(scope,sequence)',
)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class ManualPlanningStore:
    def __init__(self, path):
        self.path = Path(path).resolve() if path else None
        self.lock = threading.RLock()

    def connect(self, write=False):
        if self.path is None or not self.path.is_file():
            raise PlanningError('기존 보유정보 DB를 찾지 못했습니다.', 503)
        conn = sqlite3.connect(self.path.as_uri() + ('?mode=rw' if write else '?mode=ro'), uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        if not write:
            conn.execute('PRAGMA query_only=ON')
        return conn

    def schema(self, conn):
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {r[1] for r in conn.execute('PRAGMA table_info(manual_holdings)')}
        if not {'market', 'volume', 'avg_price', 'updated_ts'} <= columns:
            raise PlanningError('보유정보 DB 형식을 확인하세요.', 503)
        present = TABLES & tables
        if not present:
            return False
        if present != TABLES or [r[0] for r in conn.execute('SELECT version FROM manual_strategy_meta')] != [1]:
            raise PlanningError('저장 형식이 다릅니다. 기존 기록을 유지합니다.', 503)
        return True

    def prepare(self):
        with closing(self.connect()) as source:
            source.execute('BEGIN')
            if self.schema(source):
                return
            # A consistent snapshot also includes WAL contents. File-copy is unsafe.
            count = source.execute('SELECT COUNT(*) FROM manual_holdings').fetchone()[0]
            folder = self.path.parent / 'manual-planning-backups'
            folder.mkdir(exist_ok=True)
            destination = folder / ('before-manual-plans-' + uuid.uuid4().hex + '.sqlite3')
            deadline = time.monotonic() + 60
            def progress(*_):
                if time.monotonic() > deadline:
                    raise PlanningError('DB 백업 시간이 초과됐습니다. 저장되지 않았습니다.', 503)
            try:
                with closing(sqlite3.connect(destination)) as target:
                    source.backup(target, pages=2048, progress=progress, sleep=.02)
                with closing(sqlite3.connect(destination.as_uri()+'?mode=ro', uri=True)) as verify:
                    if verify.execute('PRAGMA quick_check').fetchall() != [('ok',)] or verify.execute('SELECT COUNT(*) FROM manual_holdings').fetchone()[0] != count:
                        raise PlanningError('DB 백업 대조에 실패했습니다. 저장되지 않았습니다.', 503)
            except Exception:
                # Preserve even an incomplete backup for diagnosis. Never mutate source.
                raise
        with closing(self.connect(write=True)) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            if not self.schema(conn):
                for statement in SCHEMA:
                    conn.execute(statement)
                conn.execute('INSERT INTO manual_strategy_meta VALUES (1,?,?)', (destination.name, time.time()))

    def state(self, conn, scope):
        if not self.schema(conn):
            return {'plan': None, 'plan_revision': 0, 'ledger_revision': 0, 'records': []}
        row = conn.execute('SELECT * FROM manual_strategy_plans WHERE scope=? ORDER BY revision DESC LIMIT 1', (scope,)).fetchone()
        plan = {'revision': row['revision'], 'saved_at': row['saved_ts'], 'draft': json.loads(row['draft_json']),
                'paper': json.loads(row['paper_json'])} if row else None
        records, revision = {}, 0
        for r in conn.execute('SELECT * FROM manual_strategy_records WHERE scope=? ORDER BY sequence', (scope,)):
            payload = json.loads(r['payload_json'])
            revision = r['sequence']
            if r['kind'] == 'fill':
                records[r['request_id']] = {**payload, 'id': r['request_id'], 'sequence': r['sequence'], 'recorded_at': r['created_ts'], 'voided': False}
            elif r['kind'] == 'void' and payload['target'] in records:
                records[payload['target']].update(voided=True, voided_at=r['created_ts'])
        return {'plan': plan, 'plan_revision': plan['revision'] if plan else 0,
                'ledger_revision': revision, 'records': list(records.values())}

    def read(self, selection, account=None):
        scope = encoded(identity(selection))
        with self.lock, closing(self.connect()) as conn:
            conn.execute('BEGIN')
            result = self.state(conn, scope)
        summary = replay(result['records'])
        return {**result, 'summary': summary, 'comparison': compare_journals(summary, account)}

    def write(self, selection, action, payload, account):
        scope = encoded(identity(selection))
        if action not in {'save', 'fill', 'void'}:
            raise PlanningError('저장 종류를 확인하세요.')
        request_id = payload.get('request_id')
        if not isinstance(request_id, str) or not re.fullmatch(r'[a-f0-9-]{32,36}', request_id):
            raise PlanningError('저장 요청을 다시 시작하세요.')
        expected = payload.get('expected_revision')
        if type(expected) is not int or expected < 0:
            raise PlanningError('저장된 기록을 다시 불러오세요.')
        clean = clean_draft(payload.get('draft')) if action == 'save' else clean_fill(payload.get('fill')) if action == 'fill' else {'target': payload.get('target')}
        if action == 'fill':
            if type(payload.get('plan_revision')) is not int or payload['plan_revision'] < 1:
                raise PlanningError('저장한 계획을 다시 불러오세요.')
            clean['plan_revision'] = payload['plan_revision']
        if action == 'void' and (not isinstance(clean['target'], str) or len(clean['target']) > 36):
            raise PlanningError('취소할 기록을 확인하세요.')
        fingerprint = hashlib.sha256(encoded([scope, action, clean]).encode()).hexdigest()
        with self.lock:
            # Validate against read-only current state before any schema mutation.
            with closing(self.connect()) as check:
                check.execute('BEGIN')
                before = self.state(check, scope)
                if self.schema(check):
                    table = 'manual_strategy_plans' if action == 'save' else 'manual_strategy_records'
                    previous = check.execute(f'SELECT scope,fingerprint FROM {table} WHERE request_id=?', (request_id,)).fetchone()
                    if previous:
                        if previous['scope'] != scope or previous['fingerprint'] != fingerprint:
                            raise PlanningError('같은 요청 번호의 내용이 다릅니다.', 409)
                        return self.read(selection, account)
                self.validate(before, action, clean, expected)
            self.prepare()
            with closing(self.connect(write=True)) as conn, conn:
                conn.execute('BEGIN IMMEDIATE')
                table = 'manual_strategy_plans' if action == 'save' else 'manual_strategy_records'
                previous = conn.execute(f'SELECT scope,fingerprint FROM {table} WHERE request_id=?', (request_id,)).fetchone()
                if previous:
                    if previous['scope'] != scope or previous['fingerprint'] != fingerprint:
                        raise PlanningError('같은 요청 번호의 내용이 다릅니다.', 409)
                else:
                    current = self.state(conn, scope)
                    self.validate(current, action, clean, expected)
                    if action == 'save':
                        paper = {k: account.get(k) for k in ('experiment_id', 'style', 'label', 'source_ts', 'return_pct', 'closed_trades', 'wins', 'max_drawdown_pct')}
                        conn.execute('INSERT INTO manual_strategy_plans VALUES (?,?,?,?,?,?,?)',
                            (scope, expected+1, request_id, fingerprint, time.time(), encoded(clean), encoded(paper)))
                    else:
                        if action == 'fill':
                            plan = current['plan']
                            clean['plan_revision'] = plan['revision']
                            clean['reference_price'] = None
                            if clean['stage']:
                                kind, index = clean['stage'].split(':')
                                rows = plan['draft']['buys' if kind == 'buy' else 'sells']
                                if int(index) >= len(rows) or not rows[int(index)]['price']:
                                    raise PlanningError('저장한 계획 회차를 확인하세요.')
                                if clean['ts'] < plan['saved_at']:
                                    raise PlanningError('계획 저장 전 체결은 회차를 지정하지 않고 기록하세요.')
                                clean['reference_price'] = rows[int(index)]['price']
                        conn.execute('INSERT INTO manual_strategy_records(scope,request_id,fingerprint,kind,payload_json,created_ts) VALUES (?,?,?,?,?,?)',
                            (scope, request_id, fingerprint, action, encoded(clean), time.time()))
        return self.read(selection, account)

    @staticmethod
    def validate(state, action, clean, expected):
        actual = state['plan_revision' if action == 'save' else 'ledger_revision']
        if actual != expected:
            raise PlanningError('다른 창에서 기록이 바뀌었습니다. 저장본을 다시 불러오세요.', 409)
        if action == 'save':
            return
        if not state['plan']:
            raise PlanningError('계획을 먼저 저장하세요.')
        records = [dict(r) for r in state['records']]
        if action == 'fill':
            if clean['plan_revision'] != state['plan_revision']:
                raise PlanningError('저장 계획이 바뀌었습니다. 저장본을 다시 불러오세요.', 409)
            records.append({**clean, 'sequence': actual+1})
        else:
            row = next((r for r in records if r['id'] == clean['target']), None)
            if row is None:
                raise PlanningError('체결 기록을 찾지 못했습니다.')
            row['voided'] = True
        replay(records)
