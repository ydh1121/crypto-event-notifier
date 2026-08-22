from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any

from .asset_strategy import AssetExternalFactors, AssetStrategy
from .assets import AssetProfile, AssetRegistry
from .bithumb_client import BithumbClient
from .config import Settings
from .factors import FactorSnapshot, MarketFactorProvider, _ticker_return_pct, score_basket
from .journal import TradeJournal
from .portfolio import MultiPaperPortfolio
from .realtime import RealtimeMarketCache, public_market_stream
from .risk import ExecutionGuard, OrderRateLimiter, adaptive_order_krw, estimate_sell
from .runtime_config import RuntimeConfigStore
from .runtime_state import RuntimeState
from .strategy import ExternalFactors
from .telegram_notify import TelegramNotifier


@dataclass
class AssetRuntime:
    candles: list[dict[str, Any]] | None = None
    last_candle_refresh: float = 0.0
    last_buy_at: float = 0.0
    last_action: str = ""
    context_score: float = 50.0
    context_details: dict[str, Any] | None = None
    last_context_refresh: float = 0.0


class MultiAssetEngine:
    def __init__(self, *, settings: Settings, registry: AssetRegistry, runtime_config: RuntimeConfigStore, journal: TradeJournal, state: RuntimeState, notifier: TelegramNotifier) -> None:
        self.settings = settings
        self.registry = registry
        self.runtime_config = runtime_config
        self.journal = journal
        self.state = state
        self.notifier = notifier
        self.client = BithumbClient(settings.bithumb_access_key, settings.bithumb_secret_key)
        self.strategy = AssetStrategy()
        self.factor_provider = MarketFactorProvider(self.client, okx_enabled=settings.okx_derivatives_enabled, news_modifier=settings.news_modifier)
        cfg = runtime_config.get()
        self.rate_limiter = OrderRateLimiter(cfg.max_orders_per_minute, cfg.max_orders_per_hour)
        self.execution_guard = ExecutionGuard(max_spread_bps=cfg.max_spread_bps, max_slippage_bps=cfg.max_slippage_bps, btc_flash_crash_pct=cfg.btc_flash_crash_pct, btc_flash_window_candles=cfg.btc_flash_window_candles, rate_limiter=self.rate_limiter)
        self.portfolio = MultiPaperPortfolio(start_krw=settings.paper_start_krw, max_total_exposure_krw=cfg.max_total_exposure_krw, max_daily_loss_pct=cfg.max_daily_loss_pct)
        self.cache = RealtimeMarketCache()
        self._stream = None
        self._stream_markets: tuple[str, ...] = ()
        self._asset_runtime: dict[str, AssetRuntime] = {}
        self._prices: dict[str, float] = {}
        self._btc: list[dict[str, Any]] | None = None
        self._eth: list[dict[str, Any]] | None = None
        self._last_major_refresh = 0.0
        self._factor_snapshot = FactorSnapshot(ExternalFactors(), {"fallback": "initial-neutral"})
        self._last_external_refresh = 0.0
        self._available_markets: set[str] = set()
        self._available_markets_at = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _refresh_available_markets(self) -> None:
        now = time.time()
        if self._available_markets and now - self._available_markets_at < 3600: return
        rows = self.client.market_all()
        self._available_markets = {str(row.get("market", "")).upper() for row in rows if str(row.get("market", "")).upper().startswith("KRW-")}
        self._available_markets_at = now

    def _ensure_stream(self, profiles: list[AssetProfile]) -> None:
        if not self.settings.websocket_enabled: return
        markets = tuple(sorted({self.settings.btc_market, self.settings.eth_market, *(profile.market for profile in profiles if profile.enabled)}))
        if markets == self._stream_markets and self._stream is not None: return
        if self._stream is not None: self._stream.stop()
        self._stream = public_market_stream(list(markets), self.cache)
        self._stream.start()
        self._stream_markets = markets

    def _refresh_major_candles(self, now: float, cfg: Any) -> None:
        if self._btc is None or self._eth is None or now - self._last_major_refresh >= cfg.candle_refresh_seconds:
            self._btc = self.client.candles_minutes(self.settings.btc_market, unit=self.settings.candle_unit_minutes, count=self.settings.candle_count)
            self._eth = self.client.candles_minutes(self.settings.eth_market, unit=self.settings.candle_unit_minutes, count=self.settings.candle_count)
            self._last_major_refresh = now

    def _refresh_global_factors(self, now: float, cfg: Any) -> None:
        if now - self._last_external_refresh >= cfg.external_refresh_seconds:
            self._factor_snapshot = self.factor_provider.snapshot()
            self._last_external_refresh = now

    def _context_for(self, profile: AssetProfile, runtime: AssetRuntime, now: float, cfg: Any) -> tuple[float, dict[str, Any]]:
        if runtime.context_details is not None and now - runtime.last_context_refresh < cfg.external_refresh_seconds:
            return runtime.context_score, runtime.context_details
        base_alt = float(self._factor_snapshot.factors.alt_breadth)
        if not profile.related_markets:
            details = {"mode": profile.context_mode, "fallback": "alt_breadth", "score": base_alt, "markets": []}
            runtime.context_score, runtime.context_details, runtime.last_context_refresh = base_alt, details, now
            return base_alt, details
        self._refresh_available_markets()
        markets = [market for market in profile.related_markets if market in self._available_markets and market != profile.market]
        if not markets:
            details = {"mode": profile.context_mode, "fallback": "alt_breadth", "score": base_alt, "markets": []}
            runtime.context_score, runtime.context_details, runtime.last_context_refresh = base_alt, details, now
            return base_alt, details
        rows = self.client.tickers(markets)
        returns = [_ticker_return_pct(row) for row in rows]
        major_return = float(self._factor_snapshot.details.get("major_24h_return_pct") or 0.0)
        result = score_basket(returns, markets, relative_to_pct=major_return, breadth_weight=30.0, return_weight=4.5)
        details = {"mode": profile.context_mode, **asdict(result)}
        runtime.context_score, runtime.context_details, runtime.last_context_refresh = result.score, details, now
        return result.score, details

    def _market_payload(self, market: str) -> tuple[dict[str, Any], dict[str, Any], float]:
        orderbook = self.cache.latest("orderbook", market, max_age_seconds=20.0) or self.client.orderbook(market)
        ticker = self.cache.latest("ticker", market, max_age_seconds=20.0) or self.client.ticker(market)
        return orderbook, ticker, float(ticker["trade_price"])

    def _configure_risk(self, cfg: Any) -> None:
        self.rate_limiter.per_minute = max(1, int(cfg.max_orders_per_minute))
        self.rate_limiter.per_hour = max(self.rate_limiter.per_minute, int(cfg.max_orders_per_hour))
        self.execution_guard.max_spread_bps = float(cfg.max_spread_bps)
        self.execution_guard.max_slippage_bps = float(cfg.max_slippage_bps)
        self.execution_guard.btc_flash_crash_pct = float(cfg.btc_flash_crash_pct)
        self.execution_guard.btc_flash_window_candles = int(cfg.btc_flash_window_candles)
        self.portfolio.max_total_exposure_krw = float(cfg.max_total_exposure_krw)
        self.portfolio.max_daily_loss_pct = float(cfg.max_daily_loss_pct)

    def _notify_action_change(self, profile: AssetProfile, runtime: AssetRuntime, payload: dict[str, Any]) -> None:
        action = str(payload["action"])
        previous = runtime.last_action
        runtime.last_action = action
        if action == previous or action not in {"BUY_CANDIDATE", "RISK_OFF", "WAIT_PULLBACK"}: return
        self.notifier.safe_send(f"[{profile.symbol}] {action}\n가격 {payload['price']}\nRegime {payload['regime_score']} / Entry {payload['entry_score']}\nContext {payload['context_score']}", event_key=f"action-{profile.market}-{action}", min_interval_seconds=600)

    def _analyze_asset(self, profile: AssetProfile, now: float, cfg: Any) -> None:
        runtime = self._asset_runtime.setdefault(profile.market, AssetRuntime())
        if runtime.candles is None or now - runtime.last_candle_refresh >= cfg.candle_refresh_seconds:
            runtime.candles = self.client.candles_minutes(profile.market, unit=self.settings.candle_unit_minutes, count=self.settings.candle_count)
            runtime.last_candle_refresh = now
        orderbook, _ticker, price = self._market_payload(profile.market)
        self._prices[profile.market] = price
        context_score, context_details = self._context_for(profile, runtime, now, cfg)
        external = AssetExternalFactors(
            alt_breadth=float(self._factor_snapshot.factors.alt_breadth),
            context_strength=context_score,
            derivatives_risk_on=float(self._factor_snapshot.factors.derivatives_risk_on),
            news_modifier=max(-20.0, min(20.0, float(self._factor_snapshot.factors.news_modifier) + float(profile.news_modifier))),
        )
        signal = self.strategy.score(self._btc or [], self._eth or [], runtime.candles, orderbook, external)
        position = self.portfolio.position(profile.market)
        payload = {
            "ts": now, "market": profile.market, "symbol": profile.symbol, "price": price,
            "context_mode": profile.context_mode, "context_score": round(context_score, 2), "context_details": context_details,
            **asdict(signal),
            "position": {"volume": round(position.volume, 12), "avg_price": round(position.avg_price, 12), "value_krw": round(position.volume * price, 2)},
            "profile": profile.to_dict(),
        }
        self.state.set_asset(profile.market, payload)
        self.journal.record_snapshot(market=profile.market, price=price, regime_score=signal.regime_score, entry_score=signal.entry_score, action=signal.action, payload=payload, ts=now)
        self._notify_action_change(profile, runtime, payload)

        if self.state.kill_switch and position.volume > 0:
            sell_price, slip = estimate_sell(orderbook, position.volume)
            if not isfinite(sell_price): sell_price = price
            fill = self.portfolio.sell_all(profile.market, sell_price, f"manual kill switch, estimated_slippage_bps={slip if isfinite(slip) else 'unknown'}")
            if fill:
                self.journal.record_fill(mode="paper", market=profile.market, fill=fill, ts=now)
                self.notifier.safe_send(f"[{profile.symbol}] PAPER 강제청산\n{fill.krw:,.0f}원 @ {fill.price}", event_key=f"kill-fill-{profile.market}-{int(now)}")
            return

        min_regime = profile.min_regime_score if profile.min_regime_score is not None else cfg.min_regime_score
        min_entry = profile.min_entry_score if profile.min_entry_score is not None else cfg.min_entry_score
        base_order = profile.order_krw if profile.order_krw is not None else cfg.default_order_krw
        max_position = profile.max_position_krw if profile.max_position_krw is not None else cfg.default_max_position_krw
        if not self.state.paused and not self.state.kill_switch and signal.action == "BUY_CANDIDATE" and signal.regime_score >= min_regime and signal.entry_score >= min_entry and now - runtime.last_buy_at >= cfg.buy_cooldown_seconds:
            order_krw = adaptive_order_krw(base_order, regime_score=signal.regime_score, entry_score=signal.entry_score, min_multiplier=cfg.adaptive_size_min_multiplier, max_multiplier=cfg.adaptive_size_max_multiplier)
            risk = self.execution_guard.evaluate_buy(orderbook=orderbook, btc_candles=self._btc or [], order_krw=order_krw, now=now)
            if not risk.allowed:
                self.journal.record_event("execution_risk_blocked", {"market": profile.market, **risk.to_dict()}, ts=now)
            else:
                fill_price = risk.estimated_fill_price if isfinite(risk.estimated_fill_price) else price
                allowed, reason = self.portfolio.can_buy(market=profile.market, price=fill_price, order_krw=order_krw, max_position_krw=max_position, prices=self._prices)
                if allowed:
                    fill = self.portfolio.buy(market=profile.market, price=fill_price, order_krw=order_krw, reason=f"regime={signal.regime_score}, entry={signal.entry_score}, context={context_score:.1f}, spread_bps={risk.spread_bps}, slippage_bps={risk.estimated_slippage_bps}", max_position_krw=max_position, prices=self._prices)
                    runtime.last_buy_at = now
                    self.rate_limiter.record(now)
                    self.journal.record_fill(mode="paper", market=profile.market, fill=fill, ts=now)
                    self.notifier.safe_send(f"[{profile.symbol}] PAPER 매수\n{fill.krw:,.0f}원 @ {fill.price}\nRegime {signal.regime_score} / Entry {signal.entry_score}", event_key=f"fill-{profile.market}-{int(now)}")
                else:
                    self.journal.record_event("paper_buy_blocked", {"market": profile.market, "reason": reason, "price": fill_price, "order_krw": order_krw}, ts=now)

        position = self.portfolio.position(profile.market)
        if signal.regime_score < 45.0 and position.volume > 0:
            sell_price, slip = estimate_sell(orderbook, position.volume)
            if not isfinite(sell_price): sell_price = price
            fill = self.portfolio.sell_all(profile.market, sell_price, f"risk_off regime={signal.regime_score}, estimated_slippage_bps={slip if isfinite(slip) else 'unknown'}")
            if fill:
                self.rate_limiter.record(now)
                self.journal.record_fill(mode="paper", market=profile.market, fill=fill, ts=now)
                self.notifier.safe_send(f"[{profile.symbol}] PAPER 리스크오프 청산\n{fill.krw:,.0f}원 @ {fill.price}", event_key=f"riskoff-fill-{profile.market}-{int(now)}")

    def run(self) -> None:
        self.notifier.safe_send("Crypto Auto Trader 로컬 엔진 시작 (PAPER)")
        try:
            while not self._stop.is_set():
                started = time.time()
                try:
                    cfg = self.runtime_config.get()
                    self._configure_risk(cfg)
                    profiles = self.registry.list(enabled_only=True)
                    self._ensure_stream(profiles)
                    now = time.time()
                    self._refresh_major_candles(now, cfg)
                    self._refresh_global_factors(now, cfg)
                    enabled_markets = {profile.market for profile in profiles}
                    for existing in list(self.state.assets):
                        if existing not in enabled_markets: self.state.remove_asset(existing)
                    for profile in profiles:
                        try:
                            self._analyze_asset(profile, now, cfg)
                        except Exception as exc:
                            self.state.set_error(exc, scope=f"asset:{profile.market}")
                            self.journal.record_event("asset_loop_error", {"market": profile.market, "error": type(exc).__name__, "message": str(exc)}, ts=now)
                            self.state.set_asset(profile.market, {"ts": now, "market": profile.market, "symbol": profile.symbol, "context_mode": profile.context_mode, "action": "ERROR", "error": str(exc)})
                    self.state.set_portfolio(self.portfolio.snapshot(self._prices))
                except Exception as exc:
                    self.state.set_error(exc, scope="engine")
                    self.journal.record_event("engine_error", {"error": type(exc).__name__, "message": str(exc)})
                cfg = self.runtime_config.get()
                elapsed = time.time() - started
                self._stop.wait(max(0.5, cfg.poll_seconds - elapsed))
        finally:
            if self._stream is not None: self._stream.stop()
            self.notifier.safe_send("Crypto Auto Trader 로컬 엔진 종료")

    def start(self) -> None:
        if self._thread and self._thread.is_alive(): return
        self._thread = threading.Thread(target=self.run, name="multi-asset-engine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive(): self._thread.join(timeout=10)
