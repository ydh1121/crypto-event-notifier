"""Explicit real-holding updates, with atomic receipts and optimistic concurrency.

No exchange orders, PAPER writes, deletion, or guessed historical executions.
The existing zero-quantity row remains available for history and buying again.
"""
from contextlib import closing
from decimal import Decimal
import hashlib
import json
import re
import time

from .holding_identity import holding_revision
from .journal_backup import backup_journal
from .manual_planning_store import ManualPlanningStore, encoded
from .manual_trading import PlanningError, clean_fill, number, position_fill
from .user_tools import holding_quote_currency, normalize_holding_market


def scope(payload, confirmed_exchange):
    exchange, market, quote = (payload.get(k) for k in ('exchange', 'market', 'quote_currency'))
    if exchange not in {'bithumb', 'upbit'} or (confirmed_exchange and exchange != confirmed_exchange):
        raise PlanningError('보유 거래소를 확인하세요.')
    if not isinstance(market, str) or len(market) > 80:
        raise PlanningError('보유 코인을 확인하세요.')
    try:
        normalize_holding_market(market)
        if quote not in {'KRW', 'BTC'} or holding_quote_currency(market) != quote:
            raise ValueError()
    except ValueError:
        raise PlanningError('보유 코인과 매수 통화를 확인하세요.')
    return {'exchange': exchange, 'market': market, 'quote_currency': quote,
            'key': f'{exchange}|{market}|{quote}'}


def position(row):
    qty = number(row['volume'], '보유수량')
    avg = number(row['avg_price'], '평단', positive=qty > 0)
    return {'volume': float(qty), 'avg_price': float(avg), 'updated_ts': row['updated_ts']}


def execution_amounts(change):
    """Derive money from the recorded execution, including pre-existing receipts."""
    if change['action'] not in {'buy', 'sell'}:
        return None
    fill = change['fill']
    gross = Decimal(fill['price']) * Decimal(fill['volume'])
    fee = Decimal(fill['fee'])
    return {'gross': gross, 'fee': fee,
            'net': gross + (fee if change['action'] == 'buy' else -fee)}


def with_amounts(change):
    amounts = execution_amounts(change)
    return {**change, 'amounts': {k: float(v) for k, v in amounts.items()} if amounts else None}


def clean_change(payload, confirmed_exchange):
    clean = scope(payload, confirmed_exchange)
    action = payload.get('action')
    if action not in {'buy', 'sell', 'adjust', 'close'}:
        raise PlanningError('보유정보 변경 방식을 선택하세요.')
    revision = payload.get('expected_revision')
    if not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{64}', revision):
        raise PlanningError('최신 보유정보를 불러오세요.', 409)
    request_id = payload.get('request_id')
    if not isinstance(request_id, str) or not re.fullmatch(r'[a-f0-9-]{32,36}', request_id):
        raise PlanningError('저장 요청을 다시 시작하세요.')
    clean.update(action=action, expected_revision=revision)
    if action in {'buy', 'sell'}:
        raw = payload.get('fill')
        if not isinstance(raw, dict):
            raise PlanningError('실제 체결 정보를 입력하세요.')
        clean['fill'] = clean_fill({**raw, 'side': action, 'stage': ''})
    elif action == 'adjust':
        qty = number(payload.get('volume'), '보유수량')
        avg = number(payload.get('avg_price'), '평균 매수가', positive=qty > 0)
        if qty * avg > Decimal('1e20'):
            raise PlanningError('수량과 평단을 확인하세요.')
        clean.update(volume=str(qty), avg_price=str(avg if qty else Decimal(0)))
    return clean, 'local-holding-' + request_id


def calculate_change(row, clean):
    before = position(row)
    qty, avg = Decimal(str(before['volume'])), Decimal(str(before['avg_price']))
    realized = None
    if clean['action'] in {'buy', 'sell'}:
        fill = clean['fill']
        volume = Decimal(fill['volume'])
        net = execution_amounts(clean)['net']
        qty, cost, realized = position_fill(qty, qty * avg, clean['action'], volume, net)
        avg = cost / qty if qty else Decimal(0)
    elif clean['action'] == 'adjust':
        qty, avg = Decimal(clean['volume']), Decimal(clean['avg_price'])
    else:
        if not qty:
            raise PlanningError('이미 보유 목록에서 정리된 자산입니다.')
        qty = avg = Decimal(0)
    number(qty, '변경 후 수량')
    number(avg, '변경 후 평단')
    if qty * avg > Decimal('1e20'):
        raise PlanningError('변경 후 보유 금액을 확인하세요.')
    return {'before': before, 'after': {'volume': float(qty), 'avg_price': float(avg)},
            'realized_quote': float(realized) if realized is not None else None}


