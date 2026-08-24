from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .asset_strategy import AssetExternalFactors, AssetSignal, AssetStrategy
from .bithumb_client import BithumbClient
from .risk import estimate_buy, estimate_sell, recent_move_pct, spread_bps

# Every Bithumb KRW market gets its own independent 10M KRW PAPER account.
START_KRW = 10_000_000.0
SCAN_INTERVAL_SECONDS = 180.0
BUY_COOLDOWN_SECONDS = 30 * 60.0
MIN_ORDER_KRW = 50_000.0
MAX_POSITION_PCT = 45.0
DEFAULT_BASE_WEIGHT_PCT = 7.5
HARD_STOP_PCT = -7.5
TAKE_PROFIT_PCT = 12.0
TRAIL_ARM_PCT = 5.0
TRAIL_GIVEBACK_PCT = 3.5
MAX_SPREAD_BPS = 70.0
MAX_SLIPPAGE_BPS = 45.0
BTC_FLASH_CRASH_PCT = -3.0
BTC_FLASH_WINDOW_CANDLES = 3
STATUS_PATH = Path("dashboard/runtime-demo.json")
DETAIL_DIR = Path("dashboard/demo-runtime")
DB_PATH = Path("b3_trader/data/auto_demo.sqlite3")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return min(high, max(low, value))


def _json_load(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)


@dataclass
class DemoPosition:
    volume: float = 0.0
    avg_price: float = 0.0


@dataclass
class AdaptiveProfile:
    regime_floor: float = 55.0
    entry_floor: float = 57.0
    exploration_floor: float = 56.0
    base_weight_pct: float = DEFAULT_BASE_WEIGHT_PCT
    max_position_pct: float = MAX_POSITION_PCT
    closed_trades: int = 0
    wins: int = 0
    ema_return_pct: float = 0.0
    version: int = 1


