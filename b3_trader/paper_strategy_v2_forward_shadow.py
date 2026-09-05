from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH, BTC_FLASH_CRASH_PCT, BTC_FLASH_WINDOW_CANDLES, MAX_SLIPPAGE_BPS, MAX_SPREAD_BPS
from .exchange_public import PublicExchangeAdapter, public_exchange
from .paper_exit_policy_v2 import evaluate_exit
from .paper_portfolio_risk_v2 import PortfolioRiskPolicy, cap_plan_to_portfolio_risk
from .paper_position_plan_v2 import LadderRung, PositionPlanV2, PositionSizingPolicy, evaluate_next_add, plan_new_position
from .risk import estimate_buy, estimate_sell, recent_move_pct, spread_bps

FEE_RATE = 0.0004
STATUS_PATH = Path("b3_trader/data/paper-v2-forward-shadow.json")


def balanced_policy() -> tuple[PositionSizingPolicy, PortfolioRiskPolicy]:
    return (
        PositionSizingPolicy(
            portfolio_capital_krw=10_000_000.0,
            max_gross_exposure_pct=60.0,
            reserve_cash_pct=25.0,
            max_position_pct=25.0,
            risk_budget_pct=2.0,
            min_order_krw=100_000.0,
            min_regime_for_new=50.0,
            min_entry_for_new=55.0,
            min_opportunity_for_new=58.0,
            thesis_regime_floor=35.0,
        ),
        PortfolioRiskPolicy(max_portfolio_risk_pct=5.0, min_initial_order_krw=100_000.0),
    )


def _num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _safe_json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _plan_from_json(value: str) -> PositionPlanV2:
    data = _safe_json(value)
    ladder = tuple(LadderRung(**row) for row in data.get("ladder", []) if isinstance(row, dict))
    return PositionPlanV2(
        allowed=bool(data.get("allowed")), reason=str(data.get("reason") or ""),
        portfolio_capital_krw=_num(data.get("portfolio_capital_krw")), first_entry_price=_num(data.get("first_entry_price")),
        desired_position_pct=_num(data.get("desired_position_pct")), target_position_krw=_num(data.get("target_position_krw")),
        reserved_position_krw=_num(data.get("reserved_position_krw")), stop_distance_pct=_num(data.get("stop_distance_pct")),
        invalidation_price=_num(data.get("invalidation_price")), risk_budget_krw=_num(data.get("risk_budget_krw")),
        worst_case_loss_krw=_num(data.get("worst_case_loss_krw")), thesis_regime_floor=_num(data.get("thesis_regime_floor")),
        ladder=ladder, paper_only=True, can_place_real_orders=False,
    )


