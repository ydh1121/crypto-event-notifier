from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH, START_KRW

SOURCE_STRATEGY = "adaptive"
FEE_RATE = 0.0004
SLIPPAGE_RATE = 0.0005
WARMUP_SOURCE_ROWS = 3000
MAX_SOURCE_ROWS_PER_RUN = 2500


@dataclass(frozen=True)
class StyleSpec:
    key: str
    label: str
    description: str
    entry_regime: float
    entry_score: float
    opportunity: float
    base_weight_pct: float
    max_position_pct: float
    max_buys: int
    add_drop_pct: float
    take_profit_pct: float
    stop_loss_pct: float
    exit_regime: float
    min_hold_seconds: float
    max_volatility_pct: float


STYLE_SPECS: dict[str, StyleSpec] = {
    "conservative": StyleSpec(
        "conservative", "보수적", "강한 시장·진입 조건에서 작은 비중으로 시작하고 손실을 빠르게 제한합니다.",
        66.0, 68.0, 70.0, 5.0, 20.0, 2, 3.5, 8.0, -4.0, 51.0, 900.0, 3.8,
    ),
    "balanced": StyleSpec(
        "balanced", "균형", "시장·진입·기회 점수를 고르게 사용하며 수익과 낙폭의 균형을 봅니다.",
        60.0, 60.0, 64.0, 7.5, 30.0, 3, 3.0, 10.0, -6.0, 47.0, 600.0, 5.2,
    ),
    "aggressive": StyleSpec(
        "aggressive", "공격적", "낮은 진입 문턱과 큰 허용 비중으로 더 많은 기회를 탐색합니다.",
        54.0, 55.0, 58.0, 10.0, 45.0, 4, 2.5, 14.0, -8.0, 42.0, 300.0, 8.0,
    ),
    "dca": StyleSpec(
        "dca", "분할매수", "초기 비중을 낮추고 평균단가 아래에서 여러 차례 분할 진입합니다.",
        58.0, 56.0, 60.0, 6.0, 45.0, 6, 2.0, 9.0, -12.0, 44.0, 600.0, 6.5,
    ),
    "contrarian": StyleSpec(
        "contrarian", "역추세", "충분한 조정·되돌림이 발생했지만 시장 체력이 남아 있는 구간을 탐색합니다.",
        50.0, 58.0, 58.0, 6.5, 30.0, 3, 3.0, 12.0, -8.0, 42.0, 900.0, 6.5,
    ),
    "swing": StyleSpec(
        "swing", "스윙", "시장 강도와 상대 모멘텀이 유지되는 구간에서 더 긴 목표 폭을 추구합니다.",
        62.0, 58.0, 66.0, 8.0, 35.0, 2, 4.0, 18.0, -6.5, 48.0, 1800.0, 6.0,
    ),
}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def experiment_id(exchange: str, style: str) -> str:
    return f"{exchange.strip().lower()}|{style.strip().lower()}|v1"


def strategy_key(style: str) -> str:
    return f"lab:{style.strip().lower()}:v1"


