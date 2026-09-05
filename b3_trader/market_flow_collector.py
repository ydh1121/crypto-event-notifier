from __future__ import annotations

import time
from typing import Any

from .exchange_public import PublicExchangeAdapter
from .market_flow_store import MarketFlowStore

TRADE_PAGE_SIZE = 200
MAX_TRADE_PAGES_PER_MARKET = 3
FLOW_WINDOW_SECONDS = 300.0


def _epoch_seconds(value: Any) -> float:
    try:
        raw = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if raw > 100_000_000_000_000:
        return raw / 1_000_000.0
    if raw > 100_000_000_000:
        return raw / 1_000.0
    return raw


def _normalize_trade(exchange: str, market: str, row: dict[str, Any], received_at: float) -> dict[str, Any] | None:
    side = str(row.get("ask_bid") or row.get("side") or "").upper()
    if side in {"BUY", "BID"}:
        side = "BID"
    elif side in {"SELL", "ASK"}:
        side = "ASK"
    else:
        return None
    try:
        price = float(row.get("trade_price") or 0.0)
        volume = float(row.get("trade_volume") or 0.0)
        trade_ts = _epoch_seconds(row.get("timestamp") or row.get("trade_timestamp"))
    except (TypeError, ValueError):
        return None
    sequential_id = row.get("sequential_id")
    if not sequential_id or price <= 0 or volume <= 0 or trade_ts <= 0:
        return None
    return {
        "exchange": exchange,
        "market": market,
        "sequential_id": str(sequential_id),
        "trade_ts": trade_ts,
        "trade_price": price,
        "trade_volume": volume,
        "quote_volume": price * volume,
        "aggressor_side": side,
        "side_source": "exchange",
        "received_at": received_at,
    }


def _imbalance(bid: float, ask: float) -> float | None:
    total = float(bid) + float(ask)
    if total <= 0:
        return None
    return (float(bid) - float(ask)) / total * 100.0


def _normalize_orderbook(exchange: str, market: str, row: dict[str, Any], received_at: float) -> dict[str, Any]:
    units = row.get("orderbook_units") if isinstance(row.get("orderbook_units"), list) else []
    normalized: list[tuple[float, float, float, float]] = []
    for item in units:
        if not isinstance(item, dict):
            continue
        try:
            bid_price = float(item.get("bid_price") or 0.0)
            ask_price = float(item.get("ask_price") or 0.0)
            bid_size = float(item.get("bid_size") or 0.0)
            ask_size = float(item.get("ask_size") or 0.0)
        except (TypeError, ValueError):
            continue
        if bid_price <= 0 or ask_price <= 0:
            continue
        normalized.append((bid_price, ask_price, max(0.0, bid_size), max(0.0, ask_size)))
    best_bid = normalized[0][0] if normalized else None
    best_ask = normalized[0][1] if normalized else None
    mid = ((best_bid + best_ask) / 2.0) if best_bid and best_ask else 0.0
    spread_bps = ((best_ask - best_bid) / mid * 10_000.0) if mid > 0 else None
    top5 = normalized[:5]
    bid5 = sum(price * size for price, _, size, _ in top5)
    ask5 = sum(price * size for _, price, _, size in top5)
    bid_all = sum(price * size for price, _, size, _ in normalized)
    ask_all = sum(price * size for _, price, _, size in normalized)
    return {
        "exchange": exchange,
        "market": market,
        "snapshot_ts": received_at,
        "source_ts": _epoch_seconds(row.get("timestamp")),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_bps": spread_bps,
        "bid_depth_quote_5": bid5,
        "ask_depth_quote_5": ask5,
        "imbalance_5": _imbalance(bid5, ask5),
        "bid_depth_quote_all": bid_all,
        "ask_depth_quote_all": ask_all,
        "imbalance_all": _imbalance(bid_all, ask_all),
        "received_at": received_at,
    }


