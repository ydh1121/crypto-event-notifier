from b3_trader.journal import TradeJournal
from b3_trader.paper import Fill


def test_journal_records_snapshot_fill_and_event(tmp_path):
    journal = TradeJournal(str(tmp_path / "journal.sqlite3"))
    journal.record_snapshot(
        market="KRW-B3",
        price=0.7,
        regime_score=70,
        entry_score=72,
        action="BUY_CANDIDATE",
        payload={"ok": True},
    )
    journal.record_fill(
        mode="paper",
        market="KRW-B3",
        fill=Fill("buy", 0.7, 100.0, 70.0, "test"),
    )
    journal.record_event("test_event", {"x": 1})

    assert journal.counts() == {"snapshots": 1, "fills": 1, "events": 1}
    journal.close()