class StrategyLabStore:
    """Incremental shadow-PAPER strategy laboratory using existing market-memory rows.

    It never calls an exchange API and never writes to the active adaptive PAPER
    account tables. All strategy-lab accounts/trades/learning live in dedicated
    tables in the same authoritative SQLite database.
    """

    def __init__(self, path: Path = DB_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
        self._ensure_default_experiments()
        self._ensure_ingest_state()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS strategy_lab_experiments (
                experiment_id TEXT PRIMARY KEY,
                exchange TEXT NOT NULL,
                style TEXT NOT NULL,
                strategy_key TEXT NOT NULL,
                label TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                initial_krw REAL NOT NULL,
                created_ts REAL NOT NULL,
                updated_ts REAL NOT NULL,
                UNIQUE(exchange, style)
            );

            CREATE TABLE IF NOT EXISTS strategy_lab_ingest_state (
                exchange TEXT PRIMARY KEY,
                source_strategy TEXT NOT NULL,
                last_memory_id INTEGER NOT NULL DEFAULT 0,
                initialized_ts REAL NOT NULL,
                updated_ts REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS strategy_lab_accounts (
                experiment_id TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                cash_krw REAL NOT NULL,
                volume REAL NOT NULL DEFAULT 0,
                avg_price REAL NOT NULL DEFAULT 0,
                realized_pnl REAL NOT NULL DEFAULT 0,
                peak_equity REAL NOT NULL,
                max_drawdown_pct REAL NOT NULL DEFAULT 0,
                buy_count INTEGER NOT NULL DEFAULT 0,
                entry_ts REAL NOT NULL DEFAULT 0,
                last_price REAL NOT NULL DEFAULT 0,
                closed_trades INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                gross_profit REAL NOT NULL DEFAULT 0,
                gross_loss REAL NOT NULL DEFAULT 0,
                sum_return_pct REAL NOT NULL DEFAULT 0,
                last_memory_id INTEGER NOT NULL DEFAULT 0,
                updated_ts REAL NOT NULL,
                PRIMARY KEY(experiment_id, market)
            );
            CREATE INDEX IF NOT EXISTS idx_strategy_lab_accounts_exchange
                ON strategy_lab_accounts(exchange, experiment_id, market);

            CREATE TABLE IF NOT EXISTS strategy_lab_learning (
                experiment_id TEXT NOT NULL,
                market TEXT NOT NULL,
                entry_bias REAL NOT NULL DEFAULT 0,
                weight_multiplier REAL NOT NULL DEFAULT 1,
                ema_return_pct REAL NOT NULL DEFAULT 0,
                closed_trades INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                updated_ts REAL NOT NULL,
                PRIMARY KEY(experiment_id, market)
            );

            CREATE TABLE IF NOT EXISTS strategy_lab_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                style TEXT NOT NULL,
                ts REAL NOT NULL,
                source_memory_id INTEGER NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                volume REAL NOT NULL,
                krw REAL NOT NULL,
                realized_pnl REAL NOT NULL DEFAULT 0,
                return_pct REAL NOT NULL DEFAULT 0,
                reason TEXT NOT NULL,
                buy_index INTEGER NOT NULL DEFAULT 0,
                UNIQUE(experiment_id, market, source_memory_id, side)
            );
            CREATE INDEX IF NOT EXISTS idx_strategy_lab_trades_exp_ts
                ON strategy_lab_trades(experiment_id, ts DESC);

            CREATE TABLE IF NOT EXISTS strategy_lab_metrics (
                experiment_id TEXT PRIMARY KEY,
                exchange TEXT NOT NULL,
                style TEXT NOT NULL,
                markets INTEGER NOT NULL DEFAULT 0,
                active_positions INTEGER NOT NULL DEFAULT 0,
                total_equity_krw REAL NOT NULL DEFAULT 0,
                aggregate_start_krw REAL NOT NULL DEFAULT 0,
                return_pct REAL NOT NULL DEFAULT 0,
                realized_pnl REAL NOT NULL DEFAULT 0,
                max_drawdown_pct REAL NOT NULL DEFAULT 0,
                closed_trades INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                win_rate_pct REAL NOT NULL DEFAULT 0,
                expectancy_pct REAL NOT NULL DEFAULT 0,
                profit_factor REAL NOT NULL DEFAULT 0,
                updated_ts REAL NOT NULL
            );
            """
        )
        self.conn.commit()

    def _ensure_default_experiments(self) -> None:
        now = time.time()
        for exchange in ("bithumb", "upbit"):
            for style, spec in STYLE_SPECS.items():
                self.conn.execute(
                    """INSERT OR IGNORE INTO strategy_lab_experiments(
                        experiment_id,exchange,style,strategy_key,label,description,status,initial_krw,created_ts,updated_ts
                    ) VALUES(?,?,?,?,?,?,'running',?,?,?)""",
                    (
                        experiment_id(exchange, style), exchange, style, strategy_key(style),
                        spec.label, spec.description, START_KRW, now, now,
                    ),
                )
        self.conn.commit()

    def _warm_start_cursor(self, exchange: str) -> int:
        row = self.conn.execute(
            """SELECT id FROM research_market_memory_mx
               WHERE exchange=? AND strategy=? ORDER BY id DESC LIMIT 1 OFFSET ?""",
            (exchange, SOURCE_STRATEGY, WARMUP_SOURCE_ROWS - 1),
        ).fetchone()
        if row:
            return max(0, int(row["id"]) - 1)
        return 0

    def _ensure_ingest_state(self) -> None:
        now = time.time()
        for exchange in ("bithumb", "upbit"):
            existing = self.conn.execute(
                "SELECT 1 FROM strategy_lab_ingest_state WHERE exchange=?", (exchange,)
            ).fetchone()
            if existing:
                continue
            cursor = self._warm_start_cursor(exchange)
            self.conn.execute(
                """INSERT INTO strategy_lab_ingest_state(
                    exchange,source_strategy,last_memory_id,initialized_ts,updated_ts
                ) VALUES(?,?,?,?,?)""",
                (exchange, SOURCE_STRATEGY, cursor, now, now),
            )
        self.conn.commit()

    def _experiments(self, exchange: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT * FROM strategy_lab_experiments
               WHERE exchange=? AND status='running' ORDER BY style""",
            (exchange,),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _blank_account(exp_id: str, exchange: str, market: str) -> dict[str, Any]:
        now = time.time()
        return {
            "experiment_id": exp_id, "exchange": exchange, "market": market,
            "cash_krw": START_KRW, "volume": 0.0, "avg_price": 0.0, "realized_pnl": 0.0,
            "peak_equity": START_KRW, "max_drawdown_pct": 0.0, "buy_count": 0,
            "entry_ts": 0.0, "last_price": 0.0, "closed_trades": 0, "wins": 0,
            "gross_profit": 0.0, "gross_loss": 0.0, "sum_return_pct": 0.0,
            "last_memory_id": 0, "updated_ts": now,
        }

    @staticmethod
    def _blank_learning(exp_id: str, market: str) -> dict[str, Any]:
        return {
            "experiment_id": exp_id, "market": market, "entry_bias": 0.0,
            "weight_multiplier": 1.0, "ema_return_pct": 0.0,
            "closed_trades": 0, "wins": 0, "updated_ts": time.time(),
        }

    def _load_accounts(self, exchange: str) -> dict[tuple[str, str], dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM strategy_lab_accounts WHERE exchange=?", (exchange,)
        ).fetchall()
        return {(str(row["experiment_id"]), str(row["market"])): dict(row) for row in rows}

    def _load_learning(self, experiment_ids: list[str]) -> dict[tuple[str, str], dict[str, Any]]:
        if not experiment_ids:
            return {}
        placeholders = ",".join("?" for _ in experiment_ids)
        rows = self.conn.execute(
            f"SELECT * FROM strategy_lab_learning WHERE experiment_id IN ({placeholders})",
            tuple(experiment_ids),
        ).fetchall()
        return {(str(row["experiment_id"]), str(row["market"])): dict(row) for row in rows}

    @staticmethod
    def _entry_reason(spec: StyleSpec, row: dict[str, Any], learning: dict[str, Any]) -> str:
        regime = _num(row.get("regime_score"))
        entry = _num(row.get("entry_score"))
        opportunity = _num(row.get("opportunity_score"))
        volatility = _num(row.get("volatility_pct"))
        pullback = _num(row.get("pullback_pct"))
        asset_ret = _num(row.get("asset_return_pct"))
        relative = _num(row.get("asset_vs_majors_pct"))
        fib = row.get("fib_retrace")
        bias = _num(learning.get("entry_bias"))
        if volatility > spec.max_volatility_pct:
            return ""
        if regime < spec.entry_regime + bias or entry < spec.entry_score + bias or opportunity < spec.opportunity + bias:
            return ""
        if spec.key == "conservative" and (pullback < 2.0 or pullback > 18.0 or relative < -2.0):
            return ""
        if spec.key == "contrarian":
            if pullback < 6.0 or pullback > 28.0 or asset_ret > 2.0:
                return ""
            if fib is not None and not (0.30 <= _num(fib) <= 0.75):
                return ""
            return "meaningful pullback with surviving regime"
        if spec.key == "swing" and (asset_ret <= 0.0 or relative < -1.5):
            return ""
        if spec.key == "dca" and pullback < 2.0:
            return ""
        return "style thresholds satisfied"

    @staticmethod
    def _mark_account(account: dict[str, Any], price: float, memory_id: int) -> None:
        account["last_price"] = price
        equity = _num(account.get("cash_krw")) + _num(account.get("volume")) * price
        peak = max(_num(account.get("peak_equity"), START_KRW), equity)
        drawdown = (equity / peak - 1.0) * 100.0 if peak > 0 else 0.0
        account["peak_equity"] = peak
        account["max_drawdown_pct"] = min(_num(account.get("max_drawdown_pct")), drawdown)
        account["last_memory_id"] = memory_id
        account["updated_ts"] = time.time()

    def _buy(
        self,
        *,
        account: dict[str, Any], learning: dict[str, Any], spec: StyleSpec,
        row: dict[str, Any], reason: str,
    ) -> dict[str, Any] | None:
        price = _num(row.get("price"))
        if price <= 0:
            return None
        current_value = _num(account.get("volume")) * price
        max_value = START_KRW * spec.max_position_pct / 100.0
        room = max(0.0, max_value - current_value)
        multiplier = min(1.25, max(0.55, _num(learning.get("weight_multiplier"), 1.0)))
        desired = START_KRW * spec.base_weight_pct / 100.0 * multiplier
        if int(account.get("buy_count") or 0) > 0:
            desired *= 0.78 if spec.key != "dca" else 0.92
        order_krw = min(_num(account.get("cash_krw")), room, desired)
        if order_krw < 50_000.0:
            return None
        fill_price = price * (1.0 + SLIPPAGE_RATE)
        net_notional = order_krw / (1.0 + FEE_RATE)
        volume = net_notional / fill_price
        old_volume = _num(account.get("volume"))
        old_cost = old_volume * _num(account.get("avg_price"))
        new_volume = old_volume + volume
        account["cash_krw"] = _num(account.get("cash_krw")) - order_krw
        account["volume"] = new_volume
        account["avg_price"] = (old_cost + order_krw) / new_volume if new_volume > 0 else 0.0
        account["buy_count"] = int(account.get("buy_count") or 0) + 1
        if old_volume <= 0:
            account["entry_ts"] = _num(row.get("signal_ts"), _num(row.get("ts")))
        return {
            "side": "buy", "price": fill_price, "volume": volume, "krw": order_krw,
            "realized_pnl": 0.0, "return_pct": 0.0, "reason": reason,
            "buy_index": int(account["buy_count"]),
        }

    def _sell(
        self,
        *,
        account: dict[str, Any], learning: dict[str, Any], row: dict[str, Any], reason: str,
    ) -> dict[str, Any] | None:
        price = _num(row.get("price"))
        volume = _num(account.get("volume"))
        avg_price = _num(account.get("avg_price"))
        if price <= 0 or volume <= 0 or avg_price <= 0:
            return None
        fill_price = price * (1.0 - SLIPPAGE_RATE)
        gross = volume * fill_price
        proceeds = gross * (1.0 - FEE_RATE)
        basis = volume * avg_price
        realized = proceeds - basis
        return_pct = realized / basis * 100.0 if basis > 0 else 0.0
        account["cash_krw"] = _num(account.get("cash_krw")) + proceeds
        account["volume"] = 0.0
        account["avg_price"] = 0.0
        account["realized_pnl"] = _num(account.get("realized_pnl")) + realized
        account["buy_count"] = 0
        account["entry_ts"] = 0.0
        account["closed_trades"] = int(account.get("closed_trades") or 0) + 1
        account["sum_return_pct"] = _num(account.get("sum_return_pct")) + return_pct
        if realized > 0:
            account["wins"] = int(account.get("wins") or 0) + 1
            account["gross_profit"] = _num(account.get("gross_profit")) + realized
        else:
            account["gross_loss"] = _num(account.get("gross_loss")) + realized

        closed = int(learning.get("closed_trades") or 0) + 1
        wins = int(learning.get("wins") or 0) + (1 if return_pct > 0 else 0)
        old_ema = _num(learning.get("ema_return_pct"))
        learning["ema_return_pct"] = return_pct if closed == 1 else old_ema * 0.82 + return_pct * 0.18
        learning["closed_trades"] = closed
        learning["wins"] = wins
        if return_pct > 0:
            learning["entry_bias"] = max(-2.0, _num(learning.get("entry_bias")) - 0.08)
            learning["weight_multiplier"] = min(1.20, _num(learning.get("weight_multiplier"), 1.0) * 1.012)
        else:
            learning["entry_bias"] = min(5.0, _num(learning.get("entry_bias")) + 0.22)
            learning["weight_multiplier"] = max(0.60, _num(learning.get("weight_multiplier"), 1.0) * 0.975)
        learning["updated_ts"] = time.time()
        return {
            "side": "sell", "price": fill_price, "volume": volume, "krw": proceeds,
            "realized_pnl": realized, "return_pct": return_pct, "reason": reason,
            "buy_index": 0,
        }

    def _process_style(
        self,
        *,
        experiment: dict[str, Any], spec: StyleSpec, row: dict[str, Any],
        account: dict[str, Any], learning: dict[str, Any],
    ) -> dict[str, Any] | None:
        price = _num(row.get("price"))
        if price <= 0:
            return None
        volume = _num(account.get("volume"))
        avg_price = _num(account.get("avg_price"))
        held_seconds = max(0.0, _num(row.get("signal_ts"), _num(row.get("ts"))) - _num(account.get("entry_ts")))
        if volume > 0 and avg_price > 0:
            pnl_pct = (price / avg_price - 1.0) * 100.0
            if pnl_pct <= spec.stop_loss_pct:
                return self._sell(account=account, learning=learning, row=row, reason="style hard stop")
            if pnl_pct >= spec.take_profit_pct:
                return self._sell(account=account, learning=learning, row=row, reason="style take profit")
            if held_seconds >= spec.min_hold_seconds and _num(row.get("regime_score")) < spec.exit_regime:
                return self._sell(account=account, learning=learning, row=row, reason="regime weakened")
            if int(account.get("buy_count") or 0) < spec.max_buys:
                drop_from_avg = (price / avg_price - 1.0) * 100.0
                entry_reason = self._entry_reason(spec, row, learning)
                if entry_reason and drop_from_avg <= -spec.add_drop_pct:
                    return self._buy(
                        account=account, learning=learning, spec=spec, row=row,
                        reason=f"style add after {abs(drop_from_avg):.2f}% drop",
                    )
            return None
        entry_reason = self._entry_reason(spec, row, learning)
        if entry_reason:
            return self._buy(account=account, learning=learning, spec=spec, row=row, reason=entry_reason)
        return None

    def _upsert_account(self, account: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO strategy_lab_accounts(
                experiment_id,exchange,market,cash_krw,volume,avg_price,realized_pnl,peak_equity,
                max_drawdown_pct,buy_count,entry_ts,last_price,closed_trades,wins,gross_profit,
                gross_loss,sum_return_pct,last_memory_id,updated_ts
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(experiment_id,market) DO UPDATE SET
                cash_krw=excluded.cash_krw,volume=excluded.volume,avg_price=excluded.avg_price,
                realized_pnl=excluded.realized_pnl,peak_equity=excluded.peak_equity,
                max_drawdown_pct=excluded.max_drawdown_pct,buy_count=excluded.buy_count,
                entry_ts=excluded.entry_ts,last_price=excluded.last_price,closed_trades=excluded.closed_trades,
                wins=excluded.wins,gross_profit=excluded.gross_profit,gross_loss=excluded.gross_loss,
                sum_return_pct=excluded.sum_return_pct,last_memory_id=excluded.last_memory_id,
                updated_ts=excluded.updated_ts""",
            (
                account["experiment_id"], account["exchange"], account["market"], account["cash_krw"],
                account["volume"], account["avg_price"], account["realized_pnl"], account["peak_equity"],
                account["max_drawdown_pct"], int(account["buy_count"]), account["entry_ts"],
                account["last_price"], int(account["closed_trades"]), int(account["wins"]),
                account["gross_profit"], account["gross_loss"], account["sum_return_pct"],
                int(account["last_memory_id"]), account["updated_ts"],
            ),
        )

    def _upsert_learning(self, learning: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO strategy_lab_learning(
                experiment_id,market,entry_bias,weight_multiplier,ema_return_pct,closed_trades,wins,updated_ts
            ) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(experiment_id,market) DO UPDATE SET
                entry_bias=excluded.entry_bias,weight_multiplier=excluded.weight_multiplier,
                ema_return_pct=excluded.ema_return_pct,closed_trades=excluded.closed_trades,
                wins=excluded.wins,updated_ts=excluded.updated_ts""",
            (
                learning["experiment_id"], learning["market"], learning["entry_bias"],
                learning["weight_multiplier"], learning["ema_return_pct"], int(learning["closed_trades"]),
                int(learning["wins"]), learning["updated_ts"],
            ),
        )

    def _insert_trade(self, experiment: dict[str, Any], row: dict[str, Any], trade: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO strategy_lab_trades(
                experiment_id,exchange,market,style,ts,source_memory_id,side,price,volume,krw,
                realized_pnl,return_pct,reason,buy_index
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                experiment["experiment_id"], experiment["exchange"], row["market"], experiment["style"],
                _num(row.get("signal_ts"), _num(row.get("ts"))), int(row["id"]), trade["side"],
                trade["price"], trade["volume"], trade["krw"], trade["realized_pnl"], trade["return_pct"],
                trade["reason"], int(trade["buy_index"]),
            ),
        )

    def _refresh_metrics(self, experiment: dict[str, Any]) -> dict[str, Any]:
        rows = self.conn.execute(
            "SELECT * FROM strategy_lab_accounts WHERE experiment_id=?", (experiment["experiment_id"],)
        ).fetchall()
        markets = len(rows)
        active = 0
        equity = 0.0
        realized = 0.0
        max_dd = 0.0
        closed = wins = 0
        gross_profit = gross_loss = sum_return = 0.0
        for source in rows:
            row = dict(source)
            volume = _num(row.get("volume"))
            price = _num(row.get("last_price"), _num(row.get("avg_price")))
            if volume > 0:
                active += 1
            equity += _num(row.get("cash_krw")) + volume * price
            realized += _num(row.get("realized_pnl"))
            max_dd = min(max_dd, _num(row.get("max_drawdown_pct")))
            closed += int(row.get("closed_trades") or 0)
            wins += int(row.get("wins") or 0)
            gross_profit += _num(row.get("gross_profit"))
            gross_loss += _num(row.get("gross_loss"))
            sum_return += _num(row.get("sum_return_pct"))
        aggregate_start = START_KRW * markets
        ret = (equity / aggregate_start - 1.0) * 100.0 if aggregate_start > 0 else 0.0
        win_rate = wins / closed * 100.0 if closed else 0.0
        expectancy = sum_return / closed if closed else 0.0
        profit_factor = gross_profit / abs(gross_loss) if gross_loss < 0 else (999.0 if gross_profit > 0 else 0.0)
        now = time.time()
        self.conn.execute(
            """INSERT INTO strategy_lab_metrics(
                experiment_id,exchange,style,markets,active_positions,total_equity_krw,aggregate_start_krw,
                return_pct,realized_pnl,max_drawdown_pct,closed_trades,wins,win_rate_pct,expectancy_pct,
                profit_factor,updated_ts
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(experiment_id) DO UPDATE SET
                markets=excluded.markets,active_positions=excluded.active_positions,
                total_equity_krw=excluded.total_equity_krw,aggregate_start_krw=excluded.aggregate_start_krw,
                return_pct=excluded.return_pct,realized_pnl=excluded.realized_pnl,
                max_drawdown_pct=excluded.max_drawdown_pct,closed_trades=excluded.closed_trades,
                wins=excluded.wins,win_rate_pct=excluded.win_rate_pct,expectancy_pct=excluded.expectancy_pct,
                profit_factor=excluded.profit_factor,updated_ts=excluded.updated_ts""",
            (
                experiment["experiment_id"], experiment["exchange"], experiment["style"], markets, active,
                equity, aggregate_start, ret, realized, max_dd, closed, wins, win_rate, expectancy,
                profit_factor, now,
            ),
        )
        return {
            "experiment_id": experiment["experiment_id"], "exchange": experiment["exchange"],
            "style": experiment["style"], "label": experiment["label"], "markets": markets,
            "active_positions": active, "return_pct": round(ret, 6), "realized_pnl": round(realized, 2),
            "max_drawdown_pct": round(max_dd, 4), "closed_trades": closed,
            "win_rate_pct": round(win_rate, 3), "expectancy_pct": round(expectancy, 4),
            "profit_factor": round(profit_factor, 4), "updated_ts": now,
        }

    def process_exchange(self, exchange: str, limit: int = MAX_SOURCE_ROWS_PER_RUN) -> dict[str, Any]:
        exchange = exchange.lower()
        experiments = self._experiments(exchange)
        if not experiments:
            return {"exchange": exchange, "source_rows": 0, "trades": 0, "experiments": 0, "metrics": []}
        state = self.conn.execute(
            "SELECT last_memory_id FROM strategy_lab_ingest_state WHERE exchange=?", (exchange,)
        ).fetchone()
        cursor = int(state["last_memory_id"] if state else 0)
        source_rows = self.conn.execute(
            """SELECT id,ts,signal_ts,exchange,market,strategy,price,regime_score,entry_score,
                      opportunity_score,asset_return_pct,pullback_pct,volatility_pct,orderbook_imbalance,
                      fib_retrace,btc_return_pct,eth_return_pct,asset_vs_majors_pct
               FROM research_market_memory_mx
               WHERE exchange=? AND strategy=? AND id>? ORDER BY id ASC LIMIT ?""",
            (exchange, SOURCE_STRATEGY, cursor, max(1, int(limit))),
        ).fetchall()
        if not source_rows:
            metrics = [self._refresh_metrics(exp) for exp in experiments]
            self.conn.commit()
            return {"exchange": exchange, "source_rows": 0, "trades": 0, "experiments": len(experiments), "metrics": metrics}

        accounts = self._load_accounts(exchange)
        exp_ids = [str(exp["experiment_id"]) for exp in experiments]
        learning_rows = self._load_learning(exp_ids)
        touched_accounts: set[tuple[str, str]] = set()
        touched_learning: set[tuple[str, str]] = set()
        trade_count = 0
        last_id = cursor

        for source in source_rows:
            row = dict(source)
            last_id = int(row["id"])
            market = str(row["market"])
            price = _num(row.get("price"))
            if price <= 0:
                continue
            for exp in experiments:
                style = str(exp["style"])
                spec = STYLE_SPECS.get(style)
                if not spec:
                    continue
                key = (str(exp["experiment_id"]), market)
                account = accounts.get(key)
                if account is None:
                    account = self._blank_account(key[0], exchange, market)
                    accounts[key] = account
                learning = learning_rows.get(key)
                if learning is None:
                    learning = self._blank_learning(key[0], market)
                    learning_rows[key] = learning
                trade = self._process_style(
                    experiment=exp, spec=spec, row=row, account=account, learning=learning,
                )
                self._mark_account(account, price, int(row["id"]))
                touched_accounts.add(key)
                if trade:
                    self._insert_trade(exp, row, trade)
                    trade_count += 1
                    if trade["side"] == "sell":
                        touched_learning.add(key)

        with self.conn:
            for key in touched_accounts:
                self._upsert_account(accounts[key])
            for key in touched_learning:
                self._upsert_learning(learning_rows[key])
            self.conn.execute(
                """UPDATE strategy_lab_ingest_state SET last_memory_id=?,updated_ts=? WHERE exchange=?""",
                (last_id, time.time(), exchange),
            )
            metrics = [self._refresh_metrics(exp) for exp in experiments]
        return {
            "exchange": exchange, "source_rows": len(source_rows), "trades": trade_count,
            "cursor_before": cursor, "cursor_after": last_id, "experiments": len(experiments),
            "metrics": metrics,
        }

    def snapshot(self) -> dict[str, Any]:
        metrics = self.conn.execute(
            """SELECT m.*,e.label,e.description,e.strategy_key,e.status
               FROM strategy_lab_metrics m JOIN strategy_lab_experiments e USING(experiment_id)
               ORDER BY m.exchange,m.return_pct DESC"""
        ).fetchall()
        rows: list[dict[str, Any]] = []
        for source in metrics:
            row = dict(source)
            for key in (
                "return_pct", "realized_pnl", "max_drawdown_pct", "win_rate_pct",
                "expectancy_pct", "profit_factor", "total_equity_krw", "aggregate_start_krw",
            ):
                row[key] = round(_num(row.get(key)), 6 if key == "return_pct" else 4)
            rows.append(row)
        states = {
            str(row["exchange"]): int(row["last_memory_id"])
            for row in self.conn.execute("SELECT exchange,last_memory_id FROM strategy_lab_ingest_state").fetchall()
        }
        styles = [asdict(spec) for spec in STYLE_SPECS.values()]
        return {
            "version": 1,
            "paper_only": True,
            "source": "research_market_memory_mx",
            "source_strategy": SOURCE_STRATEGY,
            "execution_model": {"fee_rate": FEE_RATE, "slippage_rate": SLIPPAGE_RATE},
            "styles": styles,
            "experiments": rows,
            "source_cursors": states,
            "updated_at": max([0.0] + [_num(row.get("updated_ts")) for row in rows]),
        }

    def close(self) -> None:
        self.conn.close()


class StrategyLabRunner:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path

    def run_once(self) -> dict[str, Any]:
        store = StrategyLabStore(self.path)
        try:
            results = [store.process_exchange(exchange) for exchange in ("bithumb", "upbit")]
            snapshot = store.snapshot()
            experiments = snapshot.get("experiments") or []
            leaders: dict[str, dict[str, Any] | None] = {}
            for exchange in ("bithumb", "upbit"):
                candidates = [row for row in experiments if row.get("exchange") == exchange]
                candidates.sort(key=lambda row: (_num(row.get("return_pct")), -abs(_num(row.get("max_drawdown_pct")))), reverse=True)
                leaders[exchange] = candidates[0] if candidates else None
            return {
                "status": "processed",
                "paper_only": True,
                "source_rows": sum(int(row.get("source_rows") or 0) for row in results),
                "trades": sum(int(row.get("trades") or 0) for row in results),
                "experiment_count": len(experiments),
                "leaders": leaders,
                "by_exchange": results,
            }
        finally:
            store.close()


def strategy_lab_snapshot(path: Path = DB_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "paper_only": True, "styles": [asdict(spec) for spec in STYLE_SPECS.values()], "experiments": []}
    store = StrategyLabStore(path)
    try:
        return store.snapshot()
    finally:
        store.close()