class MarketFlowCollector:
    """Bounded REST flow observer with explicit continuity semantics.

    Exchange-provided ASK/BID is the only accepted aggressor side in this
    stage. Recent-trade pagination is bounded. If the stored continuous anchor
    cannot be reached within that bound, new observations are retained but CVD
    continuity is not advanced.
    """

    def __init__(self, store: MarketFlowStore) -> None:
        self.store = store

    def collect_market(self, adapter: PublicExchangeAdapter, market: str, *, now: float | None = None) -> dict[str, Any]:
        received_at = float(now or time.time())
        exchange = str(adapter.exchange)
        cursor_state = self.store.cursor(exchange, market)
        previous_covered = float(cursor_state.get("covered_through_ts") or 0.0)
        pages = 0
        requests = 0
        normalized: list[dict[str, Any]] = []
        page_cursor: str | None = None
        seen_cursors: set[str] = set()
        oldest_ts = 0.0
        latest_ts = 0.0
        source_failures = 0
        source_error = ""

        for _ in range(MAX_TRADE_PAGES_PER_MARKET):
            try:
                page = adapter.recent_trades(market, count=TRADE_PAGE_SIZE, cursor=page_cursor)
                requests += 1
            except Exception as exc:
                source_failures += 1
                source_error = f"{type(exc).__name__}: {exc}"[:300]
                break
            pages += 1
            if not page:
                break
            page_rows: list[dict[str, Any]] = []
            for row in page:
                if not isinstance(row, dict):
                    continue
                item = _normalize_trade(exchange, market, row, received_at)
                if item is not None:
                    page_rows.append(item)
            normalized.extend(page_rows)
            if page_rows:
                page_oldest = min(float(row["trade_ts"]) for row in page_rows)
                page_latest = max(float(row["trade_ts"]) for row in page_rows)
                oldest_ts = page_oldest if oldest_ts <= 0 else min(oldest_ts, page_oldest)
                latest_ts = max(latest_ts, page_latest)
            if len(page) < TRADE_PAGE_SIZE:
                break
            if previous_covered > 0 and oldest_ts > 0 and oldest_ts <= previous_covered:
                break
            last = page[-1] if isinstance(page[-1], dict) else {}
            next_cursor = str(last.get("sequential_id") or "")
            if not next_cursor or next_cursor in seen_cursors:
                break
            seen_cursors.add(next_cursor)
            page_cursor = next_cursor

        inserted = self.store.insert_trades(normalized)
        pruned = self.store.prune_trades(exchange, market)

        if oldest_ts > 0 and latest_ts > 0:
            if previous_covered <= 0:
                cycle_complete = True
                coverage_start = oldest_ts
                covered_through = latest_ts
            elif oldest_ts <= previous_covered:
                cycle_complete = True
                coverage_start = float(cursor_state.get("coverage_start_ts") or oldest_ts)
                covered_through = max(previous_covered, latest_ts)
            else:
                cycle_complete = False
                coverage_start = float(cursor_state.get("coverage_start_ts") or 0.0)
                covered_through = previous_covered
            last_seen = max(float(cursor_state.get("last_seen_trade_ts") or 0.0), latest_ts)
        else:
            cycle_complete = False
            coverage_start = float(cursor_state.get("coverage_start_ts") or 0.0)
            covered_through = previous_covered
            last_seen = float(cursor_state.get("last_seen_trade_ts") or 0.0)

        self.store.upsert_cursor(
            exchange,
            market,
            {
                "coverage_start_ts": coverage_start,
                "covered_through_ts": covered_through,
                "last_seen_trade_ts": last_seen,
                "last_cycle_complete": cycle_complete,
                "last_pages": pages,
                "last_rows": len(normalized),
                "updated_at": received_at,
            },
        )

        book: dict[str, Any] = {}
        try:
            raw_book = adapter.orderbook(market)
            requests += 1
            book = _normalize_orderbook(exchange, market, raw_book if isinstance(raw_book, dict) else {}, received_at)
            self.store.insert_orderbook(book)
        except Exception as exc:
            source_failures += 1
            if not source_error:
                source_error = f"{type(exc).__name__}: {exc}"[:300]

        window_end = covered_through
        window_start = max(coverage_start, window_end - FLOW_WINDOW_SECONDS) if window_end > 0 else 0.0
        stats = self.store.trade_stats(exchange, market, start_ts=window_start, end_ts=window_end) if window_end > 0 else {
            "trade_count": 0,
            "buy_volume": 0.0,
            "sell_volume": 0.0,
            "buy_quote_volume": 0.0,
            "sell_quote_volume": 0.0,
            "delta_volume": 0.0,
            "delta_quote": 0.0,
            "delta_pct": None,
            "side_coverage_pct": None,
        }
        recent_window_complete = bool(
            coverage_start > 0
            and window_end > 0
            and coverage_start <= window_end - FLOW_WINDOW_SECONDS
            and covered_through >= window_end
            and cycle_complete
        )
        observed_cvd = self.store.observed_cvd_quote(
            exchange,
            market,
            anchor_ts=coverage_start,
            end_ts=covered_through,
        ) if coverage_start > 0 and covered_through >= coverage_start else 0.0
        feature = {
            "exchange": exchange,
            "market": market,
            "feature_ts": received_at,
            "window_seconds": max(0.0, window_end - window_start),
            "window_start_ts": window_start,
            "window_end_ts": window_end,
            **stats,
            "observed_cvd_quote": observed_cvd,
            "cvd_anchor_ts": coverage_start,
            "continuity_complete": recent_window_complete,
            "spread_bps": book.get("spread_bps"),
            "imbalance_5": book.get("imbalance_5"),
            "imbalance_all": book.get("imbalance_all"),
            "source": "public_rest",
            "received_at": received_at,
            "feature_version": 1,
        }
        self.store.insert_feature(feature)

        return {
            "ok": source_failures == 0,
            "status": "collected" if normalized or book else "source_error",
            "exchange": exchange,
            "market": market,
            "requests": requests,
            "pages": pages,
            "rows_observed": len(normalized),
            "rows_inserted": inserted,
            "rows_pruned": pruned,
            "coverage_start_ts": coverage_start,
            "covered_through_ts": covered_through,
            "last_seen_trade_ts": last_seen,
            "cycle_continuity_complete": cycle_complete,
            "recent_5m_continuity_complete": recent_window_complete,
            "trade_count": int(stats.get("trade_count") or 0),
            "delta_quote": float(stats.get("delta_quote") or 0.0),
            "delta_pct": stats.get("delta_pct"),
            "observed_cvd_quote": observed_cvd,
            "cvd_scope": "local_contiguous_observation",
            "side_source": "exchange",
            "side_coverage_pct": stats.get("side_coverage_pct"),
            "orderbook": {
                "spread_bps": book.get("spread_bps"),
                "imbalance_5": book.get("imbalance_5"),
                "imbalance_all": book.get("imbalance_all"),
                "bid_depth_quote_5": book.get("bid_depth_quote_5"),
                "ask_depth_quote_5": book.get("ask_depth_quote_5"),
            },
            "failures": source_failures,
            "error": source_error,
            "paper_only": True,
            "shadow_only": True,
            "score_wired": False,
            "can_place_orders": False,
        }
