"""Select bounded public subscriptions from existing watchlists and holdings.

Only symbols leave this reader. It never edits a portfolio, strategy or database.
Each exchange validates its own markets; one venue cannot authorize another's
subscription. Failed reads retain the last known inputs until the next refresh.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

from .exchange_public import public_exchange
from .holdings_review import read_holdings, resolve_holdings_path

DEFAULT_MARKETS = ("KRW-BTC", "KRW-ETH")
MAX_MARKETS = 8
REFRESH_SECONDS = 60.0
CATALOG_SECONDS = 300.0
EXCHANGES = ("bithumb", "upbit")


def valid_market(value):
    return isinstance(value, str) and re.fullmatch(r"KRW-[A-Z0-9]+", value) is not None


def market_list(raw):
    return tuple(dict.fromkeys(m.strip().upper() for m in str(raw or '').split(',')
                               if valid_market(m.strip().upper())))


class SubscriptionSelector:
    def __init__(self, root: Path, *, environment=None, catalog=None):
        self.root = root
        self.environment = os.environ if environment is None else environment
        self.catalog = catalog or (lambda exchange: public_exchange(exchange).krw_markets())
        self.catalogs = {}
        self.catalog_times = {}
        self.catalog_checks = {}
        self.profiles = {exchange: () for exchange in EXCHANGES}
        self.holdings = {exchange: () for exchange in EXCHANGES}
        self.evidence = {}

    def _inputs(self):
        profile_status = 'read'
        try:
            data = json.loads((self.root/'control/assets.json').read_text(encoding='utf-8-sig'))
            rows = data['assets']
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise ValueError('Invalid asset list')
            self.profiles = {exchange: tuple(dict.fromkeys(
                row['market'] for row in rows if row.get('enabled') is True
                and valid_market(row.get('market'))
                and row.get('exchange') in (None, '', exchange))) for exchange in EXCHANGES}
        except (OSError, ValueError, KeyError, TypeError):
            profile_status = 'unavailable'
        path, _ = resolve_holdings_path(self.root/'b3_trader/data/auto_demo.sqlite3')
        confirmed = self.environment.get('MARKET_FLOW_HOLDINGS_EXCHANGE')
        confirmed = confirmed if confirmed in EXCHANGES else None
        result = read_holdings(path, [], confirmed_exchange=confirmed)
        if result['status'] == 'read':
            self.holdings = {exchange: tuple(dict.fromkeys(
                'KRW-'+row['symbol'] for row in result['holdings']
                if row['valid'] and not row['closed'] and row['exchange'] == exchange
                and valid_market('KRW-'+row['symbol']))) for exchange in EXCHANGES}
        return profile_status, result['status']

    def refresh(self, now: float):
        profiles_status, holdings_status = self._inputs()
        selected = {}
        for exchange in EXCHANGES:
            previous_check = self.catalog_checks.get(exchange, {})
            interval = CATALOG_SECONDS if previous_check.get('ok') else REFRESH_SECONDS
            if now - previous_check.get('at', float('-inf')) >= interval:
                try:
                    available = {row.market for row in self.catalog(exchange)
                                 if row.exchange == exchange and valid_market(row.market)}
                    if not set(DEFAULT_MARKETS) <= available:
                        raise ValueError('Incomplete public market list')
                    self.catalogs[exchange] = available
                    self.catalog_times[exchange] = now
                    self.catalog_checks[exchange] = {'ok': True, 'at': now}
                except Exception:
                    # No URL, credentials, raw responses or exception text in status.
                    self.catalog_checks[exchange] = {'ok': False, 'at': now}
            available = self.catalogs.get(exchange, set(DEFAULT_MARKETS))
            requested = tuple(dict.fromkeys((*DEFAULT_MARKETS,
                *market_list(self.environment.get('MARKET_FLOW_STREAM_'+exchange.upper()+'_MARKETS')),
                *market_list(self.environment.get('MARKET_FLOW_STREAM_MARKETS')),
                *self.holdings[exchange], *self.profiles[exchange])))
            validated = [market for market in requested if market in available]
            selected[exchange] = tuple(validated[:MAX_MARKETS])
            self.evidence[exchange] = {
                'desired_markets': list(selected[exchange]),
                'capacity': MAX_MARKETS,
                'deferred_markets': validated[MAX_MARKETS:],
                'unavailable_markets': [m for m in requested if m not in available],
                'catalog_status': ('current' if self.catalog_checks[exchange]['ok'] else
                                   'cached' if exchange in self.catalogs else 'unavailable'),
                'catalog_checked_at': self.catalog_checks[exchange]['at'],
                'catalog_received_at': self.catalog_times.get(exchange),
                'profiles_status': profiles_status, 'holdings_status': holdings_status,
            }
        return selected
