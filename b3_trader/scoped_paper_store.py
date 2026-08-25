from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .auto_demo_v2 import DB_PATH, START_KRW, _json_load, _num
from .multi_exchange_store import MultiExchangeStore, paper_key


class ScopedPaperStore(MultiExchangeStore):
    """DemoStore-compatible facade scoped to exchange + market + strategy."""

    def __init__(self, exchange: str, strategy: str = "adaptive", path: Path = DB_PATH) -> None:
        self.exchange = exchange.strip().lower()
        self.strategy = strategy.strip().lower()
        if not self.exchange or not self.strategy:
            raise ValueError("exchange and strategy are required")
        super().__init__(path)

    @property
    def scope(self) -> tuple[str, str]:
        return self.exchange, self.strategy

    def ensure_market(self, market: str, symbol: str, name: str) -> None:  # type: ignore[override]
        super().ensure_market(self.exchange, market, self.strategy, symbol, name)

    def all_accounts(self) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM research_accounts_mx WHERE exchange=? AND strategy=?",
            self.scope,
        ).fetchall()
        return {str(row["market"]): dict(row) for row in rows}

    def all_profiles(self) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM research_profiles_mx WHERE exchange=? AND strategy=?",
            self.scope,
        ).fetchall()
        return {str(row["market"]): dict(row) for row in rows}

    def save_account(self, account: dict[str, Any]) -> None:
        self.conn.execute(
            """UPDATE research_accounts_mx SET symbol=?,name=?,cash_krw=?,volume=?,avg_price=?,realized_pnl=?,
                peak_equity=?,max_drawdown_pct=?,peak_price=?,last_buy_at=?,last_trade_at=?,entry_ts=?,
                entry_signal_json=?,updated_ts=?
                WHERE exchange=? AND market=? AND strategy=?""",
            (
                account["symbol"], account["name"], account["cash_krw"], account["volume"],
                account["avg_price"], account["realized_pnl"], account["peak_equity"],
                account["max_drawdown_pct"], account["peak_price"], account["last_buy_at"],
                account["last_trade_at"], account["entry_ts"], account["entry_signal_json"],
                time.time(), self.exchange, account["market"], self.strategy,
            ),
        )
        self.conn.commit()

    def save_profile(self, market: str, profile: dict[str, Any]) -> None:
        self.conn.execute(
            """UPDATE research_profiles_mx SET regime_floor=?,entry_floor=?,exploration_floor=?,base_weight_pct=?,
                max_position_pct=?,closed_trades=?,wins=?,ema_return_pct=?,version=?,updated_ts=?
                WHERE exchange=? AND market=? AND strategy=?""",
            (
                profile["regime_floor"], profile["entry_floor"], profile["exploration_floor"],
                profile["base_weight_pct"], profile["max_position_pct"], int(profile["closed_trades"]),
                int(profile["wins"]), profile["ema_return_pct"], int(profile["version"]), time.time(),
                self.exchange, market, self.strategy,
            ),
        )
        self.conn.commit()

    def add_fill(
        self, *, market: str, symbol: str, side: str, price: float, volume: float, krw: float,
        realized_pnl: float, reason: str, weight_pct: float = 0.0, return_pct: float = 0.0,
        signal: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO research_fills_mx(
                ts,exchange,market,strategy,symbol,side,price,volume,krw,weight_pct,
                realized_pnl,return_pct,reason,signal_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                time.time(), self.exchange, market, self.strategy, symbol, side, price, volume, krw,
                weight_pct, realized_pnl, return_pct, reason,
                json.dumps(signal or {}, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def fills(self, market: str | None = None) -> list[dict[str, Any]]:
        if market:
            rows = self.conn.execute(
                """SELECT * FROM research_fills_mx
                   WHERE exchange=? AND market=? AND strategy=? ORDER BY id ASC""",
                (self.exchange, market, self.strategy),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM research_fills_mx WHERE exchange=? AND strategy=? ORDER BY id ASC",
                self.scope,
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_fills(self, limit: int = 120, market: str | None = None) -> list[dict[str, Any]]:
        if market:
            rows = self.conn.execute(
                """SELECT * FROM research_fills_mx
                   WHERE exchange=? AND market=? AND strategy=? ORDER BY id DESC LIMIT ?""",
                (self.exchange, market, self.strategy, int(limit)),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM research_fills_mx
                   WHERE exchange=? AND strategy=? ORDER BY id DESC LIMIT ?""",
                (self.exchange, self.strategy, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def current_cycle_buy_count(self, market: str) -> int:
        rows = self.conn.execute(
            """SELECT side FROM research_fills_mx
               WHERE exchange=? AND market=? AND strategy=? ORDER BY id DESC LIMIT 80""",
            (self.exchange, market, self.strategy),
        ).fetchall()
        count = 0
        for row in rows:
            side = str(row["side"])
            if side == "sell":
                break
            if side == "buy":
                count += 1
        return count

    def save_signal(self, row: dict[str, Any]) -> None:
        payload = row.get("signal") if isinstance(row.get("signal"), dict) else {}
        self.conn.execute(
            """INSERT INTO research_signals_mx(
                exchange,market,strategy,symbol,ts,price,turnover_24h,change_24h_pct,liquidity_score,
                regime_score,entry_score,opportunity_score,strategy_action,trade_intent,
                suggested_weight_pct,reason,signal_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(exchange,market,strategy) DO UPDATE SET
                    symbol=excluded.symbol,ts=excluded.ts,price=excluded.price,
                    turnover_24h=excluded.turnover_24h,change_24h_pct=excluded.change_24h_pct,
                    liquidity_score=excluded.liquidity_score,regime_score=excluded.regime_score,
                    entry_score=excluded.entry_score,opportunity_score=excluded.opportunity_score,
                    strategy_action=excluded.strategy_action,trade_intent=excluded.trade_intent,
                    suggested_weight_pct=excluded.suggested_weight_pct,reason=excluded.reason,
                    signal_json=excluded.signal_json""",
            (
                self.exchange, row["market"], self.strategy, row["symbol"], row["ts"], row["price"],
                row["turnover_24h"], row["change_24h_pct"], row["liquidity_score"], row["regime_score"],
                row["entry_score"], row["opportunity_score"], row["strategy_action"], row["trade_intent"],
                row["suggested_weight_pct"], row["reason"], json.dumps(payload, ensure_ascii=False),
            ),
        )
        self._append_market_memory(row, payload)
        self.conn.commit()

    def _append_market_memory(self, row: dict[str, Any], signal: dict[str, Any]) -> None:
        market = str(row.get("market") or "")
        signal_ts = _num(row.get("ts"))
        if not market or signal_ts <= 0:
            return
        latest = self.conn.execute(
            """SELECT price,opportunity_score,regime_score,entry_score
               FROM research_market_memory_mx
               WHERE exchange=? AND market=? AND strategy=? ORDER BY id DESC LIMIT 1""",
            (self.exchange, market, self.strategy),
        ).fetchone()
        price_now = _num(row.get("price"))
        previous_price = _num(latest["price"]) if latest else 0.0
        opportunity = _num(row.get("opportunity_score"))
        regime = _num(row.get("regime_score"))
        entry = _num(row.get("entry_score"))
        feature_payload = {
            "strategy_action": row.get("strategy_action"),
            "reason": row.get("reason"),
            "execution_note": signal.get("execution_note"),
            "trade_plan": signal.get("trade_plan") if isinstance(signal.get("trade_plan"), dict) else {},
            "eth_vs_btc_pct": _num(signal.get("eth_vs_btc_pct")),
            "fib_retrace": signal.get("fib_retrace"),
        }
        self.conn.execute(
            """INSERT OR IGNORE INTO research_market_memory_mx(
                ts,signal_ts,exchange,market,strategy,price,change_24h_pct,turnover_24h,liquidity_score,
                regime_score,entry_score,opportunity_score,suggested_weight_pct,trade_intent,
                asset_return_pct,pullback_pct,volatility_pct,orderbook_imbalance,fib_retrace,
                btc_return_pct,eth_return_pct,asset_vs_majors_pct,price_delta_pct,opportunity_delta,
                regime_delta,entry_delta,feature_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                time.time(), signal_ts, self.exchange, market, self.strategy, price_now,
                _num(row.get("change_24h_pct")), _num(row.get("turnover_24h")), _num(row.get("liquidity_score")),
                regime, entry, opportunity, _num(row.get("suggested_weight_pct")),
                str(row.get("trade_intent") or "wait"), _num(signal.get("asset_return_pct")),
                _num(signal.get("pullback_pct")), _num(signal.get("volatility_pct")),
                _num(signal.get("orderbook_imbalance")), signal.get("fib_retrace"),
                _num(signal.get("btc_return_pct")), _num(signal.get("eth_return_pct")),
                _num(signal.get("asset_vs_majors_pct")),
                (price_now / previous_price - 1.0) * 100.0 if previous_price > 0 and price_now > 0 else 0.0,
                opportunity - (_num(latest["opportunity_score"]) if latest else opportunity),
                regime - (_num(latest["regime_score"]) if latest else regime),
                entry - (_num(latest["entry_score"]) if latest else entry),
                json.dumps(feature_payload, ensure_ascii=False, separators=(",", ":")),
            ),
        )

    def add_feedback(
        self, *, market: str, outcome_return_pct: float, realized_pnl: float, holding_seconds: float,
        profile_before: dict[str, Any], profile_after: dict[str, Any], signal: dict[str, Any], note: str,
    ) -> None:
        self.conn.execute(
            """INSERT INTO research_feedback_mx(
                ts,exchange,market,strategy,outcome_return_pct,realized_pnl,holding_seconds,
                profile_before_json,profile_after_json,signal_json,note)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                time.time(), self.exchange, market, self.strategy, outcome_return_pct, realized_pnl,
                holding_seconds, json.dumps(profile_before, ensure_ascii=False),
                json.dumps(profile_after, ensure_ascii=False), json.dumps(signal, ensure_ascii=False), note,
            ),
        )
        self.conn.commit()

    def snapshot_equity(self, market: str, equity: float, cash: float, position_value: float) -> None:
        last = self.conn.execute(
            """SELECT ts FROM research_equity_mx
               WHERE exchange=? AND market=? AND strategy=? ORDER BY id DESC LIMIT 1""",
            (self.exchange, market, self.strategy),
        ).fetchone()
        now = time.time()
        if last and now - _num(last["ts"]) < 300.0:
            return
        self.conn.execute(
            """INSERT INTO research_equity_mx(
                ts,exchange,market,strategy,equity_krw,return_pct,cash_krw,position_value_krw)
                VALUES(?,?,?,?,?,?,?,?)""",
            (now, self.exchange, market, self.strategy, equity, (equity / START_KRW - 1.0) * 100.0, cash, position_value),
        )
        self.conn.execute(
            "DELETE FROM research_equity_mx WHERE exchange=? AND strategy=? AND ts < ?",
            (self.exchange, self.strategy, now - 90 * 86400.0),
        )
        self.conn.commit()

    def leaderboard(self, limit: int = 5000) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT a.*,p.closed_trades,p.wins,p.ema_return_pct,p.version,p.base_weight_pct,p.max_position_pct,
                      s.price,s.opportunity_score,s.trade_intent,s.regime_score,s.entry_score,s.ts AS signal_ts,
                      s.suggested_weight_pct
               FROM research_accounts_mx a
               LEFT JOIN research_profiles_mx p
                 ON p.exchange=a.exchange AND p.market=a.market AND p.strategy=a.strategy
               LEFT JOIN research_signals_mx s
                 ON s.exchange=a.exchange AND s.market=a.market AND s.strategy=a.strategy
               WHERE a.exchange=? AND a.strategy=?""",
            self.scope,
        ).fetchall()
        result: list[dict[str, Any]] = []
        for source in rows:
            row = dict(source)
            current_price = _num(row.get("price"), _num(row.get("avg_price")))
            volume = _num(row.get("volume"))
            avg_price = _num(row.get("avg_price"))
            position_value = volume * current_price
            equity = _num(row.get("cash_krw")) + position_value
            closed = int(row.get("closed_trades") or 0)
            wins = int(row.get("wins") or 0)
            unrealized = position_value - volume * avg_price if volume > 0 and avg_price > 0 else 0.0
            state_class = "holding" if position_value > 0 else "completed_waiting" if closed > 0 else "untraded"
            state_label = "보유 중" if state_class == "holding" else "매매 완료 · 대기" if closed > 0 else "미진입"
            result.append(
                {
                    "exchange": self.exchange, "strategy": self.strategy,
                    "key": paper_key(self.exchange, row["market"], self.strategy),
                    "market": row["market"], "symbol": row["symbol"], "name": row["name"],
                    "equity_krw": round(equity, 2), "return_pct": round((equity / START_KRW - 1.0) * 100.0, 4),
                    "cash_krw": round(_num(row.get("cash_krw")), 2), "position_value_krw": round(position_value, 2),
                    "position_cost_krw": round(volume * avg_price, 2), "position_avg_price": round(avg_price, 12),
                    "unrealized_pnl_krw": round(unrealized, 2), "realized_pnl_krw": round(_num(row.get("realized_pnl")), 2),
                    "max_drawdown_pct": round(_num(row.get("max_drawdown_pct")), 4), "closed_trades": closed,
                    "win_rate_pct": round(wins / closed * 100.0, 2) if closed else 0.0,
                    "ema_return_pct": round(_num(row.get("ema_return_pct")), 4),
                    "profile_version": int(row.get("version") or 1), "price": round(current_price, 12),
                    "opportunity_score": round(_num(row.get("opportunity_score")), 2),
                    "regime_score": round(_num(row.get("regime_score")), 2),
                    "entry_score": round(_num(row.get("entry_score")), 2),
                    "suggested_weight_pct": round(_num(row.get("suggested_weight_pct")), 2),
                    "trade_intent": row.get("trade_intent") or "waiting", "signal_ts": _num(row.get("signal_ts")),
                    "has_position": position_value > 0, "state_class": state_class, "state_label": state_label,
                }
            )
        result.sort(key=lambda item: (item["return_pct"], item["closed_trades"], item["opportunity_score"]), reverse=True)
        return result[: max(1, int(limit))]

    def market_detail(self, market: str) -> dict[str, Any]:
        summary = next((row for row in self.leaderboard(5000) if row["market"] == market), None)
        if not summary:
            return {}
        scope = (self.exchange, market, self.strategy)
        account_row = self.conn.execute(
            "SELECT * FROM research_accounts_mx WHERE exchange=? AND market=? AND strategy=?", scope
        ).fetchone()
        profile_row = self.conn.execute(
            "SELECT * FROM research_profiles_mx WHERE exchange=? AND market=? AND strategy=?", scope
        ).fetchone()
        signal_row = self.conn.execute(
            "SELECT * FROM research_signals_mx WHERE exchange=? AND market=? AND strategy=?", scope
        ).fetchone()
        fills = self.conn.execute(
            """SELECT * FROM research_fills_mx WHERE exchange=? AND market=? AND strategy=?
               ORDER BY id DESC LIMIT 180""", scope
        ).fetchall()
        feedback = self.conn.execute(
            """SELECT * FROM research_feedback_mx WHERE exchange=? AND market=? AND strategy=?
               ORDER BY id DESC LIMIT 80""", scope
        ).fetchall()
        equity = self.conn.execute(
            """SELECT ts,equity_krw,return_pct,cash_krw,position_value_krw FROM research_equity_mx
               WHERE exchange=? AND market=? AND strategy=? ORDER BY id DESC LIMIT 720""", scope
        ).fetchall()
        memory = self.conn.execute(
            """SELECT ts,signal_ts,price,change_24h_pct,turnover_24h,liquidity_score,regime_score,
                      entry_score,opportunity_score,suggested_weight_pct,trade_intent,asset_return_pct,
                      pullback_pct,volatility_pct,orderbook_imbalance,fib_retrace,btc_return_pct,
                      eth_return_pct,asset_vs_majors_pct,price_delta_pct,opportunity_delta,regime_delta,
                      entry_delta,feature_json
               FROM research_market_memory_mx WHERE exchange=? AND market=? AND strategy=?
               ORDER BY id DESC LIMIT 720""", scope
        ).fetchall()
        signal = dict(signal_row) if signal_row else {}
        signal_payload: dict[str, Any] = {}
        if signal:
            signal_payload = _json_load(signal.pop("signal_json", "{}"))
            signal["signal"] = signal_payload
        fill_rows: list[dict[str, Any]] = []
        for source in fills:
            item = dict(source)
            item["signal"] = _json_load(item.pop("signal_json", "{}"))
            fill_rows.append(item)
        feedback_rows: list[dict[str, Any]] = []
        for source in feedback:
            item = dict(source)
            item["profile_before"] = _json_load(item.pop("profile_before_json", "{}"))
            item["profile_after"] = _json_load(item.pop("profile_after_json", "{}"))
            item["signal"] = _json_load(item.pop("signal_json", "{}"))
            feedback_rows.append(item)
        memory_rows: list[dict[str, Any]] = []
        for source in reversed(memory):
            item = dict(source)
            item["features"] = _json_load(item.pop("feature_json", "{}"))
            memory_rows.append(item)
        account = dict(account_row) if account_row else {}
        current_price = _num(signal.get("price"), _num(summary.get("price")))
        volume = _num(account.get("volume"))
        avg_price = _num(account.get("avg_price"))
        position_value = volume * current_price
        unrealized = position_value - volume * avg_price if volume > 0 and avg_price > 0 else 0.0
        unrealized_pct = (current_price / avg_price - 1.0) * 100.0 if avg_price > 0 and volume > 0 else 0.0
        return {
            "exchange": self.exchange, "strategy": self.strategy,
            "key": paper_key(self.exchange, market, self.strategy),
            "summary": summary, "account": account, "profile": dict(profile_row) if profile_row else {},
            "signal": signal, "trade_plan": signal_payload.get("trade_plan") or {},
            "position": {
                "volume": round(volume, 12), "avg_price": round(avg_price, 12),
                "current_price": round(current_price, 12), "value_krw": round(position_value, 2),
                "weight_pct": round(position_value / START_KRW * 100.0, 3),
                "unrealized_pnl_krw": round(unrealized, 2), "unrealized_pnl_pct": round(unrealized_pct, 4),
                "buy_count": self.current_cycle_buy_count(market),
            },
            "fills": fill_rows, "feedback": feedback_rows,
            "equity_history": list(reversed([dict(row) for row in equity])),
            "market_memory": memory_rows,
            "market_memory_count": int(self.conn.execute(
                """SELECT COUNT(*) FROM research_market_memory_mx
                   WHERE exchange=? AND market=? AND strategy=?""", scope
            ).fetchone()[0]),
            "state_class": summary["state_class"], "state_label": summary["state_label"],
        }
