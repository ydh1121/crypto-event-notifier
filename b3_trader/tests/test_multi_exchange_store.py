from __future__ import annotations

from pathlib import Path

from b3_trader.auto_demo_v2 import DemoStore, START_KRW
from b3_trader.multi_exchange_store import BITHUMB_CUTOVER_MIGRATION, MultiExchangeStore, paper_key
from b3_trader.scoped_paper_store import ScopedPaperStore


def test_same_market_is_isolated_by_exchange_and_strategy(tmp_path: Path) -> None:
    db = tmp_path / "paper.sqlite3"
    upbit = ScopedPaperStore("upbit", "adaptive", path=db)
    upbit.ensure_market("KRW-BTC", "BTC", "비트코인")
    upbit_account = upbit.all_accounts()["KRW-BTC"]
    upbit_account["cash_krw"] = 8_500_000.0
    upbit.save_account(upbit_account)
    upbit.close()

    bithumb = ScopedPaperStore("bithumb", "adaptive", path=db)
    bithumb.ensure_market("KRW-BTC", "BTC", "비트코인")
    bithumb_account = bithumb.all_accounts()["KRW-BTC"]
    assert bithumb_account["cash_krw"] == START_KRW
    assert paper_key("bithumb", "KRW-BTC", "adaptive") != paper_key("upbit", "KRW-BTC", "adaptive")
    bithumb.close()

    upbit = ScopedPaperStore("upbit", "adaptive", path=db)
    assert upbit.all_accounts()["KRW-BTC"]["cash_krw"] == 8_500_000.0
    row = upbit.leaderboard()[0]
    assert row["exchange"] == "upbit"
    assert row["strategy"] == "adaptive"
    assert row["key"] == "upbit|KRW-BTC|adaptive"
    upbit.close()


def test_legacy_bithumb_migration_is_explicit_and_refreshes_latest_state(tmp_path: Path) -> None:
    db = tmp_path / "paper.sqlite3"
    legacy = DemoStore(db)
    legacy.ensure_market("KRW-BTC", "BTC", "비트코인")
    account = legacy.all_accounts()["KRW-BTC"]
    account["cash_krw"] = 9_250_000.0
    legacy.save_account(account)
    legacy.close()

    mx = MultiExchangeStore(db)
    assert not [row for row in mx.scope_counts() if row["exchange"] == "bithumb"]
    first = mx.migrate_legacy_bithumb()
    assert first["accounts"] >= 1
    migrated = mx.account("bithumb", "KRW-BTC", "adaptive")
    assert migrated["cash_krw"] == 9_250_000.0
    mx.close()

    legacy = DemoStore(db)
    account = legacy.all_accounts()["KRW-BTC"]
    account["cash_krw"] = 8_750_000.0
    legacy.save_account(account)
    legacy.close()

    mx = MultiExchangeStore(db)
    # Constructing a Phase 3 store does not silently overwrite scoped Bithumb state.
    assert mx.account("bithumb", "KRW-BTC", "adaptive")["cash_krw"] == 9_250_000.0
    mx.migrate_legacy_bithumb()
    assert mx.account("bithumb", "KRW-BTC", "adaptive")["cash_krw"] == 8_750_000.0
    mx.close()


def test_guarded_cutover_records_marker_and_does_not_reimport_on_restart(tmp_path: Path) -> None:
    db = tmp_path / "paper.sqlite3"
    legacy = DemoStore(db)
    legacy.ensure_market("KRW-BTC", "BTC", "비트코인")
    account = legacy.all_accounts()["KRW-BTC"]
    account["cash_krw"] = 9_100_000.0
    legacy.save_account(account)
    legacy.close()

    mx = MultiExchangeStore(db)
    cutover = mx.cutover_legacy_bithumb()
    assert cutover["status"] == "applied"
    assert cutover["verification"]["ok"] is True
    assert mx.migration_record(BITHUMB_CUTOVER_MIGRATION)
    assert mx.account("bithumb", "KRW-BTC", "adaptive")["cash_krw"] == 9_100_000.0
    mx.close()

    # Legacy data is now stale by definition. A later scoped startup must not
    # import it again and overwrite post-cutover state.
    legacy = DemoStore(db)
    account = legacy.all_accounts()["KRW-BTC"]
    account["cash_krw"] = 7_000_000.0
    legacy.save_account(account)
    legacy.close()

    scoped = ScopedPaperStore("bithumb", "adaptive", path=db)
    account = scoped.all_accounts()["KRW-BTC"]
    account["cash_krw"] = 8_800_000.0
    scoped.save_account(account)
    scoped.close()

    mx = MultiExchangeStore(db)
    second = mx.cutover_legacy_bithumb()
    assert second["status"] == "already_applied"
    assert mx.account("bithumb", "KRW-BTC", "adaptive")["cash_krw"] == 8_800_000.0
    assert mx.account("bithumb", "KRW-BTC", "adaptive")["cash_krw"] != 7_000_000.0
    mx.close()
