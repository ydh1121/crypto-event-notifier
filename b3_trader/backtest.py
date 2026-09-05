from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

from .bithumb_client import BithumbClient
from .config import Settings
from .paper import PaperAccount
from .strategy import B3Strategy, ExternalFactors


def candle_key(row: dict[str, Any]) -> str:
    return str(row.get("candle_date_time_utc") or row.get("timestamp") or "")


def fetch_candle_history(
    client: BithumbClient,
    market: str,
    *,
    unit: int,
    bars: int,
) -> list[dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    to: str | None = None

    while len(collected) < bars:
        batch = client.candles_minutes(
            market,
            unit=unit,
            count=min(200, bars - len(collected) + 1),
            to=to,
        )
        if not batch:
            break

        for row in batch:
            key = candle_key(row)
            if key:
                collected[key] = row

        oldest = batch[-1]
        oldest_key = str(oldest.get("candle_date_time_utc") or "")
        if not oldest_key:
            break

        dt = datetime.fromisoformat(oldest_key).replace(tzinfo=timezone.utc)
        dt = dt.replace(microsecond=0)
        to = datetime.fromtimestamp(dt.timestamp() - 1, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        if len(batch) < 2:
            break

    rows = sorted(collected.values(), key=candle_key)
    return rows[-bars:]


def align_histories(
    btc: list[dict[str, Any]],
    eth: list[dict[str, Any]],
    b3: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    btc_by = {candle_key(row): row for row in btc}
    eth_by = {candle_key(row): row for row in eth}
    b3_by = {candle_key(row): row for row in b3}
    keys = sorted(set(btc_by) & set(eth_by) & set(b3_by))
    return [(btc_by[key], eth_by[key], b3_by[key]) for key in keys]


def run_backtest(
    aligned: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    *,
    start_krw: float,
    max_position_krw: float,
    order_krw: float,
    min_regime_score: float,
    min_entry_score: float,
    max_daily_loss_pct: float,
    window: int = 48,
) -> dict[str, Any]:
    strategy = B3Strategy()
    account = PaperAccount(
        start_krw=start_krw,
        max_position_krw=max_position_krw,
        max_daily_loss_pct=max_daily_loss_pct,
    )
    neutral_orderbook = {
        "orderbook_units": [{"bid_size": 1.0, "ask_size": 1.0}]
    }
    neutral_external = ExternalFactors()
    equity_curve: list[float] = []
    buys = 0
    sells = 0

    if len(aligned) < window:
        raise ValueError(f"Need at least {window} aligned bars")

    for idx in range(window - 1, len(aligned)):
        window_rows = aligned[idx - window + 1 : idx + 1]
        btc_window = list(reversed([row[0] for row in window_rows]))
        eth_window = list(reversed([row[1] for row in window_rows]))
        b3_window = list(reversed([row[2] for row in window_rows]))
        price = float(window_rows[-1][2]["trade_price"])

        signal = strategy.score(
            btc_window,
            eth_window,
            b3_window,
            neutral_orderbook,
            neutral_external,
        )

        if (
            signal.action == "BUY_CANDIDATE"
            and signal.regime_score >= min_regime_score
            and signal.entry_score >= min_entry_score
        ):
            allowed, _ = account.can_buy(price, order_krw)
            if allowed:
                account.buy(price, order_krw, "backtest signal")
                buys += 1

        if signal.regime_score < 45.0 and account.b3_volume > 0:
            if account.sell_all(price, "backtest risk-off") is not None:
                sells += 1

        equity_curve.append(account.equity(price))

    final_price = float(aligned[-1][2]["trade_price"])
    final_equity = account.equity(final_price)
    peak = start_krw
    max_drawdown_pct = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown_pct = max(
                max_drawdown_pct,
                (peak - equity) / peak * 100.0,
            )

    return {
        "bars": len(aligned),
        "start_krw": round(start_krw, 2),
        "final_equity_krw": round(final_equity, 2),
        "return_pct": round((final_equity / start_krw - 1.0) * 100.0, 3),
        "max_drawdown_pct": round(max_drawdown_pct, 3),
        "buys": buys,
        "sells": sells,
        "ending_b3": round(account.b3_volume, 8),
        "ending_cash_krw": round(account.cash_krw, 2),
        "fills": [asdict(fill) for fill in account.fills],
        "limitations": [
            "historical orderbook is neutralized",
            "Base/Gaming/derivatives/news factors are neutralized",
            "results are bar-close simulations, not tick-level fills",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="B3 price-only Phase 2 backtest")
    parser.add_argument("--bars", type=int, default=1000)
    parser.add_argument("--unit", type=int, default=5)
    args = parser.parse_args()

    load_dotenv()
    settings = Settings()
    client = BithumbClient()

    btc = fetch_candle_history(client, settings.btc_market, unit=args.unit, bars=args.bars)
    eth = fetch_candle_history(client, settings.eth_market, unit=args.unit, bars=args.bars)
    b3 = fetch_candle_history(client, settings.market, unit=args.unit, bars=args.bars)
    aligned = align_histories(btc, eth, b3)

    report = run_backtest(
        aligned,
        start_krw=settings.paper_start_krw,
        max_position_krw=settings.paper_max_position_krw,
        order_krw=settings.order_krw,
        min_regime_score=settings.min_regime_score,
        min_entry_score=settings.min_entry_score,
        max_daily_loss_pct=settings.max_daily_loss_pct,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
