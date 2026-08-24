from __future__ import annotations

import json
import time
from typing import Any

from .auto_demo_v2 import AutoPaperDemo as AutoPaperDemoV2
from .auto_demo_v2 import DB_PATH, DemoStore as DemoStoreV2, _num

MARKET_MEMORY_RETENTION_DAYS = 45
MARKET_MEMORY_DETAIL_LIMIT = 720


class DemoStore(DemoStoreV2):
    """Adds AI-ready per-scan market memory without changing PAPER execution semantics."""

    def __init__(self, path=DB_PATH) -> None:
        self._memory_writes = 0
        super().__init__(path)

    def _init_schema(self) -> None:
        super()._init_schema()
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_market_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                signal_ts REAL NOT NULL,
                market TEXT NOT NULL,
                price REAL NOT NULL,
                change_24h_pct REAL NOT NULL,
                turnover_24h REAL NOT NULL,
                liquidity_score REAL NOT NULL,
                regime_score REAL NOT NULL,
                entry_score REAL NOT NULL,
                opportunity_score REAL NOT NULL,
                suggested_weight_pct REAL NOT NULL,
                trade_intent TEXT NOT NULL,
                asset_return_pct REAL NOT NULL,
                pullback_pct REAL NOT NULL,
                volatility_pct REAL NOT NULL,
                orderbook_imbalance REAL NOT NULL,
                fib_retrace REAL,
                btc_return_pct REAL NOT NULL,
                eth_return_pct REAL NOT NULL,
                asset_vs_majors_pct REAL NOT NULL,
                price_delta_pct REAL NOT NULL DEFAULT 0,
                opportunity_delta REAL NOT NULL DEFAULT 0,
                regime_delta REAL NOT NULL DEFAULT 0,
                entry_delta REAL NOT NULL DEFAULT 0,
                feature_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_market_memory_market_signal_ts
                ON research_market_memory(market, signal_ts);
            CREATE INDEX IF NOT EXISTS idx_market_memory_market_ts
                ON research_market_memory(market, ts DESC);
            CREATE INDEX IF NOT EXISTS idx_market_memory_ts
                ON research_market_memory(ts DESC);
            """
        )
        self.conn.commit()

    @staticmethod
    def _state_class(row: dict[str, Any]) -> tuple[str, str]:
        if bool(row.get("has_position")):
            return "holding", "보유 중"
        if int(row.get("closed_trades") or 0) > 0:
            return "completed_waiting", "매매 완료 · 대기"
        return "untraded", "미진입"

    def leaderboard(self, limit: int = 5000) -> list[dict[str, Any]]:
        rows = super().leaderboard(limit)
        for row in rows:
            state_class, state_label = self._state_class(row)
            row["state_class"] = state_class
            row["state_label"] = state_label
            row["position_cost_krw"] = round(
                _num(row.get("position_avg_price"))
                * (_num(row.get("position_value_krw")) / _num(row.get("price"), 1.0)),
                2,
            ) if _num(row.get("price")) > 0 else 0.0
        return rows

    def _append_market_memory(self, row: dict[str, Any]) -> None:
        market = str(row.get("market") or "")
        signal_ts = _num(row.get("ts"))
        if not market or signal_ts <= 0:
            return
        signal = row.get("signal") if isinstance(row.get("signal"), dict) else {}
        latest = self.conn.execute(
            """SELECT price,opportunity_score,regime_score,entry_score
               FROM research_market_memory WHERE market=? ORDER BY id DESC LIMIT 1""",
            (market,),
        ).fetchone()
        previous_price = _num(latest["price"]) if latest else 0.0
        price = _num(row.get("price"))
        price_delta_pct = (price / previous_price - 1.0) * 100.0 if previous_price > 0 and price > 0 else 0.0
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
            """INSERT OR IGNORE INTO research_market_memory(
                ts,signal_ts,market,price,change_24h_pct,turnover_24h,liquidity_score,
                regime_score,entry_score,opportunity_score,suggested_weight_pct,trade_intent,
                asset_return_pct,pullback_pct,volatility_pct,orderbook_imbalance,fib_retrace,
                btc_return_pct,eth_return_pct,asset_vs_majors_pct,price_delta_pct,
                opportunity_delta,regime_delta,entry_delta,feature_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                time.time(), signal_ts, market, price, _num(row.get("change_24h_pct")),
                _num(row.get("turnover_24h")), _num(row.get("liquidity_score")), regime, entry,
                opportunity, _num(row.get("suggested_weight_pct")), str(row.get("trade_intent") or "wait"),
                _num(signal.get("asset_return_pct")), _num(signal.get("pullback_pct")),
                _num(signal.get("volatility_pct")), _num(signal.get("orderbook_imbalance")),
                signal.get("fib_retrace"), _num(signal.get("btc_return_pct")),
                _num(signal.get("eth_return_pct")), _num(signal.get("asset_vs_majors_pct")),
                price_delta_pct,
                opportunity - (_num(latest["opportunity_score"]) if latest else opportunity),
                regime - (_num(latest["regime_score"]) if latest else regime),
                entry - (_num(latest["entry_score"]) if latest else entry),
                json.dumps(feature_payload, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        self._memory_writes += 1
        if self._memory_writes % 1200 == 0:
            cutoff = time.time() - MARKET_MEMORY_RETENTION_DAYS * 86400.0
            self.conn.execute("DELETE FROM research_market_memory WHERE ts < ?", (cutoff,))
        self.conn.commit()

    def save_signal(self, row: dict[str, Any]) -> None:
        super().save_signal(row)
        self._append_market_memory(row)

    def market_detail(self, market: str) -> dict[str, Any]:
        detail = super().market_detail(market)
        if not detail:
            return detail
        memory_rows = self.conn.execute(
            """SELECT ts,signal_ts,price,change_24h_pct,turnover_24h,liquidity_score,
                      regime_score,entry_score,opportunity_score,suggested_weight_pct,trade_intent,
                      asset_return_pct,pullback_pct,volatility_pct,orderbook_imbalance,fib_retrace,
                      btc_return_pct,eth_return_pct,asset_vs_majors_pct,price_delta_pct,
                      opportunity_delta,regime_delta,entry_delta,feature_json
               FROM research_market_memory WHERE market=? ORDER BY id DESC LIMIT ?""",
            (market, MARKET_MEMORY_DETAIL_LIMIT),
        ).fetchall()
        memory: list[dict[str, Any]] = []
        for source in reversed(memory_rows):
            row = dict(source)
            try:
                row["features"] = json.loads(row.pop("feature_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                row["features"] = {}
            memory.append(row)
        detail["market_memory"] = memory
        detail["market_memory_count"] = int(
            self.conn.execute(
                "SELECT COUNT(*) AS count FROM research_market_memory WHERE market=?", (market,)
            ).fetchone()["count"]
        )
        state_class, state_label = self._state_class(detail.get("summary") or {})
        detail["state_class"] = state_class
        detail["state_label"] = state_label
        return detail


class AutoPaperDemo(AutoPaperDemoV2):
    """v3 research engine: v2 execution + persistent per-coin market memory."""

    def __init__(self) -> None:
        super().__init__()
        self.store.close()
        self.store = DemoStore()


def main() -> None:
    AutoPaperDemo().run()


if __name__ == "__main__":
    main()
