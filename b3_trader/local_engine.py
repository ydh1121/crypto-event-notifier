from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
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


def _score_word(value: float) -> str:
    value = float(value)
    if value < 40:
        return "매우 나쁨"
    if value < 55:
        return "좋지 않음"
    if value < 65:
        return "보통"
    if value < 75:
        return "좋음"
    return "매우 좋음"


def _risk_reason_text(reason: str) -> str:
    text = reason.lower()
    if "spread" in text:
        return "매수·매도 가격 차이가 너무 벌어져 있어 이번 매수는 건너뜁니다."
    if "slippage" in text:
        return "지금 주문하면 예상보다 비싸게 살 가능성이 커서 이번 매수는 건너뜁니다."
    if "btc" in text or "flash" in text:
        return "비트코인이 갑자기 크게 내려가고 있어 새 매수를 잠시 막았습니다."
    if "rate" in text or "order" in text:
        return "짧은 시간에 주문이 너무 많아질 수 있어 잠시 기다립니다."
    return "안전 조건을 통과하지 못해 이번 매수는 건너뜁니다."


@dataclass
class AssetRuntime:
    candles: list[dict[str, Any]] | None = None
    last_candle_refresh: float = 0.0
    last_buy_at: float = 0.0
    last_action: str = ""
    last_snapshot_at: float = 0.0
    context_score: float = 50.0
    context_details: dict[str, Any] | None = None
    last_context_refresh: float = 0.0


