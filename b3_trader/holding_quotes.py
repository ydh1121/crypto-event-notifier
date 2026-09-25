"""Optional public ticker reads for the local holdings viewer (stdlib only).

Same /v1/ticker contract as BithumbClient/UpbitClient. No private client, keys,
orders or persistence. Only public market codes leave the machine, on demand.
"""
from __future__ import annotations

import json
from http.client import HTTPException
import math
import re
import ssl
import threading
import time
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener

ENDPOINTS = {"bithumb": "https://api.bithumb.com/v1/ticker",
             "upbit": "https://api.upbit.com/v1/ticker"}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


def request_tickers(exchange: str, markets: list[str]) -> list:
    if exchange not in ENDPOINTS or not 0 < len(markets) <= 100 or any(
            not re.fullmatch(r"(?:KRW|BTC)-[A-Z0-9]{1,30}", m) for m in markets):
        raise ValueError("Invalid public market")
    url = ENDPOINTS[exchange] + "?" + urlencode({"markets": ",".join(markets)})
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "CryptoLocalReview/1"})
    with build_opener(_NoRedirect()).open(request, timeout=4) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Ticker response too large")
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("Invalid ticker response")
    return payload


def public_markets(holdings: list[dict]) -> dict[str, list[str]]:
    groups = {exchange: set() for exchange in ENDPOINTS}
    for h in holdings:
        exchange, market = h.get("exchange"), h.get("api_market")
        if h.get("closed") or not h.get("valid") or exchange not in groups or not isinstance(market, str):
            continue
        if not re.fullmatch(r"(?:KRW|BTC)-[A-Z0-9]{1,30}", market):
            continue
        groups[exchange].add(market)
        if market.startswith("BTC-"):
            groups[exchange].add("KRW-BTC")
            groups[exchange].add("KRW-" + market.split('-',1)[1])
    return {exchange: sorted(markets) for exchange, markets in groups.items() if markets}


def parse_tickers(exchange: str, markets: list[str], payload: list, now: float) -> list[dict]:
    accepted, seen, duplicate = {}, set(), set()
    for row in payload:
        if not isinstance(row, dict) or row.get("market") not in markets:
            continue
        market = row["market"]
        if market in seen:
            duplicate.add(market)
        seen.add(market)
        try:
            if isinstance(row.get("trade_price"), bool) or isinstance(row.get("trade_timestamp"), bool):
                continue
            price, ts = float(row["trade_price"]), float(row["trade_timestamp"]) / 1000
            if not math.isfinite(price) or not math.isfinite(ts) or price <= 0 or not 0 < ts <= now:
                continue
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        accepted[market] = {"exchange": exchange, "market": market, "price": price,
                            "signal_ts": ts, "price_source": "public_ticker"}
    return [row for market, row in accepted.items() if market not in duplicate]


class HoldingQuotes:
    """One process cache; repeated clicks cannot fan out public requests."""
    def __init__(self, fetch=request_tickers):
        self.fetch = fetch
        self.lock = threading.Lock()
        self.refresh_lock = threading.Lock()
        self.cache = {}
        self.last_attempt = -math.inf
        self.state = {"status": "not_requested", "requested": 0, "received": 0}

    def snapshot(self) -> tuple[list[dict], dict]:
        with self.lock:
            return [dict(row) for row in self.cache.values()], dict(self.state)

    def refresh(self, holdings: list[dict]) -> None:
        if not self.refresh_lock.acquire(blocking=False):
            return
        try:
            if time.monotonic() - self.last_attempt < 15:
                return
            self.last_attempt = time.monotonic()
            groups = public_markets(holdings)
            requested, received = sum(map(len, groups.values())), []
            failures = []
            with self.lock:
                self.state = {"status": "loading", "requested": requested, "received": 0}
            for exchange, all_markets in groups.items():
                # An unsupported BTC pair must not fail a batch of valid KRW
                # quotes, including the BTC conversion rate and ETH valuation.
                for quote in ('KRW', 'BTC'):
                    markets = [m for m in all_markets if m.startswith(quote+'-')]
                    if not markets:
                        continue
                    try:
                        parsed = parse_tickers(exchange, markets, self.fetch(exchange, markets), time.time())
                        received.extend(parsed)
                        if len(parsed) != len(markets):
                            failures.append({'exchange':exchange,'quote':quote,'reason':'incomplete'})
                    except HTTPError as exc:
                        failures.append({'exchange':exchange,'quote':quote,'reason':'rate_limit' if exc.code in {418,429} else 'http_error','http_status':exc.code})
                        if exc.code in {418,429}:
                            break
                    except (OSError, ValueError, TypeError, HTTPException) as exc:
                        cause = exc.reason if isinstance(exc, URLError) else exc
                        reason = 'tls_error' if isinstance(cause, ssl.SSLError) else 'timeout' if isinstance(cause, TimeoutError) else 'connection' if isinstance(exc,OSError) else 'invalid_response'
                        failures.append({'exchange':exchange,'quote':quote,'reason':reason})
                        if reason in {'connection','timeout','tls_error'}:
                            break
                    # Two groups per exchange; do not fan out or retry failures.
                    if quote == 'KRW' and any(m.startswith('BTC-') for m in all_markets):
                        time.sleep(.12)
            with self.lock:
                for row in received:
                    key = row["exchange"], row["market"]
                    if row["signal_ts"] >= self.cache.get(key, {}).get("signal_ts", 0):
                        self.cache[key] = row
                self.state = {"status": "complete" if len(received) == requested else "partial",
                              "requested": requested, "received": len(received), "failures": failures}
        finally:
            self.refresh_lock.release()
