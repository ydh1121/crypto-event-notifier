"""Existing OHLCV and event observations joined without generating missing returns."""
from __future__ import annotations

import sqlite3
from typing import Any

from .event_reaction_view import read_event_context


def read_coin_context(conn: sqlite3.Connection, tables: set[str], exchange: str, market: str) -> dict[str, Any]:
    result: dict[str, Any] = {"price_history": [], "relative": None, "events": []}
    if "research_market_ohlcv_mx" in tables:
        candles = {}
        for symbol in dict.fromkeys((market, "KRW-BTC", "KRW-ETH")):
            candles[symbol] = {r["candle_ts"]: float(r["close"]) for r in conn.execute("""
                SELECT candle_ts,close FROM research_market_ohlcv_mx
                WHERE exchange=? AND market=? AND timeframe='1h' AND is_closed=1
                ORDER BY candle_ts DESC LIMIT 400""", (exchange, symbol)) if r["close"] > 0}
        coin = candles[market]
        result["price_history"] = [{"ts": ts + 3600, "price": price} for ts, price in sorted(coin.items())]
        if coin:
            anchor = max(coin)
            windows = []
            for label, seconds in (("1h", 3600), ("4h", 14400), ("1d", 86400), ("7d", 604800)):
                row = {"horizon": label, "baseline_ts": anchor - seconds + 3600, "target_ts": anchor + 3600}
                for name, symbol in (("coin", market), ("btc", "KRW-BTC"), ("eth", "KRW-ETH")):
                    baseline, target = candles[symbol].get(anchor - seconds), candles[symbol].get(anchor)
                    row[name] = (target / baseline - 1) * 100 if baseline and target else None
                row["vs_btc_pp"] = row["coin"] - row["btc"] if row["coin"] is not None and row["btc"] is not None else None
                row["vs_eth_pp"] = row["coin"] - row["eth"] if row["coin"] is not None and row["eth"] is not None else None
                windows.append(row)
            result["relative"] = {"source": "closed_1h_ohlcv", "source_ts": anchor + 3600, "windows": windows}
    if {"research_intelligence_events", "research_intelligence_event_responses"}.issubset(tables):
        result["events"] = read_event_context(conn, exchange, market)
    return result