class PaperV2ForwardShadowRunner:
    """Forward-only shared-portfolio PAPER runtime.

    It shares no account state with the legacy per-market PAPER engine and has no
    private exchange credentials or real-order path. Public Bithumb order books
    are used only to model spread/slippage for PAPER fills.
    """

    def __init__(self, path: Path | str = DB_PATH, adapter: PublicExchangeAdapter | None = None) -> None:
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.adapter = adapter or public_exchange("bithumb")
        self.policy, self.risk_policy = balanced_policy()
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_paper_v2_account (
                id INTEGER PRIMARY KEY CHECK(id=1), cash_krw REAL NOT NULL, realized_pnl REAL NOT NULL DEFAULT 0,
                peak_equity REAL NOT NULL, max_drawdown_pct REAL NOT NULL DEFAULT 0, updated_ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS research_paper_v2_positions (
                market TEXT PRIMARY KEY, plan_json TEXT NOT NULL, entry_ts REAL NOT NULL,
                entry_regime REAL NOT NULL, entry_opportunity REAL NOT NULL, volume REAL NOT NULL,
                cost_cash REAL NOT NULL, completed_entries INTEGER NOT NULL, peak_price REAL NOT NULL,
                add_count INTEGER NOT NULL DEFAULT 0, updated_ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS research_paper_v2_fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, market TEXT NOT NULL, side TEXT NOT NULL,
                price REAL NOT NULL, volume REAL NOT NULL, krw REAL NOT NULL, fee_krw REAL NOT NULL,
                realized_pnl REAL NOT NULL DEFAULT 0, return_pct REAL NOT NULL DEFAULT 0, reason TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS research_paper_v2_equity (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, equity_krw REAL NOT NULL,
                cash_krw REAL NOT NULL, gross_exposure_krw REAL NOT NULL, reserved_risk_krw REAL NOT NULL
            );
            """
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO research_paper_v2_account(id,cash_krw,realized_pnl,peak_equity,max_drawdown_pct,updated_ts) VALUES(1,?,?,?,?,?)",
            (self.policy.portfolio_capital_krw, 0.0, self.policy.portfolio_capital_krw, 0.0, time.time()),
        )
        self.conn.commit()

    def _account(self) -> dict[str, Any]:
        return dict(self.conn.execute("SELECT * FROM research_paper_v2_account WHERE id=1").fetchone())

    def _positions(self) -> dict[str, dict[str, Any]]:
        return {str(row["market"]): dict(row) for row in self.conn.execute("SELECT * FROM research_paper_v2_positions")}

    def _signals(self) -> list[dict[str, Any]]:
        exists = self.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_signals_mx'").fetchone()
        if not exists:
            return []
        rows = self.conn.execute(
            """SELECT exchange,market,strategy,symbol,price,regime_score,entry_score,opportunity_score,trade_intent,signal_json
               FROM research_signals_mx WHERE exchange='bithumb' AND strategy='adaptive'"""
        ).fetchall()
        output: list[dict[str, Any]] = []
        for source in rows:
            row = dict(source)
            row["signal"] = _safe_json(row.pop("signal_json", "{}"))
            output.append(row)
        return output

    @staticmethod
    def _position_plan(row: dict[str, Any]) -> PositionPlanV2:
        return _plan_from_json(str(row["plan_json"]))

    def _reserved_risk(self, positions: dict[str, dict[str, Any]]) -> float:
        return round(sum(self._position_plan(row).worst_case_loss_krw for row in positions.values()), 2)

    def _reserved_exposure(self, positions: dict[str, dict[str, Any]]) -> float:
        return round(sum(self._position_plan(row).reserved_position_krw for row in positions.values()), 2)

    def _paper_buy(self, market: str, position: dict[str, Any], order_krw: float, orderbook: dict[str, Any], reason: str) -> bool:
        account = self._account()
        spread = spread_bps(orderbook)
        fill_price, slip = estimate_buy(orderbook, order_krw)
        if not math.isfinite(spread) or spread > MAX_SPREAD_BPS or not math.isfinite(slip) or slip > MAX_SLIPPAGE_BPS:
            return False
        if not math.isfinite(fill_price) or fill_price <= 0:
            return False
        fee = order_krw * FEE_RATE
        cash_used = order_krw + fee
        if cash_used > _num(account.get("cash_krw")):
            return False
        volume = order_krw / fill_price
        old_volume = _num(position.get("volume"))
        position["volume"] = old_volume + volume
        position["cost_cash"] = _num(position.get("cost_cash")) + cash_used
        position["completed_entries"] = int(position.get("completed_entries") or 0) + 1
        position["peak_price"] = max(_num(position.get("peak_price")), fill_price)
        position["updated_ts"] = time.time()
        self.conn.execute("UPDATE research_paper_v2_account SET cash_krw=?,updated_ts=? WHERE id=1", (_num(account.get("cash_krw")) - cash_used, time.time()))
        self.conn.execute(
            """INSERT INTO research_paper_v2_positions(market,plan_json,entry_ts,entry_regime,entry_opportunity,volume,cost_cash,completed_entries,peak_price,add_count,updated_ts)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(market) DO UPDATE SET volume=excluded.volume,cost_cash=excluded.cost_cash,completed_entries=excluded.completed_entries,peak_price=excluded.peak_price,add_count=excluded.add_count,updated_ts=excluded.updated_ts""",
            (market, position["plan_json"], position["entry_ts"], position["entry_regime"], position["entry_opportunity"], position["volume"], position["cost_cash"], position["completed_entries"], position["peak_price"], int(position.get("add_count") or 0), time.time()),
        )
        self.conn.execute(
            "INSERT INTO research_paper_v2_fills(ts,market,side,price,volume,krw,fee_krw,reason) VALUES(?,?,?,?,?,?,?,?)",
            (time.time(), market, "buy", fill_price, volume, order_krw, fee, reason),
        )
        self.conn.commit()
        return True

    def _paper_sell(self, market: str, position: dict[str, Any], orderbook: dict[str, Any], reason: str) -> bool:
        volume = _num(position.get("volume"))
        if volume <= 0:
            return False
        fill_price, _slip = estimate_sell(orderbook, volume)
        if not math.isfinite(fill_price) or fill_price <= 0:
            return False
        gross = volume * fill_price
        fee = gross * FEE_RATE
        proceeds = gross - fee
        cost = _num(position.get("cost_cash"))
        pnl = proceeds - cost
        ret = pnl / cost * 100.0 if cost > 0 else 0.0
        account = self._account()
        self.conn.execute(
            "UPDATE research_paper_v2_account SET cash_krw=?,realized_pnl=?,updated_ts=? WHERE id=1",
            (_num(account.get("cash_krw")) + proceeds, _num(account.get("realized_pnl")) + pnl, time.time()),
        )
        self.conn.execute(
            "INSERT INTO research_paper_v2_fills(ts,market,side,price,volume,krw,fee_krw,realized_pnl,return_pct,reason) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (time.time(), market, "sell", fill_price, volume, proceeds, fee, pnl, ret, reason),
        )
        self.conn.execute("DELETE FROM research_paper_v2_positions WHERE market=?", (market,))
        self.conn.commit()
        return True

    def _mark(self, signals_by_market: dict[str, dict[str, Any]]) -> dict[str, float]:
        account = self._account()
        positions = self._positions()
        gross = 0.0
        for market, position in positions.items():
            signal = signals_by_market.get(market) or {}
            price = _num(signal.get("price"), _num(position.get("peak_price")))
            gross += _num(position.get("volume")) * price
        equity = _num(account.get("cash_krw")) + gross
        peak = max(_num(account.get("peak_equity"), self.policy.portfolio_capital_krw), equity)
        dd = (equity / peak - 1.0) * 100.0 if peak > 0 else 0.0
        max_dd = min(_num(account.get("max_drawdown_pct")), dd)
        self.conn.execute("UPDATE research_paper_v2_account SET peak_equity=?,max_drawdown_pct=?,updated_ts=? WHERE id=1", (peak, max_dd, time.time()))
        reserved_risk = self._reserved_risk(positions)
        self.conn.execute(
            "INSERT INTO research_paper_v2_equity(ts,equity_krw,cash_krw,gross_exposure_krw,reserved_risk_krw) VALUES(?,?,?,?,?)",
            (time.time(), equity, _num(account.get("cash_krw")), gross, reserved_risk),
        )
        self.conn.commit()
        return {"equity_krw": round(equity, 2), "gross_exposure_krw": round(gross, 2), "reserved_risk_krw": round(reserved_risk, 2), "max_drawdown_pct": round(max_dd, 4)}

    def run_once(self) -> dict[str, Any]:
        signals = self._signals()
        signals_by_market = {str(row.get("market") or ""): row for row in signals}
        positions = self._positions()
        orders = {"initial": 0, "adds": 0, "sells": 0, "blocked": 0}
        btc_candles = self.adapter.candles_minutes("KRW-BTC", unit=5, count=8) if signals else []
        btc_flash = recent_move_pct(btc_candles, BTC_FLASH_WINDOW_CANDLES) <= BTC_FLASH_CRASH_PCT if btc_candles else False

        for market, position in list(positions.items()):
            signal = signals_by_market.get(market)
            if not signal:
                continue
            price = _num(signal.get("price"))
            position["peak_price"] = max(_num(position.get("peak_price")), price)
            plan = self._position_plan(position)
            exit_decision = evaluate_exit(
                plan, average_price=_num(position.get("cost_cash")) / _num(position.get("volume")) if _num(position.get("volume")) > 0 else 0.0,
                current_price=price, peak_price=_num(position.get("peak_price")), current_regime_score=_num(signal.get("regime_score")),
                current_opportunity_score=_num(signal.get("opportunity_score")), holding_seconds=max(0.0, time.time() - _num(position.get("entry_ts"))),
                entry_opportunity_score=_num(position.get("entry_opportunity")), entry_regime_score=_num(position.get("entry_regime")),
            )
            orderbook = self.adapter.orderbook(market)
            if exit_decision.action == "sell":
                if self._paper_sell(market, position, orderbook, exit_decision.reason):
                    orders["sells"] += 1
                else:
                    orders["blocked"] += 1
                continue
            next_index = int(position.get("completed_entries") or 0)
            next_order = plan.ladder[next_index].order_krw if next_index < len(plan.ladder) else 0.0
            spread = spread_bps(orderbook)
            _fill, slip = estimate_buy(orderbook, next_order) if next_order > 0 else (0.0, 0.0)
            add = evaluate_next_add(
                plan, completed_entries=next_index, current_price=price, current_regime_score=_num(signal.get("regime_score")),
                lifecycle_add_allowed=True, spread_ok=math.isfinite(spread) and spread <= MAX_SPREAD_BPS,
                slippage_ok=math.isfinite(slip) and slip <= MAX_SLIPPAGE_BPS, btc_flash_crash=btc_flash,
            )
            if add.action == "invalidate":
                if self._paper_sell(market, position, orderbook, add.reason):
                    orders["sells"] += 1
            elif add.action == "add":
                position["add_count"] = int(position.get("add_count") or 0) + 1
                if self._paper_buy(market, position, add.order_krw, orderbook, add.reason):
                    orders["adds"] += 1
                else:
                    orders["blocked"] += 1

        positions = self._positions()
        available_slots = max(0, 3 - len(positions))
        candidates = sorted(
            [row for row in signals if str(row.get("market") or "") not in positions],
            key=lambda row: (_num(row.get("opportunity_score")), _num(row.get("entry_score")), _num(row.get("regime_score"))), reverse=True,
        )
        for signal in candidates:
            if available_slots <= 0:
                break
            market = str(signal.get("market") or "")
            signal_payload = signal.get("signal") if isinstance(signal.get("signal"), dict) else {}
            plan = plan_new_position(
                first_entry_price=_num(signal.get("price")), regime_score=_num(signal.get("regime_score")), entry_score=_num(signal.get("entry_score")),
                opportunity_score=_num(signal.get("opportunity_score")), volatility_pct=_num(signal_payload.get("volatility_pct")),
                current_reserved_exposure_krw=self._reserved_exposure(positions), available_cash_krw=_num(self._account().get("cash_krw")), policy=self.policy,
            )
            plan = cap_plan_to_portfolio_risk(plan, current_reserved_risk_krw=self._reserved_risk(positions), risk_policy=self.risk_policy)
            if not plan.allowed or btc_flash:
                continue
            position = {
                "market": market, "plan_json": json.dumps(plan.to_dict(), ensure_ascii=False, separators=(",", ":")), "entry_ts": time.time(),
                "entry_regime": _num(signal.get("regime_score")), "entry_opportunity": _num(signal.get("opportunity_score")),
                "volume": 0.0, "cost_cash": 0.0, "completed_entries": 0, "peak_price": _num(signal.get("price")), "add_count": 0,
            }
            orderbook = self.adapter.orderbook(market)
            if self._paper_buy(market, position, plan.initial_order_krw, orderbook, "balanced_v2_initial"):
                orders["initial"] += 1
                available_slots -= 1
                positions = self._positions()
            else:
                orders["blocked"] += 1

        metrics = self._mark(signals_by_market)
        positions = self._positions()
        account = self._account()
        return {
            "ok": True, "status": "running", "paper_only": True, "shadow_only": True, "can_place_real_orders": False,
            "private_exchange_credentials_used": False, "shared_portfolio_budget": True, "preset": "balanced_60_25_r2_agg5",
            "portfolio_capital_krw": self.policy.portfolio_capital_krw, "cash_krw": round(_num(account.get("cash_krw")), 2),
            "equity_krw": metrics["equity_krw"], "gross_exposure_krw": metrics["gross_exposure_krw"], "reserved_risk_krw": metrics["reserved_risk_krw"],
            "reserved_risk_pct": round(metrics["reserved_risk_krw"] / self.policy.portfolio_capital_krw * 100.0, 4),
            "max_drawdown_pct": metrics["max_drawdown_pct"], "open_positions": len(positions), "orders": orders,
            "max_portfolio_risk_pct": self.risk_policy.max_portfolio_risk_pct, "max_gross_exposure_pct": self.policy.max_gross_exposure_pct,
            "updated_at": time.time(),
        }
