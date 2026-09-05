from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from b3_trader.paper_strategy_v2_forward_shadow import PaperV2ForwardShadowRunner, balanced_policy


class FakeAdapter:
    exchange = "bithumb"

    def __init__(self) -> None:
        self.prices = {"KRW-AAA": 100.0, "KRW-BBB": 200.0, "KRW-BTC": 100_000_000.0}

    def candles_minutes(self, market: str, unit: int = 5, count: int = 120):
        return [{"trade_price": 100.0} for _ in range(max(4, count))]

    def orderbook(self, market: str):
        p = float(self.prices.get(market, 100.0))
        return {"orderbook_units": [{"bid_price": p * 0.9995, "ask_price": p * 1.0005, "bid_size": 10_000_000.0, "ask_size": 10_000_000.0}]}


def _seed_signal_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE research_signals_mx(
            exchange TEXT, market TEXT, strategy TEXT, symbol TEXT, price REAL,
            regime_score REAL, entry_score REAL, opportunity_score REAL,
            trade_intent TEXT, signal_json TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO research_signals_mx VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("bithumb", "KRW-AAA", "adaptive", "AAA", 100.0, 62.0, 70.0, 68.0, "wait", json.dumps({"volatility_pct": 2.0})),
    )
    conn.commit()
    conn.close()


def test_balanced_policy_matches_selected_sweep_preset() -> None:
    policy, risk = balanced_policy()
    assert policy.max_gross_exposure_pct == 60.0
    assert policy.reserve_cash_pct == 25.0
    assert policy.max_position_pct == 25.0
    assert policy.risk_budget_pct == 2.0
    assert risk.max_portfolio_risk_pct == 5.0


def test_forward_shadow_opens_shared_portfolio_position_and_stays_paper_only(tmp_path: Path) -> None:
    db = tmp_path / "paper.sqlite3"
    _seed_signal_db(db)
    runner = PaperV2ForwardShadowRunner(db, adapter=FakeAdapter())
    try:
        result = runner.run_once()
        assert result["paper_only"] is True
        assert result["shadow_only"] is True
        assert result["can_place_real_orders"] is False
        assert result["private_exchange_credentials_used"] is False
        assert result["preset"] == "balanced_60_25_r2_agg5"
        assert result["orders"]["initial"] == 1
        assert result["open_positions"] == 1
        assert 0 < result["reserved_risk_pct"] <= 5.0
        fills = runner.conn.execute("SELECT side,krw FROM research_paper_v2_fills ORDER BY id").fetchall()
        assert len(fills) == 1
        assert fills[0]["side"] == "buy"
        assert float(fills[0]["krw"]) >= 100_000.0
    finally:
        runner.close()


def test_forward_shadow_add_does_not_recheck_opportunity_threshold(tmp_path: Path) -> None:
    db = tmp_path / "paper.sqlite3"
    _seed_signal_db(db)
    adapter = FakeAdapter()
    runner = PaperV2ForwardShadowRunner(db, adapter=adapter)
    try:
        first = runner.run_once()
        assert first["orders"]["initial"] == 1
        plan_row = runner.conn.execute("SELECT plan_json FROM research_paper_v2_positions WHERE market='KRW-AAA'").fetchone()
        plan = json.loads(plan_row["plan_json"])
        trigger = float(plan["ladder"][1]["trigger_price"])
        adapter.prices["KRW-AAA"] = trigger * 0.999
        runner.conn.execute(
            "UPDATE research_signals_mx SET price=?,regime_score=?,entry_score=?,opportunity_score=? WHERE market='KRW-AAA'",
            (trigger * 0.999, 50.0, 40.0, 45.0),
        )
        runner.conn.commit()
        second = runner.run_once()
        assert second["orders"]["adds"] == 1
        position = runner.conn.execute("SELECT completed_entries,add_count FROM research_paper_v2_positions WHERE market='KRW-AAA'").fetchone()
        assert int(position["completed_entries"]) == 2
        assert int(position["add_count"]) == 1
    finally:
        runner.close()
