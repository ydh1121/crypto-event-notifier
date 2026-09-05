from b3_trader.journal import TradeJournal
from b3_trader.paper import Fill


def test_journal_records_snapshot_fill_event_and_portfolio(tmp_path):
    journal = TradeJournal(str(tmp_path / "journal.sqlite3"))
    journal.record_snapshot(
        market="KRW-B3",
        price=0.7,
        regime_score=70,
        entry_score=72,
        action="BUY_CANDIDATE",
        payload={"ok": True, "context_score": 66},
    )
    journal.record_fill(
        mode="paper",
        market="KRW-B3",
        fill=Fill("buy", 0.7, 100.0, 70.0, "test"),
    )
    journal.record_event("test_event", {"x": 1})
    journal.record_portfolio_snapshot(
        {
            "cash_krw": 930.0,
            "equity_krw": 1000.0,
            "exposure_krw": 70.0,
            "daily_drawdown_pct": 0.0,
        }
    )

    assert journal.counts() == {
        "snapshots": 1,
        "fills": 1,
        "events": 1,
        "portfolio_snapshots": 1,
    }
    assert journal.snapshot_history("KRW-B3")[-1]["context_score"] == 66
    assert journal.portfolio_history()[-1]["equity_krw"] == 1000.0
    journal.close()


def test_paper_trade_stats_matches_round_trip(tmp_path):
    journal = TradeJournal(str(tmp_path / "journal.sqlite3"))
    journal.record_fill(
        mode="paper",
        market="KRW-B3",
        fill=Fill("buy", 1.0, 100.0, 100.0, "entry"),
    )
    journal.record_fill(
        mode="paper",
        market="KRW-B3",
        fill=Fill("sell", 1.2, 100.0, 120.0, "exit"),
    )
    stats = journal.paper_trade_stats()
    assert stats["realized_pnl_krw"] == 20.0
    assert stats["closed_trades"] == 1
    assert stats["wins"] == 1
    assert stats["win_rate_pct"] == 100.0
    journal.close()