class MultiAssetEngine:
    def __init__(
        self,
        *,
        settings: Settings,
        registry: AssetRegistry,
        runtime_config: RuntimeConfigStore,
        journal: TradeJournal,
        state: RuntimeState,
        notifier: TelegramNotifier,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.runtime_config = runtime_config
        self.journal = journal
        self.state = state
        self.notifier = notifier
        self.client = BithumbClient(
            settings.bithumb_access_key,
            settings.bithumb_secret_key,
        )
        self.strategy = AssetStrategy()
        self.factor_provider = MarketFactorProvider(
            self.client,
            okx_enabled=settings.okx_derivatives_enabled,
            news_modifier=settings.news_modifier,
        )
        cfg = runtime_config.get()
        self.rate_limiter = OrderRateLimiter(
            cfg.max_orders_per_minute,
            cfg.max_orders_per_hour,
        )
        self.execution_guard = ExecutionGuard(
            max_spread_bps=cfg.max_spread_bps,
            max_slippage_bps=cfg.max_slippage_bps,
            btc_flash_crash_pct=cfg.btc_flash_crash_pct,
            btc_flash_window_candles=cfg.btc_flash_window_candles,
            rate_limiter=self.rate_limiter,
        )
        self.portfolio = MultiPaperPortfolio(
            start_krw=settings.paper_start_krw,
            max_total_exposure_krw=cfg.max_total_exposure_krw,
            max_daily_loss_pct=cfg.max_daily_loss_pct,
        )
        restored_fills = journal.paper_fills_chronological()
        self.portfolio.restore_from_fills(restored_fills)
        if restored_fills:
            journal.record_event(
                "paper_portfolio_restored",
                {
                    "fills": len(restored_fills),
                    "cash_krw": round(self.portfolio.cash_krw, 2),
                    "open_positions": sum(
                        1 for item in self.portfolio.positions.values() if item.volume > 0
                    ),
                },
            )

        self.cache = RealtimeMarketCache()
        self._stream = None
        self._stream_markets: tuple[str, ...] = ()
        self._asset_runtime: dict[str, AssetRuntime] = {}
        self._prices: dict[str, float] = {}
        self._btc: list[dict[str, Any]] | None = None
        self._eth: list[dict[str, Any]] | None = None
        self._last_major_refresh = 0.0
        self._factor_snapshot = FactorSnapshot(
            ExternalFactors(),
            {"fallback": "initial-neutral"},
        )
        self._last_external_refresh = 0.0
        self._last_portfolio_snapshot = 0.0
        self._last_daily_summary: date | None = None
        self._available_markets: set[str] = set()
        self._available_markets_at = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _refresh_available_markets(self) -> None:
        now = time.time()
        if self._available_markets and now - self._available_markets_at < 3600:
            return
        rows = self.client.market_all()
        self._available_markets = {
            str(row.get("market", "")).upper()
            for row in rows
            if str(row.get("market", "")).upper().startswith("KRW-")
        }
        self._available_markets_at = now

    def _ensure_stream(self, profiles: list[AssetProfile]) -> None:
        if not self.settings.websocket_enabled:
            return
        markets = tuple(
            sorted(
                {
                    self.settings.btc_market,
                    self.settings.eth_market,
                    *(profile.market for profile in profiles if profile.enabled),
                }
            )
        )
        if markets == self._stream_markets and self._stream is not None:
            return
        if self._stream is not None:
            self._stream.stop()
        self._stream = public_market_stream(list(markets), self.cache)
        self._stream.start()
        self._stream_markets = markets

    def _refresh_major_candles(self, now: float, cfg: Any) -> None:
        if (
            self._btc is None
            or self._eth is None
            or now - self._last_major_refresh >= cfg.candle_refresh_seconds
        ):
            self._btc = self.client.candles_minutes(
                self.settings.btc_market,
                unit=self.settings.candle_unit_minutes,
                count=self.settings.candle_count,
            )
            self._eth = self.client.candles_minutes(
                self.settings.eth_market,
                unit=self.settings.candle_unit_minutes,
                count=self.settings.candle_count,
            )
            self._last_major_refresh = now

    def _refresh_global_factors(self, now: float, cfg: Any) -> None:
        if now - self._last_external_refresh >= cfg.external_refresh_seconds:
            self._factor_snapshot = self.factor_provider.snapshot()
            self._last_external_refresh = now
            self.state.set_market(
                {
                    "ts": now,
                    "factors": asdict(self._factor_snapshot.factors),
                    "details": self._factor_snapshot.details,
                }
            )

    def _context_for(
        self,
        profile: AssetProfile,
        runtime: AssetRuntime,
        now: float,
        cfg: Any,
    ) -> tuple[float, dict[str, Any]]:
        if (
            runtime.context_details is not None
            and now - runtime.last_context_refresh < cfg.external_refresh_seconds
        ):
            return runtime.context_score, runtime.context_details

        base_alt = float(self._factor_snapshot.factors.alt_breadth)
        if not profile.related_markets:
            details = {
                "mode": profile.context_mode,
                "fallback": "alt_breadth",
                "score": base_alt,
                "markets": [],
            }
            runtime.context_score = base_alt
            runtime.context_details = details
            runtime.last_context_refresh = now
            return base_alt, details

        self._refresh_available_markets()
        markets = [
            market
            for market in profile.related_markets
            if market in self._available_markets and market != profile.market
        ]
        if not markets:
            details = {
                "mode": profile.context_mode,
                "fallback": "alt_breadth",
                "score": base_alt,
                "markets": [],
            }
            runtime.context_score = base_alt
            runtime.context_details = details
            runtime.last_context_refresh = now
            return base_alt, details

        rows = self.client.tickers(markets)
        returns = [_ticker_return_pct(row) for row in rows]
        major_return = float(
            self._factor_snapshot.details.get("major_24h_return_pct") or 0.0
        )
        result = score_basket(
            returns,
            markets,
            relative_to_pct=major_return,
            breadth_weight=30.0,
            return_weight=4.5,
        )
        details = {"mode": profile.context_mode, **asdict(result)}
        runtime.context_score = result.score
        runtime.context_details = details
        runtime.last_context_refresh = now
        return result.score, details

    def _market_payload(
        self,
        market: str,
    ) -> tuple[dict[str, Any], dict[str, Any], float]:
        orderbook = self.cache.latest(
            "orderbook",
            market,
            max_age_seconds=20.0,
        ) or self.client.orderbook(market)
        ticker = self.cache.latest(
            "ticker",
            market,
            max_age_seconds=20.0,
        ) or self.client.ticker(market)
        return orderbook, ticker, float(ticker["trade_price"])

    def _configure_risk(self, cfg: Any) -> None:
        self.rate_limiter.per_minute = max(1, int(cfg.max_orders_per_minute))
        self.rate_limiter.per_hour = max(
            self.rate_limiter.per_minute,
            int(cfg.max_orders_per_hour),
        )
        self.execution_guard.max_spread_bps = float(cfg.max_spread_bps)
        self.execution_guard.max_slippage_bps = float(cfg.max_slippage_bps)
        self.execution_guard.btc_flash_crash_pct = float(cfg.btc_flash_crash_pct)
        self.execution_guard.btc_flash_window_candles = int(
            cfg.btc_flash_window_candles
        )
        self.portfolio.max_total_exposure_krw = float(cfg.max_total_exposure_krw)
        self.portfolio.max_daily_loss_pct = float(cfg.max_daily_loss_pct)

    def _notify_action_change(
        self,
        profile: AssetProfile,
        runtime: AssetRuntime,
        payload: dict[str, Any],
    ) -> None:
        action = str(payload["action"])
        previous = runtime.last_action
        runtime.last_action = action
        if action == previous or action not in {
            "BUY_CANDIDATE",
            "RISK_OFF",
            "WAIT_PULLBACK",
        }:
            return

        market_score = float(payload.get("regime_score") or 0.0)
        entry_score = float(payload.get("entry_score") or 0.0)
        context_score = float(payload.get("context_score") or 0.0)
        suggested = payload.get("suggested_entry") or {}

        if action == "BUY_CANDIDATE":
            amount = float(suggested.get("amount_krw") or 0.0)
            account_pct = float(suggested.get("account_pct") or 0.0)
            message = (
                f"[{profile.symbol}] 매수 후보\n"
                f"현재가 {payload['price']}원\n"
                f"추천 진입 비중: 약 {account_pct:.1f}% ({amount:,.0f}원)\n\n"
                f"전체 시장 분위기: {_score_word(market_score)} ({market_score:.0f}/100)\n"
                f"지금 매수 타이밍: {_score_word(entry_score)} ({entry_score:.0f}/100)\n"
                f"비슷한 코인 흐름: {_score_word(context_score)} ({context_score:.0f}/100)"
            )
        elif action == "WAIT_PULLBACK":
            message = (
                f"[{profile.symbol}] 가격이 조금 내려오길 기다리는 중\n"
                f"현재가 {payload['price']}원\n"
                f"시장 분위기는 {_score_word(market_score)} ({market_score:.0f}/100)이지만 "
                f"매수 타이밍은 {_score_word(entry_score)} ({entry_score:.0f}/100)입니다.\n"
                "지금 따라 사기보다 더 좋은 가격을 기다립니다."
            )
        else:
            message = (
                f"[{profile.symbol}] 지금은 새로 사지 않는 구간\n"
                f"현재가 {payload['price']}원\n"
                f"전체 시장 분위기: {_score_word(market_score)} ({market_score:.0f}/100)\n"
                f"지금 매수 타이밍: {_score_word(entry_score)} ({entry_score:.0f}/100)\n"
                f"비슷한 코인 흐름: {_score_word(context_score)} ({context_score:.0f}/100)\n"
                "시장이 좋아질 때까지 지켜봅니다."
            )

        self.notifier.safe_send(
            message,
            event_key=f"action-{profile.market}-{action}",
            min_interval_seconds=600,
        )

    @staticmethod
    def _diagnostics(
        signal: Any,
        external: AssetExternalFactors,
        context_details: dict[str, Any],
        min_regime: float,
        min_entry: float,
    ) -> dict[str, Any]:
        fib_pct = (
            float(signal.fib_retrace) * 100.0
            if signal.fib_retrace is not None
            else None
        )
        return {
            "summary": signal.reason,
            "thresholds": {
                "regime": float(min_regime),
                "entry": float(min_entry),
            },
            "regime": {
                "btc_return_pct": signal.btc_return_pct,
                "eth_return_pct": signal.eth_return_pct,
                "eth_vs_btc_pct": signal.eth_vs_btc_pct,
                "asset_vs_majors_pct": signal.asset_vs_majors_pct,
                "alt_breadth": external.alt_breadth,
                "context_strength": external.context_strength,
                "derivatives_risk_on": external.derivatives_risk_on,
                "news_modifier": external.news_modifier,
            },
            "entry": {
                "asset_return_pct": signal.asset_return_pct,
                "pullback_pct": signal.pullback_pct,
                "fib_retrace_pct": round(fib_pct, 2) if fib_pct is not None else None,
                "orderbook_imbalance": signal.orderbook_imbalance,
                "volatility_pct": signal.volatility_pct,
            },
            "context": context_details,
            "checks": {
                "regime_pass": signal.regime_score >= min_regime,
                "entry_pass": signal.entry_score >= min_entry,
                "risk_off": signal.regime_score < 50.0,
                "waiting_for_pullback": signal.regime_score >= 70.0
                and signal.entry_score < 50.0,
            },
        }

    def _analyze_asset(self, profile: AssetProfile, now: float, cfg: Any) -> None:
        runtime = self._asset_runtime.setdefault(profile.market, AssetRuntime())
        if (
            runtime.candles is None
            or now - runtime.last_candle_refresh >= cfg.candle_refresh_seconds
        ):
            runtime.candles = self.client.candles_minutes(
                profile.market,
                unit=self.settings.candle_unit_minutes,
                count=self.settings.candle_count,
            )
            runtime.last_candle_refresh = now

        orderbook, _ticker, price = self._market_payload(profile.market)
        self._prices[profile.market] = price
        context_score, context_details = self._context_for(
            profile,
            runtime,
            now,
            cfg,
        )
        external = AssetExternalFactors(
            alt_breadth=float(self._factor_snapshot.factors.alt_breadth),
            context_strength=context_score,
            derivatives_risk_on=float(
                self._factor_snapshot.factors.derivatives_risk_on
            ),
            news_modifier=max(
                -20.0,
                min(
                    20.0,
                    float(self._factor_snapshot.factors.news_modifier)
                    + float(profile.news_modifier),
                ),
            ),
        )
        signal = self.strategy.score(
            self._btc or [],
            self._eth or [],
            runtime.candles,
            orderbook,
            external,
        )
        position = self.portfolio.position(profile.market)
        min_regime = (
            profile.min_regime_score
            if profile.min_regime_score is not None
            else cfg.min_regime_score
        )
        min_entry = (
            profile.min_entry_score
            if profile.min_entry_score is not None
            else cfg.min_entry_score
        )
        base_order = (
            profile.order_krw
            if profile.order_krw is not None
            else cfg.default_order_krw
        )
        max_position = (
            profile.max_position_krw
            if profile.max_position_krw is not None
            else cfg.default_max_position_krw
        )

        suggested_raw = adaptive_order_krw(
            base_order,
            regime_score=signal.regime_score,
            entry_score=signal.entry_score,
            min_multiplier=cfg.adaptive_size_min_multiplier,
            max_multiplier=cfg.adaptive_size_max_multiplier,
        )
        current_position_value = max(0.0, position.volume * price)
        remaining_position_room = max(0.0, float(max_position) - current_position_value)
        suggested_order = min(
            float(suggested_raw),
            remaining_position_room,
            max(0.0, float(self.portfolio.cash_krw)),
        )
        account_equity = max(0.0, float(self.portfolio.equity(self._prices)))
        suggested_account_pct = (
            suggested_order / account_equity * 100.0 if account_equity > 0 else 0.0
        )
        suggested_position_pct = (
            suggested_order / float(max_position) * 100.0 if float(max_position) > 0 else 0.0
        )
        projected_position_pct = (
            (current_position_value + suggested_order) / float(max_position) * 100.0
            if float(max_position) > 0
            else 0.0
        )

        payload = {
            "ts": now,
            "market": profile.market,
            "symbol": profile.symbol,
            "price": price,
            "context_mode": profile.context_mode,
            "context_score": round(context_score, 2),
            "context_details": context_details,
            **asdict(signal),
            "suggested_entry": {
                "amount_krw": round(suggested_order, 2),
                "account_pct": round(suggested_account_pct, 2),
                "asset_limit_pct": round(suggested_position_pct, 2),
                "projected_asset_limit_pct": round(projected_position_pct, 2),
                "max_position_krw": round(float(max_position), 2),
            },
            "diagnostics": self._diagnostics(
                signal,
                external,
                context_details,
                min_regime,
                min_entry,
            ),
            "position": {
                "volume": round(position.volume, 12),
                "avg_price": round(position.avg_price, 12),
                "value_krw": round(position.volume * price, 2),
            },
            "profile": profile.to_dict(),
        }
        self.state.set_asset(profile.market, payload)

        snapshot_interval = max(30.0, float(cfg.candle_refresh_seconds))
        if now - runtime.last_snapshot_at >= snapshot_interval:
            self.journal.record_snapshot(
                market=profile.market,
                price=price,
                regime_score=signal.regime_score,
                entry_score=signal.entry_score,
                action=signal.action,
                payload=payload,
                ts=now,
            )
            runtime.last_snapshot_at = now

        self._notify_action_change(profile, runtime, payload)

        if self.state.kill_switch and position.volume > 0:
            sell_price, slip = estimate_sell(orderbook, position.volume)
            if not isfinite(sell_price):
                sell_price = price
            fill = self.portfolio.sell_all(
                profile.market,
                sell_price,
                "manual kill switch, "
                f"estimated_slippage_bps={slip if isfinite(slip) else 'unknown'}",
            )
            if fill:
                self.journal.record_fill(
                    mode="paper",
                    market=profile.market,
                    fill=fill,
                    ts=now,
                )
                self.notifier.safe_send(
                    f"[{profile.symbol}] 가상 보유분을 긴급 정리했습니다\n"
                    f"약 {fill.krw:,.0f}원 · 체결가 {fill.price}원",
                    event_key=f"kill-fill-{profile.market}-{int(now)}",
                )
            return

        if (
            not self.state.paused
            and not self.state.kill_switch
            and signal.action == "BUY_CANDIDATE"
            and signal.regime_score >= min_regime
            and signal.entry_score >= min_entry
            and now - runtime.last_buy_at >= cfg.buy_cooldown_seconds
        ):
            order_krw = adaptive_order_krw(
                base_order,
                regime_score=signal.regime_score,
                entry_score=signal.entry_score,
                min_multiplier=cfg.adaptive_size_min_multiplier,
                max_multiplier=cfg.adaptive_size_max_multiplier,
            )
            risk = self.execution_guard.evaluate_buy(
                orderbook=orderbook,
                btc_candles=self._btc or [],
                order_krw=order_krw,
                now=now,
            )
            if not risk.allowed:
                risk_payload = {"market": profile.market, **risk.to_dict()}
                self.journal.record_event(
                    "execution_risk_blocked",
                    risk_payload,
                    ts=now,
                )
                reason = risk.reasons[0] if risk.reasons else "risk guard"
                self.notifier.safe_send(
                    f"[{profile.symbol}] 매수 후보였지만 이번에는 건너뜁니다\n"
                    f"{_risk_reason_text(reason)}",
                    event_key=f"risk-block-{profile.market}-{reason}",
                    min_interval_seconds=1800,
                    disable_notification=True,
                )
            else:
                fill_price = (
                    risk.estimated_fill_price
                    if isfinite(risk.estimated_fill_price)
                    else price
                )
                allowed, reason = self.portfolio.can_buy(
                    market=profile.market,
                    price=fill_price,
                    order_krw=order_krw,
                    max_position_krw=max_position,
                    prices=self._prices,
                )
                if allowed:
                    fill = self.portfolio.buy(
                        market=profile.market,
                        price=fill_price,
                        order_krw=order_krw,
                        reason=(
                            f"regime={signal.regime_score}, "
                            f"entry={signal.entry_score}, "
                            f"context={context_score:.1f}, "
                            f"spread_bps={risk.spread_bps}, "
                            f"slippage_bps={risk.estimated_slippage_bps}"
                        ),
                        max_position_krw=max_position,
                        prices=self._prices,
                    )
                    runtime.last_buy_at = now
                    self.rate_limiter.record(now)
                    self.journal.record_fill(
                        mode="paper",
                        market=profile.market,
                        fill=fill,
                        ts=now,
                    )
                    actual_account_pct = (
                        fill.krw / account_equity * 100.0 if account_equity > 0 else 0.0
                    )
                    self.notifier.safe_send(
                        f"[{profile.symbol}] 가상 매수했습니다\n"
                        f"{fill.krw:,.0f}원 · 체결가 {fill.price}원\n"
                        f"이번 진입 비중 약 {actual_account_pct:.1f}%\n"
                        f"시장 분위기 {_score_word(signal.regime_score)} ({signal.regime_score:.0f}/100) · "
                        f"매수 타이밍 {_score_word(signal.entry_score)} ({signal.entry_score:.0f}/100)",
                        event_key=f"fill-{profile.market}-{int(now)}",
                    )
                else:
                    self.journal.record_event(
                        "paper_buy_blocked",
                        {
                            "market": profile.market,
                            "reason": reason,
                            "price": fill_price,
                            "order_krw": order_krw,
                        },
                        ts=now,
                    )

        position = self.portfolio.position(profile.market)
        if signal.regime_score < 45.0 and position.volume > 0:
            sell_price, slip = estimate_sell(orderbook, position.volume)
            if not isfinite(sell_price):
                sell_price = price
            fill = self.portfolio.sell_all(
                profile.market,
                sell_price,
                f"risk_off regime={signal.regime_score}, "
                "estimated_sell_slippage_bps="
                f"{slip if isfinite(slip) else 'unknown'}",
            )
            if fill:
                self.rate_limiter.record(now)
                self.journal.record_fill(
                    mode="paper",
                    market=profile.market,
                    fill=fill,
                    ts=now,
                )
                self.notifier.safe_send(
                    f"[{profile.symbol}] 시장이 많이 약해져 가상 보유분을 정리했습니다\n"
                    f"약 {fill.krw:,.0f}원 · 체결가 {fill.price}원\n"
                    f"시장 분위기 {signal.regime_score:.0f}/100",
                    event_key=f"riskoff-fill-{profile.market}-{int(now)}",
                )

    def _record_portfolio_state(self, now: float, cfg: Any) -> None:
        snapshot = self.portfolio.snapshot(self._prices)
        snapshot["start_krw"] = float(self.settings.paper_start_krw)
        snapshot["return_pct"] = (
            round(
                (
                    float(snapshot["equity_krw"])
                    / float(self.settings.paper_start_krw)
                    - 1.0
                )
                * 100.0,
                4,
            )
            if self.settings.paper_start_krw > 0
            else 0.0
        )
        self.state.set_portfolio(snapshot)
        if now - self._last_portfolio_snapshot >= max(
            30.0,
            float(cfg.candle_refresh_seconds),
        ):
            self.journal.record_portfolio_snapshot(snapshot, ts=now)
            self._last_portfolio_snapshot = now

    def _maybe_daily_summary(self) -> None:
        now = datetime.now()
        today = now.date()
        if now.hour < 21 or self._last_daily_summary == today:
            return
        stats = self.journal.paper_trade_stats()
        portfolio = self.portfolio.snapshot(self._prices)
        start = float(self.settings.paper_start_krw)
        equity = float(portfolio.get("equity_krw") or start)
        return_pct = (equity / start - 1.0) * 100.0 if start > 0 else 0.0
        self.notifier.safe_send(
            "오늘 가상매매 결과\n"
            f"가상 계좌 총액 {equity:,.0f}원 ({return_pct:+.2f}%)\n"
            f"확정 손익 {stats['realized_pnl_krw']:+,.0f}원\n"
            f"끝난 거래 {stats['closed_trades']}회 · 이긴 비율 {stats['win_rate_pct']:.1f}%\n"
            f"현재 코인에 들어간 금액 {float(portfolio.get('exposure_krw') or 0):,.0f}원",
            event_key=f"daily-summary-{today.isoformat()}",
        )
        self._last_daily_summary = today

    def run(self) -> None:
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
                        if existing not in enabled_markets:
                            self.state.remove_asset(existing)
                    for profile in profiles:
                        try:
                            self._analyze_asset(profile, now, cfg)
                        except Exception as exc:
                            self.state.set_error(exc, scope=f"asset:{profile.market}")
                            self.journal.record_event(
                                "asset_loop_error",
                                {
                                    "market": profile.market,
                                    "error": type(exc).__name__,
                                    "message": str(exc),
                                },
                                ts=now,
                            )
                            self.state.set_asset(
                                profile.market,
                                {
                                    "ts": now,
                                    "market": profile.market,
                                    "symbol": profile.symbol,
                                    "context_mode": profile.context_mode,
                                    "action": "ERROR",
                                    "error": str(exc),
                                },
                            )
                            self.notifier.safe_send(
                                f"[{profile.symbol}] 분석에 문제가 생겼습니다\n"
                                "프로그램은 계속 실행 중이며 잠시 뒤 다시 시도합니다.",
                                event_key=(
                                    f"asset-error-{profile.market}-{type(exc).__name__}"
                                ),
                                min_interval_seconds=1800,
                            )
                    self._record_portfolio_state(now, cfg)
                    self._maybe_daily_summary()
                except Exception as exc:
                    self.state.set_error(exc, scope="engine")
                    self.journal.record_event(
                        "engine_error",
                        {"error": type(exc).__name__, "message": str(exc)},
                    )
                    self.notifier.safe_send(
                        "자동매매 모니터에 문제가 생겼습니다.\n잠시 뒤 자동으로 다시 시도합니다.",
                        event_key=f"engine-error-{type(exc).__name__}",
                        min_interval_seconds=1800,
                    )
                cfg = self.runtime_config.get()
                elapsed = time.time() - started
                self._stop.wait(max(0.5, cfg.poll_seconds - elapsed))
        finally:
            if self._stream is not None:
                self._stream.stop()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self.run,
            name="multi-asset-engine",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
