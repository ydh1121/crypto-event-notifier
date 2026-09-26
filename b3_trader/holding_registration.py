"""Explicit insert-only registration in the existing manual holdings journal."""
from contextlib import closing
import hashlib
import json
import math
import re
import time

from .journal_backup import backup_journal
from .manual_planning_store import ManualPlanningStore, encoded
from .manual_trading import PlanningError
from .user_tools import normalize_holding_market, holding_quote_currency


def clean_registration(payload, confirmed_exchange):
    exchange = payload.get('exchange')
    if exchange not in {'bithumb', 'upbit'} or (confirmed_exchange and exchange != confirmed_exchange):
        raise PlanningError('보유 거래소를 확인하세요.')
    symbol, quote = payload.get('symbol'), payload.get('quote_currency')
    if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z0-9]{1,30}', symbol.strip().upper()):
        raise PlanningError('코인 티커를 입력하세요. 예: XRP')
    symbol = symbol.strip().upper()
    if quote not in {'KRW', 'BTC'} or symbol == quote:
        raise PlanningError('매수 통화를 확인하세요.')
    market = normalize_holding_market(symbol+('/BTC' if quote == 'BTC' else ''))
    values = {}
    for field, label in [('volume', '보유수량'), ('avg_price', '평균 매수가')]:
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise PlanningError(label+'를 입력하세요.')
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise PlanningError(label+'를 숫자로 입력하세요.')
        if not math.isfinite(number) or number <= 0:
            raise PlanningError(label+'는 0보다 커야 합니다.')
        values[field] = number
    if not math.isfinite(values['volume']*values['avg_price']):
        raise PlanningError('수량과 평단이 너무 큽니다.')
    request_id = payload.get('request_id')
    if not isinstance(request_id, str) or not re.fullmatch(r'[a-f0-9-]{32,36}', request_id):
        raise PlanningError('추가 요청을 다시 시작하세요.')
    return {'exchange': exchange, 'market': market, **values}, 'local-add-'+request_id


class HoldingRegistration:
    def __init__(self, path):
        self.store = ManualPlanningStore(path)
        self.backed_up = False

    def current(self, conn, clean, request_id, fingerprint):
        self.store.schema(conn)
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='holding_mutation_receipts'").fetchone()
        if exists:
            receipt = conn.execute('SELECT result_json FROM holding_mutation_receipts WHERE mutation_id=?', (request_id,)).fetchone()
            if receipt:
                saved = json.loads(receipt[0])
                if saved.get('fingerprint') != fingerprint:
                    raise PlanningError('같은 요청 번호의 내용이 다릅니다.', 409)
                return saved
        # The legacy journal has a market-only primary key. Never replace another
        # exchange, a closed holding or an older spelling of the same identity.
        for row in conn.execute('SELECT market FROM manual_holdings'):
            try:
                market = normalize_holding_market(row[0])
            except ValueError:
                continue
            if market == clean['market']:
                raise PlanningError('이미 등록된 코인입니다. 매도 완료 목록도 확인하세요.', 409)
        return None

    def add(self, payload, confirmed_exchange=None):
        clean, request_id = clean_registration(payload, confirmed_exchange)
        fingerprint = hashlib.sha256(encoded(clean).encode()).hexdigest()
        with self.store.lock:
            with closing(self.store.connect()) as conn:
                conn.execute('BEGIN')
                saved = self.current(conn, clean, request_id, fingerprint)
                if saved:
                    return saved
                if not self.backed_up:
                    backup_journal(conn, self.store.path.parent/'holding-registration-backups', 'before-add-holding-')
                    self.backed_up = True
            with closing(self.store.connect(write=True)) as conn, conn:
                conn.execute('BEGIN IMMEDIATE')
                saved = self.current(conn, clean, request_id, fingerprint)
                if saved:
                    return saved
                columns = {r[1] for r in conn.execute('PRAGMA table_info(manual_holdings)')}
                if 'exchange' not in columns:
                    conn.execute('ALTER TABLE manual_holdings ADD COLUMN exchange TEXT')
                conn.execute('''CREATE TABLE IF NOT EXISTS holding_mutation_receipts (
                    mutation_id TEXT PRIMARY KEY, applied_ts REAL NOT NULL, result_json TEXT NOT NULL)''')
                now = time.time()
                result = {**clean, 'action': 'add_holding', 'mutation_id': request_id, 'fingerprint': fingerprint,
                          'updated_ts': now, 'key': f"{clean['exchange']}|{clean['market']}|{holding_quote_currency(clean['market'])}"}
                conn.execute('INSERT INTO manual_holdings(market,volume,avg_price,exchange,updated_ts) VALUES (?,?,?,?,?)',
                             (clean['market'], clean['volume'], clean['avg_price'], clean['exchange'], now))
                conn.execute('INSERT INTO holding_mutation_receipts VALUES (?,?,?)', (request_id, now, encoded(result)))
                return result
