"""Read existing manual holdings for local planning; never instantiate a store.

The holdings journal is separate from PAPER. No exchange/ticker fallback, schema
creation, price request or holding mutation belongs in this projection.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import sqlite3
import time

from .user_tools import holding_api_market, holding_base_currency, holding_quote_currency


def resolve_holdings_path(paper: Path, explicit: Path | None = None) -> tuple[Path | None, str]:
    if explicit is not None:
        return explicit.resolve(), "explicit"
    paper = paper.resolve()
    if paper.parent.name != "data" or paper.parent.parent.name != "b3_trader":
        return None, "configuration_required"
    checkout = paper.parent.parent.parent
    value = os.environ.get("B3_JOURNAL_DB")
    source = "environment" if value is not None else "default"
    if value is None:
        try:
            # Read only the configured non-secret journal path. Do not import
            # Settings/load_dotenv or copy environment contents into a report.
            with (checkout / ".env").open(encoding="utf-8-sig") as stream:
                for line in stream:
                    match = re.match(r"\s*(?:export\s+)?B3_JOURNAL_DB\s*=\s*(.*?)\s*$", line)
                    if match:
                        value, source = match[1], "project_setting"
            if value is not None:
                if value[:1] in {"'", '"'}:
                    quote = value[0]
                    end = value.find(quote, 1)
                    tail = value[end+1:].strip() if end >= 0 else ''
                    if end < 0 or (tail and not tail.startswith('#')):
                        return None, "configuration_required"
                    value = value[1:end]
                else:
                    value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError):
            return None, "configuration_required"
    # Interpolation/multiline values need an explicit path, never a guessed DB.
    if value is not None and (not value or '$' in value or '\n' in value or '\r' in value):
        return None, "configuration_required"
    path = Path(value) if value is not None else Path("b3_trader/data/crypto_trader.sqlite3")
    return (path if path.is_absolute() else checkout / path).resolve(), source


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def read_holdings(path: Path | None, prices: list[dict], *, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    result = {"status": "configuration_required", "observed_at": now, "holdings": []}
    if path is None:
        return result
    if not path.is_file():
        return {**result, "status": "db_missing"}
    try:
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(manual_holdings)")}
            if not columns:
                return {**result, "status": "table_missing"}
            if not {"market", "volume", "avg_price", "updated_ts"} <= columns:
                return {**result, "status": "schema_mismatch"}
            exchange = "exchange" if "exchange" in columns else "NULL AS exchange"
            rows = [dict(r) for r in conn.execute(
                f"SELECT market,volume,avg_price,{exchange},updated_ts FROM manual_holdings ORDER BY market")]
        finally:
            conn.close()
    except (OSError, sqlite3.Error):
        return {**result, "status": "read_failed"}
    quotes = {}
    for p in prices:
        price, ts = _number(p.get("price")), _number(p.get("signal_ts"))
        key = p.get("exchange"), p.get("market")
        if price is not None and price > 0 and ts is not None and 0 < ts <= now:
            if ts >= quotes.get(key, {}).get("signal_ts", 0):
                quotes[key] = {**p, "price": price, "signal_ts": ts}
    items = []
    for row in rows:
        market = str(row["market"] or "")
        exchange = str(row["exchange"] or "").strip().lower()
        if exchange not in {"bithumb", "upbit"}:
            exchange = None
        try:
            quote, symbol, api_market = holding_quote_currency(market), holding_base_currency(market), holding_api_market(market)
        except ValueError:
            quote, symbol, api_market = None, market, None
        quantity, average = _number(row["volume"]), _number(row["avg_price"])
        valid = quantity is not None and quantity >= 0 and average is not None and average >= 0 and (quantity == 0 or average > 0)
        price_row = quotes.get((exchange, api_market), {}) if exchange and api_market else {}
        price, source_ts = _number(price_row.get("price")), _number(price_row.get("signal_ts"))
        if price is None or price <= 0 or source_ts is None or not 0 < source_ts <= now:
            price, source_ts = None, None
        stale = source_ts is None or now - source_ts > 1200
        invested = quantity * average if valid else None
        value = quantity * price if valid and price is not None else None
        pnl = value - invested if value is not None else None
        fx_row = quotes.get((exchange, "KRW-BTC"), {}) if quote == "BTC" else {}
        fx = 1 if quote == "KRW" else fx_row.get("price")
        fx_ts = source_ts if quote == "KRW" else fx_row.get("signal_ts")
        value_krw = value * fx if value is not None and fx is not None else None
        items.append({"key": f"{exchange or 'unknown'}|{market}|{quote or 'unknown'}",
            "exchange": exchange, "market": market, "api_market": api_market, "quote_currency": quote, "symbol": symbol,
            "volume": quantity, "avg_price": average, "updated_ts": _number(row["updated_ts"]),
            "valid": valid, "closed": valid and quantity == 0, "current_price": price,
            "price_ts": source_ts, "price_stale": stale, "invested_quote": invested,
            "price_source": price_row.get("price_source", "local_signal"),
            "value_krw": value_krw, "quote_to_krw": fx, "conversion_ts": fx_ts,
            "valuation_stale": stale or fx_ts is None or now - fx_ts > 1200,
            "value_quote": value, "unrealized_pnl_quote": pnl,
            "unrealized_pnl_pct": pnl / invested * 100 if pnl is not None and invested else None,
            "planning_available": bool(valid and quantity > 0 and exchange and quote == "KRW")})
    active = [h for h in items if not h["closed"]]
    priced = [h for h in active if h["valid"] and h["value_krw"] is not None]
    complete = len(priced) == len(active)
    # Today's BTC/KRW rate is not the historical acquisition cost in KRW.
    pnl_complete = complete and all(h["quote_currency"] == "KRW" for h in active)
    return {**result, "status": "read", "holdings": items, "holding_count": len(active),
        "closed_count": len(items) - len(active), "priced_count": len(priced),
        "valuation_complete": complete, "valuation_stale": any(h["valuation_stale"] for h in priced),
        "known_value_krw": sum(h["value_krw"] for h in priced),
        "value_krw": sum(h["value_krw"] for h in priced) if complete else None,
        "pnl_krw": sum(h["unrealized_pnl_quote"] for h in priced) if pnl_complete else None}
