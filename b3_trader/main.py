from __future__ import annotations

import json
import time
from dataclasses import asdict
from math import isfinite
from typing import Any

from dotenv import load_dotenv

from .bithumb_client import BithumbClient
from .config import Settings
from .factors import FactorSnapshot, MarketFactorProvider
from .journal import TradeJournal
from .paper import PaperAccount
from .realtime import (
    RealtimeMarketCache,
    private_account_stream,
    public_market_stream,
)
from .risk import (
    ExecutionGuard,
    OrderRateLimiter,
    adaptive_order_krw,
    estimate_sell,
)
from .strategy import B3Strategy, ExternalFactors


def run() -> None:
    load_dotenv()
    settings = Settings()
    client = BithumbClient(settings.bithumb_access_key, settings.bithumb_secret_key)
    strategy = B3Strategy()
    account = PaperAccount(
        start_krw=settings.paper_start_krw,
        max_position_krw=settings.paper_max_position_krw,
        max_daily_loss_pct=settings.max_daily_loss_pct,
    )
    journal = TradeJournal(settings.journal_db)
    factor_provider = MarketFactorProvider(
        client,
        okx_enabled=settings.okx_derivatives_enabled,
        news_modifier=settings.news_modifier,
    )
    rate_limiter = OrderRateLimiter(
        settings.max_orders_per_minute,
        settings.max_orders_per_hour,
    )
    execution_guard = ExecutionGuard(
        max_spread_bps=settings.max_spread_bps,
        max_slippage_bps=settings.max_slippage_bps,
        btc_flash_crash_pct=settings.btc_flash_crash_pct,
        btc_flash_window_candles=settings.btc_flash_window_candles,
        rate_limiter=rate_limiter,
    )

    realtime_cache = RealtimeMarketCache()
    public_stream = None
    private_stream = None

    if settings.websocket_enabled:
        public_stream = public_market_stream(
            [settings.market, settings.btc_market, settings.eth_market],
            realtime_cache,
        )
        public_stream.start()

    if (
        settings.private_websocket_enabled
        and settings.bithumb_access_key
        and settings.bithumb_secret_key
    ):
        private_stream = private_account_stream(
            [settings.market],
            realtime_cache,
            client.authorization_header,
        )
        private_stream.start()

    if settings.live_trading_armed:
        print("WARNING: live credentials are armed, but Phase 3 runner remains PAPER-ONLY.")

    print(
        json.dumps(
            {
                "mode": "PAPER",
                "phase": 3,
                "market": settings.market,
                "websocket": bool(public_stream),
                "private_websocket": bool(private_stream),
                "okx_derivatives": settings.okx_derivatives_enabled,
                "journal_db": settings.journal_db,
                "execution_guard": {
                    "max_spread_bps": settings.max_spread_bps,
                    "max_slippage_bps": settings.max_slippage_bps,
                    "btc_flash_crash_pct": settings.btc_flash_crash_pct,
                    "max_orders_per_minute": settings.max_orders_per_minute,
                    "max_orders_per_hour": settings.max_orders_per_hour,
                },
            },
            ensure_ascii=False,
        )
    )

    last_buy_at = 0.0
    last_candle_refresh = 0.0
    last_external_refresh = 0.0
    btc: list[dict[str, Any]] | None = None
    eth: list[dict[str, Any]] | None = None
    b3: list[dict[str, Any]] | None = None
    factor_snapshot = FactorSnapshot(ExternalFactors(), {"fallback": "initial-neutral"})

    try:
        while True:
            started = time.time()
            try:
                now = time.time()

                if (
                    btc is None
                    or eth is None
                    or b3 is None
                    or now - last_candle_refresh >= settings.candle_refresh_seconds
                ):
                    btc = client.candles_minutes(
                        settings.btc_market,
                        unit=settings.candle_unit_minutes,
                        count=settings.candle_count,
                    )
                    eth = client.candles_minutes(
                        settings.eth_market,
                        unit=settings.candle_unit_minutes,
                        count=settings.candle_count,
                    )
                    b3 = client.candles_minutes(
                        settings.market,
                        unit=settings.candle_unit_minutes,
                        count=settings.candle_count,
                    )
                    last_candle_refresh = now

                if now - last_external_refresh >= settings.external_refresh_seconds:
                    factor_snapshot = factor_provider.snapshot()
                    last_external_refresh = now

                orderbook = realtime_cache.latest(
                    "orderbook",
                    settings.market,
                    max_age_seconds=20.0,
                )
                if orderbook is None:
                    orderbook = client.orderbook(settings.market)

                ticker = realtime_cache.latest(
                    "ticker",
                    settings.market,
                    max_age_seconds=20.0,
                )
                if ticker is None:
                    ticker = client.ticker(settings.market)

                price = float(ticker["trade_price"])
                signal = strategy.score(
                    btc,
                    eth,
                    b3,
                    orderbook,
                    factor_snapshot.factors,
                )

                output = {
                    "ts": int(now),
                    "price": price,
                    **asdict(signal),
                    "external": asdict(factor_snapshot.factors),
                    "external_details": factor_snapshot.details,
                    "paper_equity_krw": round(account.equity(price), 2),
                    "paper_cash_krw": round(account.cash_krw, 2),
                    "paper_b3": round(account.b3_volume, 8),
                    "paper_avg_price": round(account.avg_price, 6),
                    "daily_drawdown_pct": round(account.daily_drawdown_pct(price), 4),
                }
                print(json.dumps(output, ensure_ascii=False))
                journal.record_snapshot(
                    market=settings.market,
                    price=price,
                    regime_score=signal.regime_score,
                    entry_score=signal.entry_score,
                    action=signal.action,
                    payload=output,
                    ts=now,
                )

                if (
                    signal.action == "BUY_CANDIDATE"
                    and signal.regime_score >= settings.min_regime_score
                    and signal.entry_score >= settings.min_entry_score
                    and now - last_buy_at >= settings.buy_cooldown_seconds
                ):
                    sized_order_krw = adaptive_order_krw(
                        settings.order_krw,
                        regime_score=signal.regime_score,
                        entry_score=signal.entry_score,
                        min_multiplier=settings.adaptive_size_min_multiplier,
                        max_multiplier=settings.adaptive_size_max_multiplier,
                    )

                    risk = execution_guard.evaluate_buy(
                        orderbook=orderbook,
                        btc_candles=btc,
                        order_krw=sized_order_krw,
                        now=now,
                    )
                    if not risk.allowed:
                        journal.record_event(
                            "execution_risk_blocked",
                            risk.to_dict(),
                            ts=now,
                        )
                        print(
                            json.dumps(
                                {"paper_buy_blocked": "execution_risk", "risk": risk.to_dict()},
                                ensure_ascii=False,
                            )
                        )
                    else:
                        fill_price = (
                            risk.estimated_fill_price
                            if isfinite(risk.estimated_fill_price)
                            else price
                        )
                        allowed, reason = account.can_buy(fill_price, sized_order_krw)
                        if allowed:
                            fill = account.buy(
                                fill_price,
                                sized_order_krw,
                                (
                                    f"regime={signal.regime_score}, "
                                    f"entry={signal.entry_score}, "
                                    f"spread_bps={risk.spread_bps}, "
                                    f"slippage_bps={risk.estimated_slippage_bps}"
                                ),
                            )
                            rate_limiter.record(now)
                            last_buy_at = now
                            journal.record_fill(
                                mode="paper",
                                market=settings.market,
                                fill=fill,
                                ts=now,
                            )
                            print(
                                json.dumps(
                                    {"paper_fill": asdict(fill), "risk": risk.to_dict()},
                                    ensure_ascii=False,
                                )
                            )
                        else:
                            journal.record_event(
                                "paper_buy_blocked",
                                {
                                    "reason": reason,
                                    "price": fill_price,
                                    "order_krw": sized_order_krw,
                                    "risk": risk.to_dict(),
                                },
                                ts=now,
                            )
                            print(
                                json.dumps(
                                    {"paper_buy_blocked": reason, "risk": risk.to_dict()},
                                    ensure_ascii=False,
                                )
                            )

                # Emergency risk-off exits are never blocked by spread/rate guards.
                if signal.regime_score < 45.0 and account.b3_volume > 0:
                    sell_price, sell_slippage = estimate_sell(orderbook, account.b3_volume)
                    if not isfinite(sell_price):
                        sell_price = price
                    fill = account.sell_all(
                        sell_price,
                        (
                            f"risk_off regime={signal.regime_score}, "
                            f"estimated_sell_slippage_bps="
                            f"{sell_slippage if isfinite(sell_slippage) else 'unknown'}"
                        ),
                    )
                    if fill:
                        rate_limiter.record(now)
                        journal.record_fill(
                            mode="paper",
                            market=settings.market,
                            fill=fill,
                            ts=now,
                        )
                        print(json.dumps({"paper_fill": asdict(fill)}, ensure_ascii=False))

            except KeyboardInterrupt:
                raise
            except Exception as exc:
                payload = {"error": type(exc).__name__, "message": str(exc)}
                journal.record_event("loop_error", payload)
                print(json.dumps(payload, ensure_ascii=False))

            elapsed = time.time() - started
            time.sleep(max(0.5, settings.poll_seconds - elapsed))
    finally:
        if public_stream:
            public_stream.stop()
        if private_stream:
            private_stream.stop()
        journal.close()


if __name__ == "__main__":
    run()