class HoldingManagement:
    def __init__(self, path):
        self.store = ManualPlanningStore(path)
        self.backed_up = False

    def current(self, conn, clean, confirmed_exchange):
        self.store.schema(conn)
        columns = {r[1] for r in conn.execute('PRAGMA table_info(manual_holdings)')}
        exchange = 'exchange' if 'exchange' in columns else 'NULL AS exchange'
        row = conn.execute(f'SELECT market,volume,avg_price,{exchange},updated_ts FROM manual_holdings WHERE market=?',
                           (clean['market'],)).fetchone()
        if row is None:
            raise PlanningError('보유 자산을 찾지 못했습니다.', 404)
        effective = confirmed_exchange or str(row['exchange'] or '').strip().lower()
        if effective != clean['exchange']:
            raise PlanningError('보유 거래소가 변경됐습니다. 다시 불러오세요.', 409)
        position(row)
        return row

    @staticmethod
    def has_receipts(conn):
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='holding_mutation_receipts'").fetchone()

    def receipt(self, conn, request_id, fingerprint):
        if self.has_receipts(conn):
            row = conn.execute('SELECT result_json FROM holding_mutation_receipts WHERE mutation_id=?', (request_id,)).fetchone()
            if row:
                saved = json.loads(row[0])
                if saved.get('fingerprint') != fingerprint:
                    raise PlanningError('같은 요청 번호의 내용이 다릅니다.', 409)
                return with_amounts(saved)

    def read(self, payload, confirmed_exchange=None):
        clean = scope(payload, confirmed_exchange)
        with closing(self.store.connect()) as conn:
            conn.execute('BEGIN')
            row = self.current(conn, clean, confirmed_exchange)
            history = []
            if self.has_receipts(conn):
                # Exact exchange + original market spelling + quote scope. The
                # shared receipt journal also holds unrelated cloud mutations.
                rows = conn.execute('''SELECT result_json FROM holding_mutation_receipts
                    WHERE mutation_id LIKE 'local-holding-%' AND json_valid(result_json)
                    AND json_extract(result_json,'$.key')=? ORDER BY applied_ts DESC,mutation_id DESC LIMIT 101''', (clean['key'],))
                history = [with_amounts(json.loads(r[0])) for r in rows]
            return {**clean, 'current': position(row), 'revision': holding_revision(row),
                    'history': history[:100], 'has_more': len(history) > 100}

    def change(self, payload, confirmed_exchange=None, *, apply=False):
        clean, request_id = clean_change(payload, confirmed_exchange)
        fingerprint = hashlib.sha256(encoded(clean).encode()).hexdigest()
        with self.store.lock:
            with closing(self.store.connect()) as conn:
                conn.execute('BEGIN')
                saved = self.receipt(conn, request_id, fingerprint)
                if saved:
                    return saved
                row = self.current(conn, clean, confirmed_exchange)
                if holding_revision(row) != clean['expected_revision']:
                    raise PlanningError('보유정보가 바뀌었습니다. 최신 정보로 다시 확인하세요.', 409)
                preview = with_amounts({**clean, **calculate_change(row, clean)})
                if not apply:
                    return preview
                if not self.backed_up:
                    backup_journal(conn, self.store.path.parent / 'holding-management-backups', 'before-manage-holding-')
                    self.backed_up = True
            with closing(self.store.connect(write=True)) as conn, conn:
                conn.execute('BEGIN IMMEDIATE')
                saved = self.receipt(conn, request_id, fingerprint)
                if saved:
                    return saved
                row = self.current(conn, clean, confirmed_exchange)
                if holding_revision(row) != clean['expected_revision']:
                    raise PlanningError('보유정보가 바뀌었습니다. 최신 정보로 다시 확인하세요.', 409)
                result = with_amounts({**clean, **calculate_change(row, clean), 'mutation_id': request_id,
                                      'fingerprint': fingerprint, 'applied_ts': time.time()})
                after = result['after']
                conn.execute('UPDATE manual_holdings SET volume=?,avg_price=?,updated_ts=? WHERE market=?',
                             (after['volume'], after['avg_price'], result['applied_ts'], clean['market']))
                conn.execute('''CREATE TABLE IF NOT EXISTS holding_mutation_receipts (
                    mutation_id TEXT PRIMARY KEY, applied_ts REAL NOT NULL, result_json TEXT NOT NULL)''')
                conn.execute('INSERT INTO holding_mutation_receipts VALUES (?,?,?)',
                             (request_id, result['applied_ts'], encoded(result)))
                return result
