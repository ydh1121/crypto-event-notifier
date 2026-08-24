from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .asset_strategy import AssetExternalFactors, AssetSignal, AssetStrategy
from .bithumb_client import BithumbClient

START_KRW = 10_000_000.0
ORDER_KRW = 1_000_000.0
MAX_POSITION_KRW = 1_500_000.0
MAX_EXPOSURE_KRW = 6_000_000.0
MAX_OPEN_POSITIONS = 4
MIN_TURNOVER_24H = 3_000_000_000.0
SCAN_INTERVAL_SECONDS = 180.0
BUY_COOLDOWN_SECONDS = 30 * 60.0
HARD_STOP_PCT = -8.0
CANDIDATE_LIMIT = 12
STATUS_PATH = Path("dashboard/runtime-demo.json")
DB_PATH = Path("b3_trader/data/auto_demo.sqlite3")
EXCLUDED_SYMBOLS = {
    "BTC", "ETH", "USDT", "USDC", "DAI", "TUSD", "FDUSD", "USDP", "PYUSD",
}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return min(high, max(low, value))


@dataclass
class DemoPosition:
    volume: float = 0.0
    avg_price: float = 0.0


class DemoStore:
    def __init__(self, path: Path = DB_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS demo_fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                market TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                volume REAL NOT NULL,
                krw REAL NOT NULL,
                realized_pnl REAL NOT NULL DEFAULT 0,
                reason TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def fills(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM demo_fills ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]

    def recent_fills(self, limit: int = 12) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM demo_fills ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [dict(row) for row in rows]

    def add_fill(
        self,
        *,
        market: str,
        symbol: str,
        side: str,
        price: float,
        volume: float,
        krw: float,
        realized_pnl: float,
        reason: str,
    ) -> None:
        self.conn.execute(
            "INSERT INTO demo_fills(ts,market,symbol,side,price,volume,krw,realized_pnl,reason) VALUES(?,?,?,?,?,?,?,?,?)",
            (time.time(), market, symbol, side, price, volume, krw, realized_pnl, reason),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


class AutoPaperDemo:
    """Isolated PAPER-only portfolio that scans Bithumb KRW markets.

    This process never calls Bithumb private endpoints and never shares fills with the
    main PAPER portfolio. It reuses the existing AssetStrategy for entry/regime scoring.
    """

    def __init__(self) -> None:
        self.client = BithumbClient()
        self.strategy = AssetStrategy()
        self.store = DemoStore()
        self.cash_krw = START_KRW
        self.positions: dict[str, DemoPosition] = {}
        self.symbols: dict[str, str] = {}
        self.last_buy_at: dict[str, float] = {}
        self.prices: dict[str, float] = {}
        self.realized_pnl = 0.0
        self._restore()

    def _restore(self) -> None:
        for row in self.store.fills():
            market = str(row["market"])
            symbol = str(row["symbol"])
            side = str(row["side"])
            price = _num(row["price"])
            volume = _num(row["volume"])
            krw = _num(row["krw"])
            self.symbols[market] = symbol
            position = self.positions.setdefault(market, DemoPosition())
            if side == "buy":
                old_cost = position.avg_price * position.volume
                position.volume += volume
                position.avg_price = (old_cost + krw) / position.volume if position.volume else 0.0
                self.cash_krw -= krw
            elif side == "sell":
                self.cash_krw += krw
                self.realized_pnl += _num(row["realized_pnl"])
                position.volume = max(0.0, position.volume - volume)
                if position.volume <= 1e-12:
                    position.volume = 0.0
                    position.avg_price = 0.0
        self.positions = {m: p for m, p in self.positions.items() if p.volume > 0}

    def _all_tickers(self) -> tuple[list[dict[str, Any]], dict[str, str]]:
        markets = [row for row in self.client.market_all() if str(row.get("market", "")).startswith("KRW-")]
        names = {str(row["market"]): str(row.get("korean_name") or row.get("english_name") or row["market"]) for row in markets}
        market_ids = list(names)
        rows: list[dict[str, Any]] = []
        for offset in range(0, len(market_ids), 70):
            rows.extend(self.client.tickers(market_ids[offset : offset + 70]))
            time.sleep(0.08)
        return rows, names

    def _rank_universe(self, tickers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
        eligible: list[dict[str, Any]] = []
        positive = 0
        breadth_denominator = 0
        for row in tickers:
            market = str(row.get("market") or "")
            if not market.startswith("KRW-"):
                continue
            symbol = market.replace("KRW-", "", 1)
            price = _num(row.get("trade_price"))
            turnover = _num(row.get("acc_trade_price_24h"))
            change_rate = _num(row.get("signed_change_rate"))
            self.prices[market] = price
            if symbol not in EXCLUDED_SYMBOLS and price > 0:
                breadth_denominator += 1
                if change_rate > 0:
                    positive += 1
            if symbol in EXCLUDED_SYMBOLS or price <= 0 or turnover < MIN_TURNOVER_24H:
                continue
            if abs(change_rate) > 0.32:
                continue
            liquidity = _clamp((math.log10(max(turnover, 1.0)) - 9.0) / 3.0 * 100.0)
            momentum = _clamp(50.0 + change_rate * 260.0)
            rank_score = 0.68 * liquidity + 0.32 * momentum
            eligible.append(
                {
                    "market": market,
                    "symbol": symbol,
                    "price": price,
                    "turnover_24h": turnover,
                    "change_24h_pct": change_rate * 100.0,
                    "rank_score": round(rank_score, 2),
                }
            )
        breadth = positive / breadth_denominator * 100.0 if breadth_denominator else 50.0
        eligible.sort(key=lambda row: row["rank_score"], reverse=True)
        return eligible[:CANDIDATE_LIMIT], breadth

    def _score_market(
        self,
        row: dict[str, Any],
        btc_candles: list[dict[str, Any]],
        eth_candles: list[dict[str, Any]],
        breadth: float,
    ) -> AssetSignal:
        market = str(row["market"])
        candles = self.client.candles_minutes(market, unit=5, count=48)
        orderbook = self.client.orderbook(market)
        external = AssetExternalFactors(
            alt_breadth=breadth,
            context_strength=_clamp(45.0 + (float(row["rank_score"]) - 50.0) * 0.35),
            derivatives_risk_on=50.0,
            news_modifier=0.0,
        )
        return self.strategy.score(btc_candles, eth_candles, candles, orderbook, external)

    def _position_value(self, market: str) -> float:
        p = self.positions.get(market)
        return p.volume * self.prices.get(market, p.avg_price) if p else 0.0

    def exposure(self) -> float:
        return sum(self._position_value(market) for market in self.positions)

    def equity(self) -> float:
        return self.cash_krw + self.exposure()

    def _buy(self, row: dict[str, Any], signal: AssetSignal) -> None:
        market = str(row["market"])
        if market in self.positions or len(self.positions) >= MAX_OPEN_POSITIONS:
            return
        now = time.time()
        if now - self.last_buy_at.get(market, 0.0) < BUY_COOLDOWN_SECONDS:
            return
        if self.exposure() + ORDER_KRW > MAX_EXPOSURE_KRW or self.cash_krw < ORDER_KRW:
            return
        price = _num(row["price"])
        order = min(ORDER_KRW, MAX_POSITION_KRW, self.cash_krw)
        if price <= 0 or order < 100_000:
            return
        volume = order / price
        self.positions[market] = DemoPosition(volume=volume, avg_price=price)
        self.symbols[market] = str(row["symbol"])
        self.cash_krw -= order
        self.last_buy_at[market] = now
        self.store.add_fill(
            market=market,
            symbol=str(row["symbol"]),
            side="buy",
            price=price,
            volume=volume,
            krw=order,
            realized_pnl=0.0,
            reason=f"BUY_CANDIDATE regime={signal.regime_score} entry={signal.entry_score}",
        )

    def _sell(self, market: str, price: float, reason: str) -> None:
        position = self.positions.get(market)
        if not position or position.volume <= 0 or price <= 0:
            return
        proceeds = position.volume * price
        cost = position.volume * position.avg_price
        realized = proceeds - cost
        self.cash_krw += proceeds
        self.store.add_fill(
            market=market,
            symbol=self.symbols.get(market, market.replace("KRW-", "")),
            side="sell",
            price=price,
            volume=position.volume,
            krw=proceeds,
            realized_pnl=realized,
            reason=reason,
        )
        self.positions.pop(market, None)
        self.realized_pnl += realized

    def _write_status(self, *, candidates: list[dict[str, Any]], error: str = "") -> None:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        positions = []
        for market, position in self.positions.items():
            price = self.prices.get(market, position.avg_price)
            pnl = position.volume * (price - position.avg_price)
            positions.append(
                {
                    "market": market,
                    "symbol": self.symbols.get(market, market.replace("KRW-", "")),
                    "volume": round(position.volume, 12),
                    "avg_price": round(position.avg_price, 12),
                    "price": round(price, 12),
                    "value_krw": round(position.volume * price, 2),
                    "pnl_krw": round(pnl, 2),
                    "pnl_pct": round((price / position.avg_price - 1.0) * 100.0, 3) if position.avg_price else 0.0,
                }
            )
        payload = {
            "running": not bool(error),
            "paper_only": True,
            "start_krw": START_KRW,
            "cash_krw": round(self.cash_krw, 2),
            "equity_krw": round(self.equity(), 2),
            "exposure_krw": round(self.exposure(), 2),
            "realized_pnl_krw": round(self.realized_pnl, 2),
            "positions": positions,
            "candidates": candidates[:8],
            "recent_fills": self.store.recent_fills(8),
            "updated_at": time.time(),
            "error": error,
            "rules": {
                "max_open_positions": MAX_OPEN_POSITIONS,
                "order_krw": ORDER_KRW,
                "max_exposure_krw": MAX_EXPOSURE_KRW,
                "min_turnover_24h": MIN_TURNOVER_24H,
            },
        }
        temp = STATUS_PATH.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temp, STATUS_PATH)

    def scan_once(self) -> None:
        tickers, _ = self._all_tickers()
        ranked, breadth = self._rank_universe(tickers)
        btc_candles = self.client.candles_minutes("KRW-BTC", unit=5, count=48)
        eth_candles = self.client.candles_minutes("KRW-ETH", unit=5, count=48)

        by_market = {row["market"]: row for row in ranked}
        # Open positions must stay in the scoring set even if they fall out of the top liquidity/momentum list.
        for market in list(self.positions):
            if market not in by_market:
                price = self.prices.get(market, 0.0)
                by_market[market] = {
                    "market": market,
                    "symbol": self.symbols.get(market, market.replace("KRW-", "")),
                    "price": price,
                    "turnover_24h": 0.0,
                    "change_24h_pct": 0.0,
                    "rank_score": 50.0,
                }

        scored: list[dict[str, Any]] = []
        signals: dict[str, AssetSignal] = {}
        for row in list(by_market.values())[: CANDIDATE_LIMIT + MAX_OPEN_POSITIONS]:
            market = str(row["market"])
            try:
                signal = self._score_market(row, btc_candles, eth_candles, breadth)
            except Exception:
                continue
            signals[market] = signal
            scored.append({**row, **asdict(signal)})
            time.sleep(0.10)

        # Exit first. The core engine already treats a deeply weak regime as an emergency exit;
        # the demo also has a hard PAPER stop so an unattended experiment cannot snowball.
        for market, position in list(self.positions.items()):
            price = self.prices.get(market, position.avg_price)
            pnl_pct = (price / position.avg_price - 1.0) * 100.0 if position.avg_price else 0.0
            signal = signals.get(market)
            if pnl_pct <= HARD_STOP_PCT:
                self._sell(market, price, f"hard PAPER stop {pnl_pct:.2f}%")
            elif signal and signal.regime_score < 45.0:
                self._sell(market, price, f"market weakness regime={signal.regime_score}")

        buyable = [row for row in scored if row.get("action") == "BUY_CANDIDATE" and row["market"] not in self.positions]
        buyable.sort(key=lambda row: (float(row.get("entry_score", 0.0)) + float(row.get("regime_score", 0.0))), reverse=True)
        for row in buyable:
            if len(self.positions) >= MAX_OPEN_POSITIONS:
                break
            self._buy(row, signals[str(row["market"])])

        scored.sort(key=lambda row: (row.get("action") == "BUY_CANDIDATE", float(row.get("entry_score", 0.0))), reverse=True)
        self._write_status(candidates=scored)

    def run(self) -> None:
        self._write_status(candidates=[])
        try:
            while True:
                started = time.time()
                try:
                    self.scan_once()
                except Exception as exc:
                    self._write_status(candidates=[], error=f"{type(exc).__name__}: {exc}")
                elapsed = time.time() - started
                time.sleep(max(15.0, SCAN_INTERVAL_SECONDS - elapsed))
        finally:
            self.store.close()


def main() -> None:
    AutoPaperDemo().run()


if __name__ == "__main__":
    main()
