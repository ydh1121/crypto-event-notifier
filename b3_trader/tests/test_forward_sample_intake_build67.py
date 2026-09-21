from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.dex_shadow_score_v2_preregistration import FORWARD_CUTOFF_TS
from b3_trader.forward_sample_intake import ForwardSampleIntake
from b3_trader.market_notice import MarketNotice


class FakeSource:
    source = "official_fake"

    def __init__(self, exchange: str, pages: dict[int, list[MarketNotice]]) -> None:
        self.exchange = exchange
        self.pages = pages
        self.calls: list[int] = []

    def fetch_page(self, page: int) -> list[MarketNotice]:
        self.calls.append(page)
        return list(self.pages.get(page, []))


def _notice(
    exchange: str,
    notice_id: str,
    symbol: str,
    *,
    announcement_at: float,
    trade_open_at: float,
) -> MarketNotice:
    return MarketNotice(
        exchange=exchange,
        notice_id=notice_id,
        title=f"{symbol} ({symbol}) 원화 마켓 추가",
        url=f"https://example.test/{exchange}/{notice_id}",
        published_at=announcement_at,
        event_kind="LISTING",
        symbols=(symbol,),
        source="official_fake",
        announcement_at=announcement_at,
        trade_open_at=trade_open_at,
    )


def test_build67_intakes_only_post_cutoff_official_cases(tmp_path: Path) -> None:
    db = tmp_path / "research.sqlite3"
    state = tmp_path / "build67-state.json"
    before = _notice(
        "bithumb", "before", "OLD",
        announcement_at=FORWARD_CUTOFF_TS - 7200,
        trade_open_at=FORWARD_CUTOFF_TS - 3600,
    )
    confirmed = _notice(
        "bithumb", "confirmed", "NEW",
        announcement_at=FORWARD_CUTOFF_TS + 60,
        trade_open_at=FORWARD_CUTOFF_TS + 3600,
    )
    pending = _notice(
        "upbit", "pending", "WAIT",
        announcement_at=FORWARD_CUTOFF_TS + 120,
        trade_open_at=0.0,
    )
    bithumb = FakeSource("bithumb", {1: [before, confirmed], 2: []})
    upbit = FakeSource("upbit", {1: [pending], 2: []})

    intake = ForwardSampleIntake(
        db,
        sources=(bithumb, upbit),
        state_path=state,
        pages_per_exchange=2,
    )
    result = intake.run_once()
    assert result["ok"] is True
    assert result["unique_forward_notices"] == 2
    assert result["seed"]["seeded_new_cases"] == 2
    assert result["forward_counts_after"]["confirmed_forward_open_cases"] == 1
    assert result["forward_counts_after"]["pending_open_time_forward_candidates"] == 1
    assert bithumb.calls == [1, 2]
    assert upbit.calls == [1, 2]

    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT domestic_notice_id,domestic_open_at,status FROM listing_history_cases ORDER BY domestic_notice_id"
        ).fetchall()
    finally:
        conn.close()
    assert rows == [
        ("confirmed", FORWARD_CUTOFF_TS + 3600, "pending_identity"),
        ("pending", 0.0, "pending_identity"),
    ]


def test_build67_is_idempotent_and_does_not_use_historical_cursor(tmp_path: Path) -> None:
    db = tmp_path / "research.sqlite3"
    state = tmp_path / "build67-state.json"
    notice = _notice(
        "bithumb", "same", "SAME",
        announcement_at=FORWARD_CUTOFF_TS + 60,
        trade_open_at=FORWARD_CUTOFF_TS + 600,
    )
    source = FakeSource("bithumb", {1: [notice]})
    intake = ForwardSampleIntake(db, sources=(source,), state_path=state, pages_per_exchange=1)

    first = intake.run_once()
    second = intake.run_once()
    assert first["seed"]["seeded_new_cases"] == 1
    assert second["seed"]["seeded_new_cases"] == 0
    assert second["seed"]["existing_cases_seen"] == 1
    assert second["isolation"]["build47_historical_cursor_read"] is False
    assert second["isolation"]["build47_historical_cursor_mutation"] is False


def test_build67_plan_is_read_only_and_bounded(tmp_path: Path) -> None:
    db = tmp_path / "missing.sqlite3"
    intake = ForwardSampleIntake(db, sources=(), state_path=tmp_path / "state.json", pages_per_exchange=99)
    plan = intake.plan()
    assert plan["status"] == "planned"
    assert plan["network_fetches"] is False
    assert plan["hard_max_pages_per_exchange"] == 3
    assert plan["pages_per_exchange"] == 3
    assert plan["run_scope"]["resolve_identity"] is False
    assert plan["run_scope"]["fetch_dex"] is False
    assert plan["run_scope"]["calculate_v2_score"] is False
    assert db.exists() is False
