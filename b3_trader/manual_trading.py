"""Recorded manual executions and comparison; never an order/exchange client."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
import re
import time

from .user_tools import normalize_holding_market, holding_quote_currency
from .trade_cycle_metrics import cycle_metrics


class PlanningError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def identity(data):
    exchange, market, experiment = (data.get(k) for k in ('exchange', 'market', 'experiment'))
    if exchange not in {'bithumb', 'upbit'} or not isinstance(market, str) or len(market) > 80:
        raise PlanningError('거래소와 코인을 확인하세요.')
    try:
        normalized = normalize_holding_market(market)
    except ValueError:
        raise PlanningError('코인 표기를 확인하세요.')
    if normalized != market or holding_quote_currency(market) != 'KRW':
        raise PlanningError('원화 마켓을 선택하세요.')
    if not isinstance(experiment, str) or not re.fullmatch(r'[A-Za-z0-9_.:|\-]{1,180}', experiment):
        raise PlanningError('전략을 선택하세요.')
    return [exchange, market, 'KRW', experiment]


def number(value, label, *, positive=False, maximum='1e20'):
    if isinstance(value, bool) or value is None or len(str(value)) > 80:
        raise PlanningError(f'{label}을 확인하세요.')
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or n > Decimal(maximum) or (positive and n == 0) or (n != 0 and n < Decimal('1e-18')):
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        raise PlanningError(f'{label}을 확인하세요.')
    return n


def clean_draft(raw):
    if not isinstance(raw, dict):
        raise PlanningError('계획을 확인하세요.')
    out = {}
    for key in ('volume', 'average', 'fee', 'slippage', 'budget'):
        value = raw.get(key)
        if key == 'budget' and value == '':
            out[key] = ''
            continue
        n = number(value, '계획 숫자', maximum='99.9999' if key in {'fee', 'slippage'} else '1e20')
        out[key] = str(value)
        if key == 'average' and number(out['volume'], '수량') > 0 and n == 0:
            raise PlanningError('보유수량이 있으면 평단을 입력하세요.')
    for key, amount in (('buys', 'amount'), ('sells', 'weight')):
        rows = raw.get(key)
        if not isinstance(rows, list) or len(rows) > 20:
            raise PlanningError('분할 회차는 20개까지 저장합니다.')
        out[key] = []
        total = Decimal(0)
        for row in rows:
            if not isinstance(row, dict):
                raise PlanningError('분할 회차를 확인하세요.')
            price, value = row.get('price'), row.get(amount)
            if price == '' and value == '':
                out[key].append({'price': '', amount: ''})
                continue
            number(price, '회차 가격', positive=True)
            total += number(value, '회차 금액·비중', positive=True)
            out[key].append({'price': str(price), amount: str(value)})
            if row.get('basis') in {'next_condition', 'conditional_recalculation'}:
                out[key][-1]['basis'] = row['basis']
        if key == 'sells' and total > 100:
            raise PlanningError('익절 비중의 합계는 100% 이하여야 합니다.')
    revision = raw.get('holdingRevision')
    if not isinstance(revision, str) or len(revision) > 160:
        raise PlanningError('시작 보유정보를 다시 불러오세요.')
    out.update(holdingRevision=revision, origin=raw.get('origin') if raw.get('origin') in {'manual', 'strategy'} else 'manual')
    return out


def clean_fill(raw, now=None):
    now = time.time() if now is None else now
    if not isinstance(raw, dict) or raw.get('side') not in {'buy', 'sell'}:
        raise PlanningError('매수 또는 매도를 선택하세요.')
    ts = float(number(raw.get('ts'), '체결 시각', positive=True, maximum=str(now + 60)))
    if ts < 1230768000:
        raise PlanningError('체결 시각을 확인하세요.')
    price = number(raw.get('price'), '체결가', positive=True)
    volume = number(raw.get('volume'), '체결 수량', positive=True)
    fee = number(raw.get('fee'), '실제 수수료')
    if price * volume > Decimal('1e20') or fee > price * volume:
        raise PlanningError('체결 금액과 수수료를 확인하세요.')
    stage = raw.get('stage', '')
    if not isinstance(stage, str) or (stage and not re.fullmatch(r'(buy|sell):(?:[0-9]|1[0-9])', stage)):
        raise PlanningError('비교할 계획 회차를 확인하세요.')
    if stage and stage.split(':')[0] != raw['side']:
        raise PlanningError('체결 종류와 계획 회차가 다릅니다.')
    return {'ts': ts, 'side': raw['side'], 'price': str(price), 'volume': str(volume), 'fee': str(fee), 'stage': stage}


def position_fill(qty, cost, side, volume, net):
    """Average-cost position arithmetic shared by actual holdings and journals."""
    if side == 'buy':
        return qty + volume, cost + net, None
    if side != 'sell':
        raise PlanningError('체결 종류를 확인하세요.')
    if volume > qty or qty == 0:
        raise PlanningError('보유수량보다 많이 매도할 수 없습니다.')
    basis = cost * volume / qty
    remaining = qty - volume
    return remaining, cost - basis if remaining else Decimal(0), net - basis


def replay(trades, *, paper=False):
    """Average-cost manual ledger, actual paid fees. No mark or opening holding is guessed.

    PAPER krw already includes fees; both journals use the same cycle arithmetic.
    A completed cycle starts flat and ends flat, including partial sells.
    """
    qty = cost = realized = fees = invested = cycle_cost = cycle_pnl = Decimal(0)
    opened = None
    rows, cycles = [], []
    positions, position = [], None
    for t in sorted(trades, key=lambda t: (t['ts'], t.get('sequence', t.get('id', 0)))):
        if t.get('voided'):
            continue
        volume = number(t['volume'], '체결 수량', positive=True)
        price = number(t['price'], '체결가', positive=True)
        side = t['side']
        fee = Decimal(0) if paper else number(t['fee'], '수수료')
        net = number(t['krw'], '체결 금액') if paper else price * volume + (fee if side == 'buy' else -fee)
        pnl = None
        if side == 'buy':
            if qty == 0:
                opened, cycle_cost, cycle_pnl = t['ts'], Decimal(0), Decimal(0)
                position = {'entry_trade_id': t.get('id', t.get('sequence')), 'entry_ts': opened,
                            'exit_ts': None, 'exit_trade_id': None, 'buy_count': 0, 'sell_count': 0}
                cycle_proceeds = cycle_fees = Decimal(0)
            qty, cost, pnl = position_fill(qty, cost, side, volume, net)
            invested += net
            cycle_cost += net
            position['buy_count'] += 1
        elif side == 'sell':
            # Native PAPER quantities can have tiny binary rounding differences.
            if paper and qty > 0 and abs(volume - qty) <= max(Decimal('1e-8'), qty * Decimal('1e-9')):
                volume = qty
            if volume > qty or qty == 0:
                raise PlanningError('기록된 매수 잔량보다 많이 매도할 수 없습니다. 앞선 매수부터 기록하세요.')
            qty, cost, pnl = position_fill(qty, cost, side, volume, net)
            realized += pnl
            cycle_pnl += pnl
            cycle_proceeds += net
            position['sell_count'] += 1
            if qty == 0:
                cycles.append({'opened_at': opened, 'closed_at': t['ts'], 'realized': float(cycle_pnl),
                    'return_pct': float(cycle_pnl / cycle_cost * 100) if cycle_cost else None})
                cost = Decimal(0)
        else:
            raise PlanningError('체결 종류를 확인하세요.')
        fees += fee
        cycle_fees += fee
        position.update(invested_krw=float(cycle_cost), proceeds_krw=float(cycle_proceeds),
                        fees_krw=None if paper else float(cycle_fees),
                        realized_pnl_krw=float(cycle_pnl), remaining_volume=float(qty),
                        remaining_cost_krw=float(cost), return_pct=None)
        if qty == 0:
            position.update(exit_ts=t['ts'], exit_trade_id=t.get('id', t.get('sequence')),
                            return_pct=float(cycle_pnl / cycle_cost * 100) if cycle_cost else None)
            positions.append(position)
            position = None
        rows.append({**t, 'gross_krw': float(price * volume), 'net': float(net), 'realized': float(pnl) if pnl is not None else None,
                     'remaining': float(qty)})
    if position:
        positions.append(position)
    return {'volume': float(qty), 'average': float(cost / qty) if qty else None,
            'realized': float(realized), 'fees': float(fees), 'buy_total': float(invested),
            'trades': rows, 'cycles': cycles, 'positions': positions}


def compare_journals(real, account):
    active = real['trades']
    result = {'version': 2, 'status': 'no_manual_trades', 'manual': cycle_metrics(real['positions']),
              'paper': None, 'start': None, 'end': None, 'costs_included': True,
              'paper_revision': (account or {}).get('revision'), 'witnesses_limit': 20,
              'manual_witnesses': [], 'paper_witnesses': [], 'paper_carried_positions': None}
    if not active:
        return result
    start, end = min(t['ts'] for t in active), max(t['ts'] for t in active)
    result.update(start=start, end=end, status='paper_unavailable',
                  manual_witnesses=list(reversed(real['positions']))[:20])
    if not account or not account.get('reconciliation', {}).get('matches'):
        return result
    journal = account.get('journal', {})
    if 'rows' not in journal or journal.get('total') != len(journal['rows']):
        result['status'] = 'paper_incomplete'
        return result
    trades = [dict(zip(journal['columns'], row)) for row in journal['rows']]
    previous = 0
    for trade in trades:
        ts = trade.get('ts')
        if not isinstance(ts, (int, float)) or not math.isfinite(ts) or ts <= 0 or ts < previous:
            return result
        previous = ts
    try:
        paper = replay([t for t in trades if t['ts'] <= end], paper=True)
    except PlanningError:
        return result
    selected = [c for c in paper['positions'] if c['entry_ts'] >= start]
    result.update(status='ok', paper=cycle_metrics(selected), paper_witnesses=list(reversed(selected))[:20],
                  paper_carried_positions=sum(c['entry_ts'] < start and (c['exit_ts'] is None or c['exit_ts'] >= start)
                                              for c in paper['positions']))
    return result
