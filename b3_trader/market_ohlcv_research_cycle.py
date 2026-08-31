from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH
from .exchange_public import PublicExchangeAdapter, public_exchange
from .market_cross_exchange_gap import MarketCrossExchangeGapEngine
from .market_domestic_premium import MarketDomesticPremiumEngine
from .market_flow_collector import MarketFlowCollector
from .market_flow_reaction import MarketFlowReactionStore
from .market_flow_store import MarketFlowStore
from .market_ohlcv_collector import MarketOhlcvCollector, TIMEFRAMES
from .market_ohlcv_store import MarketOhlcvStore
from .market_price_flow_divergence import MarketPriceFlowDivergenceStore
from .market_relative_strength import BENCHMARK_MARKETS, MarketRelativeStrengthEngine
from .research_control import atomic_json

STATE_PATH = Path("b3_trader/data/research-platform/market-ohlcv-cycle-state.json")
EXCHANGES = ("bithumb", "upbit")
MAX_MARKETS_PER_EXCHANGE_PER_RUN = 8
MAX_FLOW_MARKETS_PER_EXCHANGE_PER_RUN = 4
MAX_PREMIUM_MARKETS_PER_RUN = 1


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _rotate(markets: list[str], cursor: int, limit: int) -> tuple[list[str], int]:
    if not markets or limit <= 0:
        return [], 0 if not markets else max(0, int(cursor)) % len(markets)
    total = len(markets)
    start = max(0, int(cursor)) % total
    picked = [markets[(start + offset) % total] for offset in range(min(total, max(1, int(limit))))]
    return picked, (start + len(picked)) % total


def _pick_markets(markets: list[str], cursor: int) -> tuple[list[str], int]:
    """Always keep BTC/ETH benchmark history fresh inside the same eight-market cap."""
    benchmark_set = set(BENCHMARK_MARKETS)
    benchmarks = [market for market in BENCHMARK_MARKETS if market in markets]
    rotating = [market for market in markets if market not in benchmark_set]
    remaining = max(0, MAX_MARKETS_PER_EXCHANGE_PER_RUN - len(benchmarks))
    picked_rotating, next_cursor = _rotate(rotating, cursor, remaining)
    picked = [*benchmarks, *picked_rotating]
    if not benchmarks and len(picked) < MAX_MARKETS_PER_EXCHANGE_PER_RUN:
        picked, next_cursor = _rotate(markets, cursor, MAX_MARKETS_PER_EXCHANGE_PER_RUN)
    return picked[:MAX_MARKETS_PER_EXCHANGE_PER_RUN], next_cursor


def _premium_candidate_order(market: str) -> tuple[int, str]:
    """Seed verified runtime evidence with BTC/ETH before rotating other markets."""
    value = str(market).upper()
    if value == "KRW-BTC":
        return (0, value)
    if value == "KRW-ETH":
        return (1, value)
    return (2, value)