class DemoStore:
    """SQLite persistence for independent per-market PAPER research accounts."""

    def __init__(self, path: Path = DB_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_accounts (
                market TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                cash_krw REAL NOT NULL,
                volume REAL NOT NULL DEFAULT 0,
                avg_price REAL NOT NULL DEFAULT 0,
                realized_pnl REAL NOT NULL DEFAULT 0,
                peak_equity REAL NOT NULL,
                max_drawdown_pct REAL NOT NULL DEFAULT 0,
                peak_price REAL NOT NULL DEFAULT 0,
                last_buy_at REAL NOT NULL DEFAULT 0,
                last_trade_at REAL NOT NULL DEFAULT 0,
                entry_ts REAL NOT NULL DEFAULT 0,
                entry_signal_json TEXT NOT NULL DEFAULT '{}',
                updated_ts REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS research_profiles (
                market TEXT PRIMARY KEY,
                regime_floor REAL NOT NULL,
                entry_floor REAL NOT NULL,
                exploration_floor REAL NOT NULL,
                base_weight_pct REAL NOT NULL,
                max_position_pct REAL NOT NULL,
                closed_trades INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                ema_return_pct REAL NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 1,
                updated_ts REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS research_fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                market TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                volume REAL NOT NULL,
                krw REAL NOT NULL,
                weight_pct REAL NOT NULL DEFAULT 0,
                realized_pnl REAL NOT NULL DEFAULT 0,
                return_pct REAL NOT NULL DEFAULT 0,
                reason TEXT NOT NULL,
                signal_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_research_fills_market_ts ON research_fills(market, ts DESC);

            CREATE TABLE IF NOT EXISTS research_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                market TEXT NOT NULL,
                outcome_return_pct REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                holding_seconds REAL NOT NULL,
                profile_before_json TEXT NOT NULL,
                profile_after_json TEXT NOT NULL,
                signal_json TEXT NOT NULL,
                note TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_research_feedback_market_ts ON research_feedback(market, ts DESC);

            CREATE TABLE IF NOT EXISTS research_signals (
                market TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                ts REAL NOT NULL,
                price REAL NOT NULL,
                turnover_24h REAL NOT NULL,
                change_24h_pct REAL NOT NULL,
                liquidity_score REAL NOT NULL,
                regime_score REAL NOT NULL,
                entry_score REAL NOT NULL,
                opportunity_score REAL NOT NULL,
                strategy_action TEXT NOT NULL,
                trade_intent TEXT NOT NULL,
                suggested_weight_pct REAL NOT NULL,
                reason TEXT NOT NULL,
                signal_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS research_equity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                market TEXT NOT NULL,
                equity_krw REAL NOT NULL,
                return_pct REAL NOT NULL,
                cash_krw REAL NOT NULL,
                position_value_krw REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_research_equity_market_ts ON research_equity(market, ts DESC);
            """
        )
        self.conn.commit()

    def ensure_market(self, market: str, symbol: str, name: str) -> None:
        now = time.time()
        self.conn.execute(
            """
            INSERT OR IGNORE INTO research_accounts(
                market,symbol,name,cash_krw,volume,avg_price,realized_pnl,peak_equity,
                max_drawdown_pct,peak_price,last_buy_at,last_trade_at,entry_ts,entry_signal_json,updated_ts
            ) VALUES(?,?,?,?,0,0,0,?,0,0,0,0,0,'{}',?)
            """,
            (market, symbol, name, START_KRW, START_KRW, now),
        )
        profile = AdaptiveProfile()
        self.conn.execute(
            """
            INSERT OR IGNORE INTO research_profiles(
                market,regime_floor,entry_floor,exploration_floor,base_weight_pct,max_position_pct,
                closed_trades,wins,ema_return_pct,version,updated_ts
            ) VALUES(?,?,?,?,?,?,0,0,0,1,?)
            """,
            (
                market,
                profile.regime_floor,
                profile.entry_floor,
                profile.exploration_floor,
                profile.base_weight_pct,
                profile.max_position_pct,
                now,
            ),
        )
        self.conn.execute(
            "UPDATE research_accounts SET symbol=?, name=? WHERE market=?",
            (symbol, name, market),
        )
        self.conn.commit()

    def all_accounts(self) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM research_accounts").fetchall()
        return {str(row["market"]): dict(row) for row in rows}

    def all_profiles(self) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM research_profiles").fetchall()
        return {str(row["market"]): dict(row) for row in rows}

    def save_account(self, account: dict[str, Any]) -> None:
        self.conn.execute(
            """
            UPDATE research_accounts SET
                symbol=?,name=?,cash_krw=?,volume=?,avg_price=?,realized_pnl=?,peak_equity=?,
                max_drawdown_pct=?,peak_price=?,last_buy_at=?,last_trade_at=?,entry_ts=?,
                entry_signal_json=?,updated_ts=? WHERE market=?
            """,
            (
                account["symbol"],
                account["name"],
                account["cash_krw"],
                account["volume"],
                account["avg_price"],
                account["realized_pnl"],
                account["peak_equity"],
                account["max_drawdown_pct"],
                account["peak_price"],
                account["last_buy_at"],
                account["last_trade_at"],
                account["entry_ts"],
                account["entry_signal_json"],
                time.time(),
                account["market"],
            ),
        )
        self.conn.commit()

    def save_profile(self, market: str, profile: dict[str, Any]) -> None:
        self.conn.execute(
            """
            UPDATE research_profiles SET regime_floor=?,entry_floor=?,exploration_floor=?,
                base_weight_pct=?,max_position_pct=?,closed_trades=?,wins=?,ema_return_pct=?,
                version=?,updated_ts=? WHERE market=?
            """,
            (
                profile["regime_floor"],
                profile["entry_floor"],
                profile["exploration_floor"],
                profile["base_weight_pct"],
                profile["max_position_pct"],
                int(profile["closed_trades"]),
                int(profile["wins"]),
                profile["ema_return_pct"],
                int(profile["version"]),
                time.time(),
                market,
            ),
        )
        self.conn.commit()

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
        weight_pct: float = 0.0,
        return_pct: float = 0.0,
        signal: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO research_fills(
                ts,market,symbol,side,price,volume,krw,weight_pct,realized_pnl,return_pct,reason,signal_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                time.time(), market, symbol, side, price, volume, krw, weight_pct,
                realized_pnl, return_pct, reason, json.dumps(signal or {}, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def fills(self, market: str | None = None) -> list[dict[str, Any]]:
        if market:
            rows = self.conn.execute(
                "SELECT * FROM research_fills WHERE market=? ORDER BY id ASC", (market,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM research_fills ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]

    def recent_fills(self, limit: int = 12, market: str | None = None) -> list[dict[str, Any]]:
        if market:
            rows = self.conn.execute(
                "SELECT * FROM research_fills WHERE market=? ORDER BY id DESC LIMIT ?",
                (market, int(limit)),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM research_fills ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [dict(row) for row in rows]

    def save_signal(self, row: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO research_signals(
                market,symbol,ts,price,turnover_24h,change_24h_pct,liquidity_score,regime_score,
                entry_score,opportunity_score,strategy_action,trade_intent,suggested_weight_pct,reason,signal_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(market) DO UPDATE SET
                symbol=excluded.symbol,ts=excluded.ts,price=excluded.price,turnover_24h=excluded.turnover_24h,
                change_24h_pct=excluded.change_24h_pct,liquidity_score=excluded.liquidity_score,
                regime_score=excluded.regime_score,entry_score=excluded.entry_score,
                opportunity_score=excluded.opportunity_score,strategy_action=excluded.strategy_action,
                trade_intent=excluded.trade_intent,suggested_weight_pct=excluded.suggested_weight_pct,
                reason=excluded.reason,signal_json=excluded.signal_json
            """,
            (
                row["market"], row["symbol"], row["ts"], row["price"], row["turnover_24h"],
                row["change_24h_pct"], row["liquidity_score"], row["regime_score"], row["entry_score"],
                row["opportunity_score"], row["strategy_action"], row["trade_intent"],
                row["suggested_weight_pct"], row["reason"], json.dumps(row.get("signal") or {}, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def add_feedback(
        self,
        *,
        market: str,
        outcome_return_pct: float,
        realized_pnl: float,
        holding_seconds: float,
        profile_before: dict[str, Any],
        profile_after: dict[str, Any],
        signal: dict[str, Any],
        note: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO research_feedback(
                ts,market,outcome_return_pct,realized_pnl,holding_seconds,profile_before_json,
                profile_after_json,signal_json,note
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                time.time(), market, outcome_return_pct, realized_pnl, holding_seconds,
                json.dumps(profile_before, ensure_ascii=False), json.dumps(profile_after, ensure_ascii=False),
                json.dumps(signal, ensure_ascii=False), note,
            ),
        )
        self.conn.commit()

    def snapshot_equity(self, market: str, equity: float, cash: float, position_value: float) -> None:
        last = self.conn.execute(
            "SELECT ts FROM research_equity WHERE market=? ORDER BY id DESC LIMIT 1", (market,)
        ).fetchone()
        now = time.time()
        if last and now - _num(last["ts"]) < 600.0:
            return
        self.conn.execute(
            "INSERT INTO research_equity(ts,market,equity_krw,return_pct,cash_krw,position_value_krw) VALUES(?,?,?,?,?,?)",
            (now, market, equity, (equity / START_KRW - 1.0) * 100.0, cash, position_value),
        )
        self.conn.execute("DELETE FROM research_equity WHERE ts < ?", (now - 90 * 86400.0,))
        self.conn.commit()

    def leaderboard(self, limit: int = 500) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT a.*, p.closed_trades, p.wins, p.ema_return_pct, p.version,
                   s.price, s.opportunity_score, s.trade_intent, s.regime_score, s.entry_score, s.ts AS signal_ts
            FROM research_accounts a
            LEFT JOIN research_profiles p ON p.market=a.market
            LEFT JOIN research_signals s ON s.market=a.market
            """
        ).fetchall()
        result: list[dict[str, Any]] = []
        for source in rows:
            row = dict(source)
            price = _num(row.get("price"), _num(row.get("avg_price")))
            position_value = _num(row.get("volume")) * price
            equity = _num(row.get("cash_krw")) + position_value
            closed = int(row.get("closed_trades") or 0)
            wins = int(row.get("wins") or 0)
            result.append(
                {
                    "market": row["market"],
                    "symbol": row["symbol"],
                    "name": row["name"],
                    "equity_krw": round(equity, 2),
                    "return_pct": round((equity / START_KRW - 1.0) * 100.0, 4),
                    "cash_krw": round(_num(row.get("cash_krw")), 2),
                    "position_value_krw": round(position_value, 2),
                    "realized_pnl_krw": round(_num(row.get("realized_pnl")), 2),
                    "max_drawdown_pct": round(_num(row.get("max_drawdown_pct")), 4),
                    "closed_trades": closed,
                    "win_rate_pct": round(wins / closed * 100.0, 2) if closed else 0.0,
                    "ema_return_pct": round(_num(row.get("ema_return_pct")), 4),
                    "profile_version": int(row.get("version") or 1),
                    "price": round(price, 12),
                    "opportunity_score": round(_num(row.get("opportunity_score")), 2),
                    "regime_score": round(_num(row.get("regime_score")), 2),
                    "entry_score": round(_num(row.get("entry_score")), 2),
                    "trade_intent": row.get("trade_intent") or "waiting",
                    "signal_ts": _num(row.get("signal_ts")),
                    "has_position": position_value > 0,
                }
            )
        result.sort(key=lambda item: item["return_pct"], reverse=True)
        return result[: max(1, int(limit))]

    def market_detail(self, market: str) -> dict[str, Any]:
        leaderboard_row = next((row for row in self.leaderboard(2000) if row["market"] == market), None)
        if not leaderboard_row:
            return {}
        account_row = self.conn.execute("SELECT * FROM research_accounts WHERE market=?", (market,)).fetchone()
        profile_row = self.conn.execute("SELECT * FROM research_profiles WHERE market=?", (market,)).fetchone()
        signal_row = self.conn.execute("SELECT * FROM research_signals WHERE market=?", (market,)).fetchone()
        fills = self.conn.execute(
            "SELECT * FROM research_fills WHERE market=? ORDER BY id DESC LIMIT 120", (market,)
        ).fetchall()
        feedback = self.conn.execute(
            "SELECT * FROM research_feedback WHERE market=? ORDER BY id DESC LIMIT 60", (market,)
        ).fetchall()
        equity = self.conn.execute(
            "SELECT ts,equity_krw,return_pct,cash_krw,position_value_krw FROM research_equity WHERE market=? ORDER BY id DESC LIMIT 360",
            (market,),
        ).fetchall()
        signal = dict(signal_row) if signal_row else {}
        if signal:
            signal["signal"] = _json_load(signal.pop("signal_json", "{}"))
        feedback_rows = []
        for source in feedback:
            row = dict(source)
            row["profile_before"] = _json_load(row.pop("profile_before_json", "{}"))
            row["profile_after"] = _json_load(row.pop("profile_after_json", "{}"))
            row["signal"] = _json_load(row.pop("signal_json", "{}"))
            feedback_rows.append(row)
        fill_rows = []
        for source in fills:
            row = dict(source)
            row["signal"] = _json_load(row.pop("signal_json", "{}"))
            fill_rows.append(row)
        return {
            "summary": leaderboard_row,
            "account": dict(account_row) if account_row else {},
            "profile": dict(profile_row) if profile_row else {},
            "signal": signal,
            "fills": fill_rows,
            "feedback": feedback_rows,
            "equity_history": list(reversed([dict(row) for row in equity])),
        }

    def close(self) -> None:
        self.conn.close()


class AutoPaperDemo:
    """Bithumb-wide, per-coin, adaptive PAPER research engine.

    Every KRW market has an independent virtual 10M KRW account. The engine never
    calls private/order endpoints. It deliberately includes bounded exploration so
    research does not freeze forever just because the legacy BUY_CANDIDATE threshold
    was not reached. Learning only changes PAPER profile thresholds/position sizing;
    it never rewrites production Python code and never enables real trading.
    """

    def __init__(self) -> None:
        self.client = BithumbClient()
        self.strategy = AssetStrategy()
        self.store = DemoStore()
        self.prices: dict[str, float] = {}
        self.names: dict[str, str] = {}
        self.scan_number = 0
        self.last_scan_started = 0.0
        self.last_scan_completed = 0.0

    def _all_tickers(self) -> tuple[list[dict[str, Any]], dict[str, str]]:
        markets = [row for row in self.client.market_all() if str(row.get("market", "")).startswith("KRW-")]
        names = {
            str(row["market"]): str(row.get("korean_name") or row.get("english_name") or row["market"])
            for row in markets
        }
        market_ids = list(names)
        rows: list[dict[str, Any]] = []
        for offset in range(0, len(market_ids), 70):
            rows.extend(self.client.tickers(market_ids[offset : offset + 70]))
            time.sleep(0.08)
        return rows, names

    def _rank_universe(self, tickers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
        """Return every valid KRW market, sorted only to make the sweep deterministic."""
        rows: list[dict[str, Any]] = []
        positive = 0
        denominator = 0
        for ticker in tickers:
            market = str(ticker.get("market") or "")
            if not market.startswith("KRW-"):
                continue
            symbol = market.replace("KRW-", "", 1)
            price = _num(ticker.get("trade_price"))
            turnover = _num(ticker.get("acc_trade_price_24h"))
            change_rate = _num(ticker.get("signed_change_rate"))
            if price <= 0:
                continue
            self.prices[market] = price
            denominator += 1
            if change_rate > 0:
                positive += 1
            liquidity = _clamp((math.log10(max(turnover, 1.0)) - 7.0) / 5.0 * 100.0)
            momentum = _clamp(50.0 + change_rate * 240.0)
            rows.append(
                {
                    "market": market,
                    "symbol": symbol,
                    "name": self.names.get(market, symbol),
                    "price": price,
                    "turnover_24h": turnover,
                    "change_24h_pct": change_rate * 100.0,
                    "liquidity_score": round(liquidity, 2),
                    "rank_score": round(0.62 * liquidity + 0.38 * momentum, 2),
                }
            )
        breadth = positive / denominator * 100.0 if denominator else 50.0
        rows.sort(key=lambda row: (row["turnover_24h"], row["market"]), reverse=True)
        return rows, breadth

    def _score_market(
        self,
        row: dict[str, Any],
        btc_candles: list[dict[str, Any]],
        eth_candles: list[dict[str, Any]],
        breadth: float,
    ) -> tuple[AssetSignal, dict[str, Any]]:
        market = str(row["market"])
        candles = self.client.candles_minutes(market, unit=5, count=48)
        orderbook = self.client.orderbook(market)
        context = _clamp(35.0 + float(row["liquidity_score"]) * 0.35 + _clamp(50.0 + row["change_24h_pct"] * 2.0) * 0.30)
        signal = self.strategy.score(
            btc_candles,
            eth_candles,
            candles,
            orderbook,
            AssetExternalFactors(
                alt_breadth=breadth,
                context_strength=context,
                derivatives_risk_on=50.0,
                news_modifier=0.0,
            ),
        )
        return signal, orderbook

    @staticmethod
    def _opportunity(signal: AssetSignal, liquidity_score: float) -> float:
        momentum = _clamp(50.0 + signal.asset_return_pct * 4.0)
        orderbook = _clamp(50.0 + signal.orderbook_imbalance * 180.0)
        return round(
            _clamp(
                0.30 * signal.regime_score
                + 0.34 * signal.entry_score
                + 0.14 * momentum
                + 0.10 * orderbook
                + 0.12 * liquidity_score
            ),
            2,
        )

    @staticmethod
    def _suggested_weight(profile: dict[str, Any], opportunity: float, intent: str) -> float:
        base = _num(profile.get("base_weight_pct"), DEFAULT_BASE_WEIGHT_PCT)
        confidence = _clamp((opportunity - 42.0) / 38.0, 0.0, 1.0)
        weight = base * (0.72 + confidence * 0.78)
        if intent in {"explore", "idle_explore"}:
            weight *= 0.55
        elif intent == "add":
            weight *= 0.75
        return round(_clamp(weight, 2.5, 15.0), 2)

    def _trade_intent(
        self,
        account: dict[str, Any],
        profile: dict[str, Any],
        signal: AssetSignal,
        opportunity: float,
        price: float,
        now: float,
    ) -> tuple[str, str]:
        volume = _num(account.get("volume"))
        avg = _num(account.get("avg_price"))
        if volume > 0 and avg > 0:
            pnl_pct = (price / avg - 1.0) * 100.0
            peak = max(price, _num(account.get("peak_price"), price))
            peak_gain = (peak / avg - 1.0) * 100.0
            giveback = (price / peak - 1.0) * 100.0 if peak > 0 else 0.0
            holding = now - _num(account.get("entry_ts"), now)
            if pnl_pct <= HARD_STOP_PCT:
                return "sell", f"hard_stop {pnl_pct:.2f}%"
            if pnl_pct >= TAKE_PROFIT_PCT:
                return "sell", f"take_profit {pnl_pct:.2f}%"
            if peak_gain >= TRAIL_ARM_PCT and giveback <= -TRAIL_GIVEBACK_PCT:
                return "sell", f"trailing_exit peak={peak_gain:.2f}% giveback={giveback:.2f}%"
            if signal.regime_score < 35.0 and pnl_pct < 0:
                return "sell", f"market_weakness regime={signal.regime_score:.2f}"
            if holding >= 18 * 3600.0 and pnl_pct < 2.0 and opportunity < 50.0:
                return "sell", f"time_exit {holding / 3600.0:.1f}h opportunity={opportunity:.1f}"
            if (
                now - _num(account.get("last_buy_at")) >= BUY_COOLDOWN_SECONDS
                and opportunity >= max(62.0, _num(profile.get("exploration_floor"), 56.0) + 5.0)
            ):
                return "add", f"adaptive_add opportunity={opportunity:.1f}"
            return "hold", f"position_hold pnl={pnl_pct:.2f}% opportunity={opportunity:.1f}"

        normal = (
            signal.regime_score >= _num(profile.get("regime_floor"), 55.0)
            and signal.entry_score >= _num(profile.get("entry_floor"), 57.0)
            and opportunity >= _num(profile.get("exploration_floor"), 56.0)
        )
        if signal.action == "BUY_CANDIDATE":
            return "buy", "legacy BUY_CANDIDATE + adaptive profile"
        if normal:
            return "buy", "adaptive thresholds passed"
        if opportunity >= _num(profile.get("exploration_floor"), 56.0) and signal.regime_score >= 42.0:
            return "explore", "bounded exploration: opportunity is constructive"

        last_trade = _num(account.get("last_trade_at"))
        idle_hours = (now - last_trade) / 3600.0 if last_trade > 0 else 999.0
        relaxed = max(45.0, _num(profile.get("exploration_floor"), 56.0) - 8.0)
        if idle_hours >= 6.0 and opportunity >= relaxed and signal.regime_score >= 38.0:
            return "idle_explore", f"idle exploration after {idle_hours:.1f}h"
        return "wait", "no forced trade: opportunity/risk still too weak"

    def _risk_buy(
        self,
        orderbook: dict[str, Any],
        btc_candles: list[dict[str, Any]],
        order_krw: float,
    ) -> tuple[bool, float, str]:
        spread = spread_bps(orderbook)
        fill_price, slippage = estimate_buy(orderbook, order_krw)
        btc_move = recent_move_pct(btc_candles, BTC_FLASH_WINDOW_CANDLES)
        reasons = []
        if not math.isfinite(spread) or spread > MAX_SPREAD_BPS:
            reasons.append(f"spread={spread:.1f}bps")
        if not math.isfinite(slippage) or slippage > MAX_SLIPPAGE_BPS:
            reasons.append(f"slippage={slippage:.1f}bps")
        if btc_move <= BTC_FLASH_CRASH_PCT:
            reasons.append(f"btc_flash={btc_move:.2f}%")
        return not reasons, fill_price, ", ".join(reasons)

    def _buy(
        self,
        account: dict[str, Any],
        profile: dict[str, Any],
        row: dict[str, Any],
        signal: AssetSignal,
        opportunity: float,
        intent: str,
        orderbook: dict[str, Any],
        btc_candles: list[dict[str, Any]],
    ) -> str:
        price = _num(row.get("price"))
        weight = self._suggested_weight(profile, opportunity, intent)
        max_position = START_KRW * _num(profile.get("max_position_pct"), MAX_POSITION_PCT) / 100.0
        current_value = _num(account.get("volume")) * price
        order = min(
            START_KRW * weight / 100.0,
            max(0.0, max_position - current_value),
            _num(account.get("cash_krw")),
        )
        if price <= 0 or order < MIN_ORDER_KRW:
            return "blocked: position/cash limit"
        allowed, fill_price, risk_reason = self._risk_buy(orderbook, btc_candles, order)
        if not allowed or not math.isfinite(fill_price) or fill_price <= 0:
            return f"blocked: {risk_reason or 'invalid fill'}"

        volume = order / fill_price
        old_volume = _num(account.get("volume"))
        old_cost = old_volume * _num(account.get("avg_price"))
        new_volume = old_volume + volume
        account["volume"] = new_volume
        account["avg_price"] = (old_cost + order) / new_volume if new_volume else 0.0
        account["cash_krw"] = _num(account.get("cash_krw")) - order
        account["peak_price"] = max(_num(account.get("peak_price")), fill_price)
        now = time.time()
        account["last_buy_at"] = now
        account["last_trade_at"] = now
        if old_volume <= 0:
            account["entry_ts"] = now
            account["entry_signal_json"] = json.dumps(
                {
                    **asdict(signal),
                    "opportunity_score": opportunity,
                    "intent": intent,
                    "weight_pct": weight,
                },
                ensure_ascii=False,
            )
        self.store.save_account(account)
        self.store.add_fill(
            market=row["market"], symbol=row["symbol"], side="buy", price=fill_price,
            volume=volume, krw=order, realized_pnl=0.0, return_pct=0.0, weight_pct=weight,
            reason=f"{intent}; opportunity={opportunity:.1f}",
            signal={**asdict(signal), "opportunity_score": opportunity},
        )
        return f"bought {weight:.2f}%"

    def _adapt_profile(
        self,
        profile: dict[str, Any],
        entry_signal: dict[str, Any],
        trade_return_pct: float,
    ) -> tuple[dict[str, Any], str]:
        before = dict(profile)
        closed = int(profile.get("closed_trades") or 0) + 1
        wins = int(profile.get("wins") or 0) + (1 if trade_return_pct > 0 else 0)
        old_ema = _num(profile.get("ema_return_pct"))
        ema = trade_return_pct if closed == 1 else old_ema * 0.80 + trade_return_pct * 0.20
        lr = max(0.05, min(0.16, 0.24 / math.sqrt(closed)))
        entry_regime = _num(entry_signal.get("regime_score"), _num(profile.get("regime_floor"), 55.0))
        entry_entry = _num(entry_signal.get("entry_score"), _num(profile.get("entry_floor"), 57.0))
        entry_opp = _num(entry_signal.get("opportunity_score"), _num(profile.get("exploration_floor"), 56.0))

        if trade_return_pct > 0:
            profile["regime_floor"] = _clamp(
                _num(profile.get("regime_floor")) + lr * ((entry_regime - 2.0) - _num(profile.get("regime_floor"))),
                42.0, 72.0,
            )
            profile["entry_floor"] = _clamp(
                _num(profile.get("entry_floor")) + lr * ((entry_entry - 2.0) - _num(profile.get("entry_floor"))),
                44.0, 74.0,
            )
            profile["exploration_floor"] = _clamp(
                _num(profile.get("exploration_floor")) + lr * ((entry_opp - 2.0) - _num(profile.get("exploration_floor"))),
                44.0, 72.0,
            )
            direction = "winning entry conditions were reinforced"
        else:
            profile["regime_floor"] = _clamp(max(_num(profile.get("regime_floor")), entry_regime + 2.0 * lr), 42.0, 75.0)
            profile["entry_floor"] = _clamp(max(_num(profile.get("entry_floor")), entry_entry + 3.0 * lr), 44.0, 77.0)
            profile["exploration_floor"] = _clamp(max(_num(profile.get("exploration_floor")), entry_opp + 3.0 * lr), 44.0, 75.0)
            direction = "losing entry conditions were made more selective"

        win_rate = wins / closed if closed else 0.0
        base = _num(profile.get("base_weight_pct"), DEFAULT_BASE_WEIGHT_PCT)
        base += (0.28 if trade_return_pct > 0 else -0.38) + _clamp(ema, -10.0, 10.0) * 0.015 + (win_rate - 0.5) * 0.15
        profile["base_weight_pct"] = _clamp(base, 3.0, 15.0)
        profile["closed_trades"] = closed
        profile["wins"] = wins
        profile["ema_return_pct"] = ema
        profile["version"] = int(profile.get("version") or 1) + 1
        self.store.save_profile(str(profile["market"]), profile)
        note = f"{direction}; v{before.get('version', 1)}→v{profile['version']}"
        return before, note

    def _sell(
        self,
        account: dict[str, Any],
        profile: dict[str, Any],
        row: dict[str, Any],
        signal: AssetSignal,
        opportunity: float,
        reason: str,
        orderbook: dict[str, Any],
    ) -> str:
        volume = _num(account.get("volume"))
        avg = _num(account.get("avg_price"))
        price = _num(row.get("price"))
        if volume <= 0 or avg <= 0 or price <= 0:
            return "blocked: no position"
        fill_price, slippage = estimate_sell(orderbook, volume)
        if not math.isfinite(fill_price) or fill_price <= 0:
            return "blocked: sell depth insufficient"
        proceeds = volume * fill_price
        cost = volume * avg
        realized = proceeds - cost
        return_pct = (fill_price / avg - 1.0) * 100.0
        holding_seconds = max(0.0, time.time() - _num(account.get("entry_ts"), time.time()))
        entry_signal = _json_load(account.get("entry_signal_json"))

        account["cash_krw"] = _num(account.get("cash_krw")) + proceeds
        account["realized_pnl"] = _num(account.get("realized_pnl")) + realized
        account["volume"] = 0.0
        account["avg_price"] = 0.0
        account["peak_price"] = 0.0
        account["last_trade_at"] = time.time()
        account["entry_ts"] = 0.0
        account["entry_signal_json"] = "{}"
        self.store.save_account(account)
        self.store.add_fill(
            market=row["market"], symbol=row["symbol"], side="sell", price=fill_price,
            volume=volume, krw=proceeds, realized_pnl=realized, return_pct=return_pct, weight_pct=100.0,
            reason=f"{reason}; sell_slippage_bps={slippage:.2f}",
            signal={**asdict(signal), "opportunity_score": opportunity},
        )
        before, note = self._adapt_profile(profile, entry_signal, return_pct)
        self.store.add_feedback(
            market=row["market"], outcome_return_pct=return_pct, realized_pnl=realized,
            holding_seconds=holding_seconds, profile_before=before, profile_after=dict(profile),
            signal=entry_signal, note=note,
        )
        return f"sold {return_pct:+.2f}%"

    def _update_equity(self, account: dict[str, Any], price: float) -> tuple[float, float]:
        position_value = _num(account.get("volume")) * price
        equity = _num(account.get("cash_krw")) + position_value
        peak = max(_num(account.get("peak_equity"), START_KRW), equity)
        drawdown = (equity / peak - 1.0) * 100.0 if peak > 0 else 0.0
        account["peak_equity"] = peak
        account["max_drawdown_pct"] = min(_num(account.get("max_drawdown_pct")), drawdown)
        if _num(account.get("volume")) > 0:
            account["peak_price"] = max(_num(account.get("peak_price")), price)
        self.store.save_account(account)
        self.store.snapshot_equity(account["market"], equity, _num(account.get("cash_krw")), position_value)
        return equity, position_value

    def _write_market_detail(self, market: str) -> None:
        detail = self.store.market_detail(market)
        if detail:
            safe_name = market.replace("/", "_")
            _atomic_json(DETAIL_DIR / f"{safe_name}.json", detail)

    def _write_status(self, *, scanned: int, total: int, error: str = "") -> None:
        leaderboard = self.store.leaderboard(500)
        active_positions = sum(1 for row in leaderboard if row["has_position"])
        total_equity = sum(_num(row.get("equity_krw")) for row in leaderboard)
        total_cash = sum(_num(row.get("cash_krw")) for row in leaderboard)
        best = leaderboard[0] if leaderboard else None
        payload = {
            "running": not bool(error),
            "paper_only": True,
            "mode": "per_coin_adaptive_research",
            "pid": os.getpid(),
            "start_krw": START_KRW,
            "per_market_start_krw": START_KRW,
            "market_count": len(leaderboard),
            "scanned_count": scanned,
            "scan_total": total,
            "active_positions": active_positions,
            "aggregate_virtual_capital_krw": START_KRW * len(leaderboard),
            "equity_krw": round(total_equity, 2),
            "cash_krw": round(total_cash, 2),
            "positions": [row for row in leaderboard if row["has_position"]][:20],
            "candidates": sorted(leaderboard, key=lambda row: row["opportunity_score"], reverse=True)[:20],
            "leaderboard": leaderboard[:60],
            "best_market": best,
            "updated_at": time.time(),
            "last_scan_started": self.last_scan_started,
            "last_scan_completed": self.last_scan_completed,
            "scan_number": self.scan_number,
            "error": error,
            "rules": {
                "each_market_start_krw": START_KRW,
                "scan_interval_seconds": SCAN_INTERVAL_SECONDS,
                "max_position_pct": MAX_POSITION_PCT,
                "base_weight_pct": DEFAULT_BASE_WEIGHT_PCT,
                "bounded_exploration": True,
                "adaptive_profile_learning": True,
                "hard_stop_pct": HARD_STOP_PCT,
                "take_profit_pct": TAKE_PROFIT_PCT,
                "max_spread_bps": MAX_SPREAD_BPS,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            },
        }
        _atomic_json(STATUS_PATH, payload)

    def scan_once(self) -> None:
        self.last_scan_started = time.time()
        tickers, names = self._all_tickers()
        self.names = names
        universe, breadth = self._rank_universe(tickers)
        for row in universe:
            self.store.ensure_market(row["market"], row["symbol"], row["name"])
        accounts = self.store.all_accounts()
        profiles = self.store.all_profiles()
        for market, profile in profiles.items():
            profile["market"] = market

        btc_candles = self.client.candles_minutes("KRW-BTC", unit=5, count=48)
        eth_candles = self.client.candles_minutes("KRW-ETH", unit=5, count=48)
        total = len(universe)
        self._write_status(scanned=0, total=total)

        for index, row in enumerate(universe, start=1):
            market = row["market"]
            account = accounts[market]
            profile = profiles[market]
            now = time.time()
            try:
                signal, orderbook = self._score_market(row, btc_candles, eth_candles, breadth)
                opportunity = self._opportunity(signal, row["liquidity_score"])
                intent, reason = self._trade_intent(account, profile, signal, opportunity, row["price"], now)
                suggested_weight = self._suggested_weight(profile, opportunity, intent)
                execution_note = ""
                if intent in {"buy", "explore", "idle_explore", "add"}:
                    execution_note = self._buy(account, profile, row, signal, opportunity, intent, orderbook, btc_candles)
                elif intent == "sell":
                    execution_note = self._sell(account, profile, row, signal, opportunity, reason, orderbook)
                equity, position_value = self._update_equity(account, row["price"])
                self.store.save_signal(
                    {
                        "market": market,
                        "symbol": row["symbol"],
                        "ts": now,
                        "price": row["price"],
                        "turnover_24h": row["turnover_24h"],
                        "change_24h_pct": row["change_24h_pct"],
                        "liquidity_score": row["liquidity_score"],
                        "regime_score": signal.regime_score,
                        "entry_score": signal.entry_score,
                        "opportunity_score": opportunity,
                        "strategy_action": signal.action,
                        "trade_intent": intent,
                        "suggested_weight_pct": suggested_weight,
                        "reason": f"{reason}; {execution_note}" if execution_note else reason,
                        "signal": {
                            **asdict(signal),
                            "equity_krw": equity,
                            "position_value_krw": position_value,
                        },
                    }
                )
                self._write_market_detail(market)
            except Exception as exc:
                self.store.save_signal(
                    {
                        "market": market,
                        "symbol": row["symbol"],
                        "ts": now,
                        "price": row["price"],
                        "turnover_24h": row["turnover_24h"],
                        "change_24h_pct": row["change_24h_pct"],
                        "liquidity_score": row["liquidity_score"],
                        "regime_score": 0.0,
                        "entry_score": 0.0,
                        "opportunity_score": 0.0,
                        "strategy_action": "ERROR",
                        "trade_intent": "analysis_error",
                        "suggested_weight_pct": 0.0,
                        "reason": f"{type(exc).__name__}: {exc}",
                        "signal": {},
                    }
                )
            if index % 20 == 0 or index == total:
                self._write_status(scanned=index, total=total)
            time.sleep(0.06)

        self.scan_number += 1
        self.last_scan_completed = time.time()
        self._write_status(scanned=total, total=total)

    def run(self, stop_event: threading.Event | None = None) -> None:
        stop_event = stop_event or threading.Event()
        self._write_status(scanned=0, total=0)
        try:
            while not stop_event.is_set():
                started = time.time()
                try:
                    self.scan_once()
                except Exception as exc:
                    self._write_status(scanned=0, total=0, error=f"{type(exc).__name__}: {exc}")
                elapsed = time.time() - started
                wait_seconds = max(15.0, SCAN_INTERVAL_SECONDS - elapsed)
                if stop_event.wait(wait_seconds):
                    break
        finally:
            self.store.close()


def main() -> None:
    AutoPaperDemo().run()


if __name__ == "__main__":
    main()
