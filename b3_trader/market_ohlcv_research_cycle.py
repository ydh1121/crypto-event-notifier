from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .exchange_public import PublicExchangeAdapter, public_exchange
from .market_ohlcv_collector import MarketOhlcvCollector, TIMEFRAMES
from .market_ohlcv_store import MarketOhlcvStore
from .research_control import atomic_json

STATE_PATH = Path("b3_trader/data/research-platform/market-ohlcv-cycle-state.json")
EXCHANGES = ("bithumb", "upbit")
MAX_MARKETS_PER_EXCHANGE_PER_RUN = 8


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _rotate(markets: list[str], cursor: int, limit: int) -> tuple[list[str], int]:
    if not markets:
        return [], 0
    total = len(markets)
    start = max(0, int(cursor)) % total
    picked = [markets[(start + offset) % total] for offset in range(min(total, max(1, int(limit))))]
    return picked, (start + len(picked)) % total


class MarketOhlcvResearchCycle:
    """PAPER-independent bounded history owner for KRW market OHLCV.

    Each run rotates at most eight markets per exchange. The collector bridges
    only the missing window (up to 200 bars/request) and the store retains the
    newest 400 bars per market/timeframe. It does not read or change strategies,
    fills, positions or orders.
    """

    def __init__(
        self,
        path: Path | str = DB_PATH,
        *,
        store: MarketOhlcvStore | None = None,
        adapters: dict[str, PublicExchangeAdapter] | None = None,
        collector: MarketOhlcvCollector | None = None,
        state_path: Path | str = STATE_PATH,
    ) -> None:
        self.path = Path(path)
        self.store = store or MarketOhlcvStore(self.path)
        self.adapters = adapters or {name: public_exchange(name) for name in EXCHANGES}
        self.collector = collector or MarketOhlcvCollector(self.store)
        self.state_path = Path(state_path)
        self._owns_store = store is None

    def close(self) -> None:
        if self._owns_store:
            self.store.close()

    def run_once(self) -> dict[str, Any]:
        started = time.time()
        now = time.time()
        state = _read_state(self.state_path)
        cursors = state.get("cursors") if isinstance(state.get("cursors"), dict) else {}
        next_cursors: dict[str, int] = {}
        exchange_results: dict[str, Any] = {}
        total_requests = 0
        total_written = 0
        total_pruned = 0
        total_failures = 0
        total_processed = 0

        for exchange in EXCHANGES:
            adapter = self.adapters.get(exchange)
            if adapter is None:
                exchange_results[exchange] = {"status": "adapter_missing", "processed": 0, "failures": 1}
                total_failures += 1
                next_cursors[exchange] = int(cursors.get(exchange) or 0)
                continue
            try:
                markets = sorted({row.market for row in adapter.krw_markets() if str(row.market).startswith("KRW-")})
            except Exception as exc:
                exchange_results[exchange] = {
                    "status": "market_list_error",
                    "processed": 0,
                    "failures": 1,
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                }
                total_failures += 1
                next_cursors[exchange] = int(cursors.get(exchange) or 0)
                continue

            picked, cursor = _rotate(
                markets,
                int(cursors.get(exchange) or 0),
                MAX_MARKETS_PER_EXCHANGE_PER_RUN,
            )
            next_cursors[exchange] = cursor
            market_results: list[dict[str, Any]] = []
            for market in picked:
                outcome = self.collector.collect_market(adapter, market, now=now)
                market_results.append(outcome)
                total_requests += int(outcome.get("requests") or 0)
                total_written += int(outcome.get("rows_written") or 0)
                total_pruned += int(outcome.get("rows_pruned") or 0)
                total_failures += int(outcome.get("failures") or 0)
                total_processed += 1
            exchange_results[exchange] = {
                "status": "collected" if picked else "no_markets",
                "universe": len(markets),
                "processed": len(picked),
                "cursor": cursor,
                "markets": market_results,
            }

        atomic_json(
            self.state_path,
            {
                "version": 1,
                "updated_at": time.time(),
                "cursors": next_cursors,
                "max_markets_per_exchange_per_run": MAX_MARKETS_PER_EXCHANGE_PER_RUN,
            },
        )
        return {
            "ok": total_failures == 0,
            "status": "collected" if total_processed else "waiting_for_markets",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "can_modify_strategy": False,
            "network_public_only": True,
            "database_mutation": True,
            "database_scope": "research_market_ohlcv_mx_only",
            "retention_bars_per_market_timeframe": self.store.retention_bars,
            "timeframes": [spec.name for spec in TIMEFRAMES],
            "max_markets_per_exchange_per_run": MAX_MARKETS_PER_EXCHANGE_PER_RUN,
            "markets_processed": total_processed,
            "requests": total_requests,
            "rows_written": total_written,
            "rows_pruned": total_pruned,
            "failures": total_failures,
            "exchanges": exchange_results,
            "elapsed_seconds": round(time.time() - started, 3),
        }
