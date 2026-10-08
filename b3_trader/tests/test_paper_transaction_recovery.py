import json
import sqlite3
import time

import pytest

from b3_trader import auto_demo_v2 as legacy
from b3_trader import multi_exchange_paper as paper
from b3_trader.asset_strategy import AssetSignal
from b3_trader.exchange_public import PublicMarket
from b3_trader.scoped_paper_store import ScopedPaperStore


def make_demo(tmp_path, monkeypatch, exchange="upbit"):
    db = tmp_path / "paper.sqlite3"
    monkeypatch.setattr(paper, "ScopedPaperStore",
                        lambda e, s: ScopedPaperStore(e, s, db))

    class Quotes:
        def krw_markets(self):
            return [PublicMarket(exchange, "KRW-B3", "B3", "B3")]

        def krw_tickers(self):
            return [{"market": "KRW-B3", "trade_price": 100,
                     "acc_trade_price_24h": 1e10, "signed_change_rate": .02}]

        def candles_minutes(self, *args, **kwargs):
            assert not demo.store.conn.in_transaction  # no network under writer lock
            return []

    monkeypatch.setattr(paper, "public_exchange", lambda e: Quotes())
    demo = paper.MultiExchangePaperDemo(exchange)
    demo.status_path = tmp_path / "status.json"
    demo.detail_dir = tmp_path / "details"
    demo._last_retention_maintenance = time.time()
    demo.store.conn.execute("PRAGMA busy_timeout=10")
    signal = AssetSignal(80, 80, 1, 1, 2, 0, 1, .1, 5, 1, .5, "BUY_CANDIDATE", "fixture")
    book = {"orderbook_units": [{"bid_price": 99.9, "ask_price": 100,
                                  "bid_size": 1e8, "ask_size": 1e8}]}

    def score(*args):
        assert not demo.store.conn.in_transaction
        return signal, book

    monkeypatch.setattr(demo, "_score_market", score)
    monkeypatch.setattr(demo, "_risk_buy", lambda *a: (True, 100, ""))
    monkeypatch.setattr(legacy.time, "sleep", lambda _: None)
    demo._all_tickers()
    return demo, db


@pytest.mark.parametrize("exchange", ["bithumb", "upbit"])
def test_failed_catalog_write_does_not_poison_next_scan(tmp_path, monkeypatch, exchange):
    demo, db = make_demo(tmp_path, monkeypatch, exchange)
    writer = sqlite3.connect(db)
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE research_accounts_mx SET peak_price=2")
        with pytest.raises(sqlite3.OperationalError):
            demo.scan_once()
        status = json.loads(demo.status_path.read_text())
        assert status["scan_failure"]["sqlite_errorname"] == "SQLITE_BUSY"
        assert status["scan_failure"]["transaction_open"] is False
        assert not demo.store.conn.in_transaction
        writer.commit()
        demo.scan_once()
        account = demo.store.all_accounts()["KRW-B3"]
        fills = demo.store.fills("KRW-B3")
        assert len(fills) == 1 and fills[0]["side"] == "buy"
        assert account["cash_krw"] == pytest.approx(legacy.START_KRW - fills[0]["krw"])
        assert account["volume"] == pytest.approx(fills[0]["volume"])
        assert demo.store.conn.execute("SELECT count(*) FROM research_market_memory_mx").fetchone()[0] == 1
        assert json.loads(demo.status_path.read_text())["scan_failure"] == {}
        assert not demo.store.conn.in_transaction
    finally:
        writer.close()
        demo.store.close()


@pytest.mark.parametrize("method", ["add_fill", "snapshot_equity", "save_signal"])
def test_failed_buy_keeps_account_and_journal_together(tmp_path, monkeypatch, method):
    demo, db = make_demo(tmp_path, monkeypatch)
    before = demo.store.all_accounts()["KRW-B3"]
    original = getattr(demo.store, method)

    def failure(*args, **kwargs):
        original(*args, **kwargs)
        raise sqlite3.OperationalError("injected storage failure")

    monkeypatch.setattr(demo.store, method, failure)
    try:
        with pytest.raises(sqlite3.OperationalError):
            demo.scan_once()
        account = demo.store.all_accounts()["KRW-B3"]
        for key in ("cash_krw", "volume", "avg_price", "realized_pnl"):
            assert account[key] == before[key]
        for table in ("research_fills_mx", "research_feedback_mx", "research_equity_mx",
                      "research_signals_mx", "research_market_memory_mx"):
            assert demo.store.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        assert not demo.store.conn.in_transaction
        monkeypatch.setattr(demo.store, method, original)
        demo.scan_once()
        assert len(demo.store.fills()) == 1
    finally:
        demo.store.close()


@pytest.mark.parametrize("method", ["add_fill", "save_profile", "add_feedback"])
def test_failed_sell_preserves_position_learning_and_existing_buy(tmp_path, monkeypatch, method):
    demo, db = make_demo(tmp_path, monkeypatch)
    demo.scan_once()
    before_account = demo.store.all_accounts()["KRW-B3"]
    before_profile = demo.store.all_profiles()["KRW-B3"]
    original = getattr(demo.store, method)

    def failure(*args, **kwargs):
        original(*args, **kwargs)
        raise sqlite3.OperationalError("injected storage failure")

    monkeypatch.setattr(demo, "_trade_intent", lambda *a: ("sell", "fixture close"))
    monkeypatch.setattr(demo.store, method, failure)
    try:
        with pytest.raises(sqlite3.OperationalError):
            demo.scan_once()
        assert demo.store.all_accounts()["KRW-B3"] == before_account
        assert demo.store.all_profiles()["KRW-B3"] == before_profile
        assert [f["side"] for f in demo.store.fills()] == ["buy"]
        assert demo.store.conn.execute("SELECT count(*) FROM research_feedback_mx").fetchone()[0] == 0
        monkeypatch.setattr(demo.store, method, original)
        demo.scan_once()
        fills = demo.store.fills()
        account = demo.store.all_accounts()["KRW-B3"]
        assert [f["side"] for f in fills] == ["buy", "sell"]
        assert account["volume"] == 0
        assert account["realized_pnl"] == pytest.approx(fills[-1]["realized_pnl"])
        assert demo.store.all_profiles()["KRW-B3"]["closed_trades"] == 1
    finally:
        demo.store.close()


def test_sqlite_error_during_scoring_is_not_a_zero_score(tmp_path, monkeypatch):
    demo, db = make_demo(tmp_path, monkeypatch)

    def fail(*args):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(demo, "_score_market", fail)
    try:
        with pytest.raises(sqlite3.OperationalError):
            demo.scan_once()
        assert demo.store.conn.execute("SELECT count(*) FROM research_market_memory_mx").fetchone()[0] == 0
        assert not demo.store.conn.in_transaction
    finally:
        demo.store.close()


def test_nested_transaction_is_rejected_and_outer_changes_roll_back(tmp_path):
    store = ScopedPaperStore("upbit", path=tmp_path / "paper.sqlite3")
    store.ensure_market("KRW-B3", "B3", "B3")
    try:
        with pytest.raises(RuntimeError):
            with store.market_transaction():
                account = store.all_accounts()["KRW-B3"]
                account["cash_krw"] = 123
                store.save_account(account)
                with store.market_transaction():
                    pass
        assert store.all_accounts()["KRW-B3"]["cash_krw"] == legacy.START_KRW
        assert not store.conn.in_transaction
    finally:
        store.close()