class MarketOhlcvResearchCycle:
    """PAPER-independent bounded market-history/flow feature owner.

    Each run keeps KRW-BTC and KRW-ETH fresh and rotates the remaining OHLCV
    slots, for at most eight markets per exchange. Up to four of those markets
    also receive bounded public recent-trade/orderbook observation. Trade flow
    only accepts exchange-provided aggressor side and retains explicit REST
    continuity metadata, so partial observations cannot masquerade as complete
    CVD. Relative strength, conservative domestic exchange gap and verified
    foreign-reference premium remain shadow/read-only research features.

    After the OHLCV refresh, local-only price-flow divergence evidence is joined
    from completed OHLCV plus continuous WebSocket trade/orderbook windows. The
    cycle then evaluates only forward candles that occur after each completed
    divergence signal, producing 15m/1h/4h/1d reaction evidence and aggregate
    coefficients. Neither stage is wired to scoring, PAPER decisions or orders.
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
        self.flow_store = MarketFlowStore(self.path)
        self.price_flow_divergence = MarketPriceFlowDivergenceStore(self.path)
        self.flow_reaction = MarketFlowReactionStore(self.path)
        self.adapters = adapters or {name: public_exchange(name) for name in EXCHANGES}
        self.collector = collector or MarketOhlcvCollector(self.store)
        self.flow_collector = MarketFlowCollector(self.flow_store)
        self.relative_strength = MarketRelativeStrengthEngine(self.store.conn)
        self.cross_exchange_gap = MarketCrossExchangeGapEngine(self.store.conn)
        self.domestic_premium = MarketDomesticPremiumEngine(self.store.conn)
        self.state_path = Path(state_path)
        self._owns_store = store is None

    def close(self) -> None:
        self.flow_reaction.close()
        self.price_flow_divergence.close()
        self.flow_store.close()
        if self._owns_store:
            self.store.close()

    def run_once(self) -> dict[str, Any]:
        started = time.time()
        now = time.time()
        state = _read_state(self.state_path)
        cursors = state.get("cursors") if isinstance(state.get("cursors"), dict) else {}
        premium_cursor = int(state.get("premium_cursor") or 0)
        next_cursors: dict[str, int] = {}
        exchange_results: dict[str, Any] = {}
        market_names: dict[str, dict[str, str]] = {}
        total_requests = 0
        total_written = 0
        total_pruned = 0
        total_failures = 0
        total_processed = 0
        total_relative_features = 0
        total_flow_requests = 0
        total_flow_rows_inserted = 0
        total_flow_failures = 0
        total_flow_processed = 0

        for exchange in EXCHANGES:
            adapter = self.adapters.get(exchange)
            if adapter is None:
                exchange_results[exchange] = {"status": "adapter_missing", "processed": 0, "failures": 1}
                market_names[exchange] = {}
                total_failures += 1
                next_cursors[exchange] = int(cursors.get(exchange) or 0)
                continue
            try:
                market_rows = [row for row in adapter.krw_markets() if str(row.market).startswith("KRW-")]
                markets = sorted({row.market for row in market_rows})
                market_names[exchange] = {str(row.market): str(row.name or "") for row in market_rows}
            except Exception as exc:
                exchange_results[exchange] = {
                    "status": "market_list_error",
                    "processed": 0,
                    "failures": 1,
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                }
                market_names[exchange] = {}
                total_failures += 1
                next_cursors[exchange] = int(cursors.get(exchange) or 0)
                continue

            picked, cursor = _pick_markets(markets, int(cursors.get(exchange) or 0))
            next_cursors[exchange] = cursor
            flow_picked = set(picked[:MAX_FLOW_MARKETS_PER_EXCHANGE_PER_RUN])
            market_results: list[dict[str, Any]] = []
            for market in picked:
                outcome = self.collector.collect_market(adapter, market, now=now)
                if market in flow_picked:
                    try:
                        flow = self.flow_collector.collect_market(adapter, market, now=time.time())
                    except Exception as exc:
                        flow = {
                            "ok": False,
                            "status": "flow_observation_error",
                            "exchange": exchange,
                            "market": market,
                            "requests": 0,
                            "rows_inserted": 0,
                            "failures": 1,
                            "error": f"{type(exc).__name__}: {exc}"[:300],
                            "paper_only": True,
                            "shadow_only": True,
                            "score_wired": False,
                            "can_place_orders": False,
                        }
                    outcome["flow"] = flow
                    total_flow_requests += int(flow.get("requests") or 0)
                    total_flow_rows_inserted += int(flow.get("rows_inserted") or 0)
                    total_flow_failures += int(flow.get("failures") or 0)
                    total_flow_processed += 1
                market_results.append(outcome)
                total_requests += int(outcome.get("requests") or 0)
                total_written += int(outcome.get("rows_written") or 0)
                total_pruned += int(outcome.get("rows_pruned") or 0)
                total_failures += int(outcome.get("failures") or 0)
                total_processed += 1

            try:
                relative = self.relative_strength.compute_exchange(exchange, universe_count=len(markets))
            except Exception as exc:
                total_failures += 1
                relative = {
                    "ok": False,
                    "status": "relative_strength_error",
                    "features_written": 0,
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                    "paper_only": True,
                    "can_place_orders": False,
                }
            total_relative_features += int(relative.get("features_written") or 0)
            exchange_results[exchange] = {
                "status": "collected" if picked else "no_markets",
                "universe": len(markets),
                "processed": len(picked),
                "flow_processed": len(flow_picked),
                "cursor": cursor,
                "benchmarks_prioritized": [market for market in BENCHMARK_MARKETS if market in picked],
                "markets": market_results,
                "relative_strength": relative,
            }

        try:
            gap_result = self.cross_exchange_gap.compute(
                bithumb_names=market_names.get("bithumb", {}),
                upbit_names=market_names.get("upbit", {}),
                now=now,
            )
        except Exception as exc:
            total_failures += 1
            gap_result = {
                "ok": False,
                "status": "cross_exchange_gap_error",
                "rows_written": 0,
                "gap_ready_rows": 0,
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "paper_only": True,
                "score_wired": False,
                "can_place_orders": False,
            }

        premium_candidates = sorted(
            [
                str(row["market"])
                for row in self.store.conn.execute(
                    """SELECT market FROM research_market_cross_exchange_gap_mx
                       WHERE identity_verified=1 AND gap_ready=1"""
                ).fetchall()
            ],
            key=_premium_candidate_order,
        )
        premium_picked, next_premium_cursor = _rotate(
            premium_candidates,
            premium_cursor,
            MAX_PREMIUM_MARKETS_PER_RUN,
        )
        if premium_picked:
            try:
                premium_result = self.domestic_premium.collect_market(premium_picked[0], now=now)
            except Exception as exc:
                total_failures += 1
                premium_result = {
                    "ok": False,
                    "status": "domestic_premium_error",
                    "market": premium_picked[0],
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                    "paper_only": True,
                    "score_wired": False,
                    "can_place_orders": False,
                }
        else:
            premium_result = {
                "ok": True,
                "status": "waiting_for_gap_ready_market",
                "market": "",
                "verified_sources": 0,
                "paper_only": True,
                "score_wired": False,
                "can_place_orders": False,
            }
            next_premium_cursor = 0

        try:
            price_flow_result = self.price_flow_divergence.compute_pending(now=time.time())
        except Exception as exc:
            total_failures += 1
            price_flow_result = {
                "ok": False,
                "status": "price_flow_divergence_error",
                "candidates_scanned": 0,
                "ready_written": 0,
                "waiting_written": 0,
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "paper_only": True,
                "score_wired": False,
                "can_place_orders": False,
            }

        try:
            flow_reaction_result = self.flow_reaction.compute_pending(now=time.time())
        except Exception as exc:
            total_failures += 1
            flow_reaction_result = {
                "ok": False,
                "status": "flow_reaction_error",
                "signals_scanned": 0,
                "reactions_processed": 0,
                "ready_written": 0,
                "waiting_written": 0,
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "paper_only": True,
                "score_wired": False,
                "can_place_orders": False,
            }

        atomic_json(
            self.state_path,
            {
                "version": 7,
                "updated_at": time.time(),
                "cursors": next_cursors,
                "premium_cursor": next_premium_cursor,
                "max_markets_per_exchange_per_run": MAX_MARKETS_PER_EXCHANGE_PER_RUN,
                "max_flow_markets_per_exchange_per_run": MAX_FLOW_MARKETS_PER_EXCHANGE_PER_RUN,
                "max_premium_markets_per_run": MAX_PREMIUM_MARKETS_PER_RUN,
                "benchmark_markets": list(BENCHMARK_MARKETS),
                "market_flow": {
                    "aggressor_side": "exchange_provided_only",
                    "cvd_scope": "local_contiguous_observation",
                    "score_wired": False,
                },
                "cross_exchange_gap": {
                    "identity_basis": "symbol+official_name_exact",
                    "source_timeframe": "1m",
                },
                "domestic_premium": {
                    "domestic_identity": "same_verified_provider_id",
                    "foreign_identity": "coingecko_exact_venue_pair",
                    "score_wired": False,
                },
                "price_flow_divergence": {
                    "join_contract": "exact_aligned_closed_ohlcv+continuous_ws_trade+continuous_ws_orderbook",
                    "heuristic_version": 1,
                    "score_wired": False,
                },
                "flow_reaction": {
                    "join_contract": "forward_only_exact_contiguous_closed_ohlcv_after_signal_window",
                    "horizons": ["15m", "1h", "4h", "1d"],
                    "feature_version": 1,
                    "score_wired": False,
                },
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
            "database_scope": "market_history_research_tables_only",
            "retention_bars_per_market_timeframe": self.store.retention_bars,
            "timeframes": [spec.name for spec in TIMEFRAMES],
            "benchmark_markets": list(BENCHMARK_MARKETS),
            "max_markets_per_exchange_per_run": MAX_MARKETS_PER_EXCHANGE_PER_RUN,
            "max_flow_markets_per_exchange_per_run": MAX_FLOW_MARKETS_PER_EXCHANGE_PER_RUN,
            "max_premium_markets_per_run": MAX_PREMIUM_MARKETS_PER_RUN,
            "markets_processed": total_processed,
            "requests": total_requests,
            "rows_written": total_written,
            "rows_pruned": total_pruned,
            "relative_strength_features_written": total_relative_features,
            "market_flow": {
                "processed": total_flow_processed,
                "requests": total_flow_requests,
                "rows_inserted": total_flow_rows_inserted,
                "failures": total_flow_failures,
                "aggressor_side": "exchange_provided_only",
                "cvd_scope": "local_contiguous_observation",
                "paper_only": True,
                "score_wired": False,
                "can_place_orders": False,
            },
            "cross_exchange_gap": gap_result,
            "domestic_premium": premium_result,
            "price_flow_divergence": price_flow_result,
            "flow_reaction": flow_reaction_result,
            "failures": total_failures,
            "exchanges": exchange_results,
            "elapsed_seconds": round(time.time() - started, 3),
        }
