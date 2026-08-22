from __future__ import annotations

import json
import os
import time
from dataclasses import asdict

from dotenv import load_dotenv

from .bithumb_client import BithumbClient
from .config import Settings
from .paper import PaperAccount
from .strategy import B3Strategy, ExternalFactors


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


def external_factors() -> ExternalFactors:
    return ExternalFactors(
        alt_breadth=env_float("ALT_BREADTH_SCORE", 50.0),
        base_strength=env_float("BASE_STRENGTH_SCORE", 50.0),
        gaming_strength=env_float("GAMING_STRENGTH_SCORE", 50.0),
        derivatives_risk_on=env_float("DERIVATIVES_RISK_ON_SCORE", 50.0),
        news_modifier=env_float("NEWS_MODIFIER", 0.0),
    )


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

    if settings.live_trading_armed:
        print("WARNING: live credentials are armed, but Phase 1 runner remains PAPER-ONLY.")

    print(
        json.dumps(
            {
                "mode": "PAPER",
                "market": settings.market,
                "paper_start_krw": settings.paper_start_krw,
                "max_position_krw": settings.paper_max_position_krw,
            },
            ensure_ascii=False,
        )
    )

    last_buy_at = 0.0
    buy_cooldown_seconds = 30 * 60

    while True:
        started = time.time()
        try:
            btc = client.candles_minutes(settings.btc_market, unit=5, count=48)
            eth = client.candles_minutes(settings.eth_market, unit=5, count=48)
            b3 = client.candles_minutes(settings.market, unit=5, count=48)
            orderbook = client.orderbook(settings.market)
            ticker = client.ticker(settings.market)
            price = float(ticker["trade_price"])

            signal = strategy.score(btc, eth, b3, orderbook, external_factors())
            output = {
                "ts": int(time.time()),
                "price": price,
                **asdict(signal),
                "paper_equity_krw": round(account.equity(price), 2),
                "paper_cash_krw": round(account.cash_krw, 2),
                "paper_b3": round(account.b3_volume, 8),
                "paper_avg_price": round(account.avg_price, 6),
            }
            print(json.dumps(output, ensure_ascii=False))

            now = time.time()
            if (
                signal.action == "BUY_CANDIDATE"
                and signal.regime_score >= settings.min_regime_score
                and signal.entry_score >= settings.min_entry_score
                and now - last_buy_at >= buy_cooldown_seconds
            ):
                allowed, reason = account.can_buy(price, settings.order_krw)
                if allowed:
                    fill = account.buy(
                        price,
                        settings.order_krw,
                        f"regime={signal.regime_score}, entry={signal.entry_score}",
                    )
                    last_buy_at = now
                    print(json.dumps({"paper_fill": asdict(fill)}, ensure_ascii=False))
                else:
                    print(json.dumps({"paper_buy_blocked": reason}, ensure_ascii=False))

            # Phase 1 exit guard: broad risk-off exits paper position completely.
            if signal.regime_score < 45.0 and account.b3_volume > 0:
                fill = account.sell_all(price, f"risk_off regime={signal.regime_score}")
                if fill:
                    print(json.dumps({"paper_fill": asdict(fill)}, ensure_ascii=False))

        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))

        elapsed = time.time() - started
        time.sleep(max(1.0, settings.poll_seconds - elapsed))


if __name__ == "__main__":
    run()
