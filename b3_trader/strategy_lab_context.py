"""Existing OHLCV and event observations joined without generating missing returns."""
from __future__ import annotations

import sqlite3
from typing import Any


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
        # Only events with an actual response for this coin enter its history.
        events = conn.execute("""SELECT e.event_id,e.event_type,e.title,e.source_url,e.source_ts
            FROM research_intelligence_events e WHERE EXISTS (
                SELECT 1 FROM research_intelligence_event_responses r
                WHERE r.event_id=e.event_id AND r.exchange=? AND r.market=?)
            ORDER BY e.source_ts DESC LIMIT 20""", (exchange, market)).fetchall()
        for event in events:
            item = dict(event)
            item["event_ts"] = item.pop("source_ts")
            responses: dict[str, Any] = {}
            # Match the provider and event timestamp of the coin observation; never
            # combine unlike baselines or providers merely because labels match.
            for c in conn.execute("""SELECT * FROM research_intelligence_event_responses
                WHERE event_id=? AND exchange=? AND market=? ORDER BY captured_at DESC""", (item["event_id"], exchange, market)):
                h = c["horizon_label"]
                if h in responses:
                    continue
                response: dict[str, Any] = {"coin": c["return_pct"], "btc": None, "eth": None,
                    "baseline_ts": c["baseline_trade_ts"], "baseline_price": c["baseline_price"],
                    "target_ts": c["target_trade_ts"], "target_price": c["target_price"], "captured_at": c["captured_at"]}
                for name, symbol in (("btc", "KRW-BTC"), ("eth", "KRW-ETH")):
                    benchmark = conn.execute("""SELECT return_pct FROM research_intelligence_event_responses
                        WHERE event_id=? AND exchange=? AND market=? AND horizon_label=? AND provider_id=? AND event_ts=?""",
                        (item["event_id"], exchange, symbol, h, c["provider_id"], c["event_ts"])).fetchone()
                    if benchmark:
                        response[name] = benchmark[0]
                responses[h] = response
            item["responses"] = responses
            result["events"].append(item)
    return result
