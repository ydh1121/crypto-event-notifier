from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.intelligence_event import normalize_intelligence_event
from b3_trader.intelligence_event_store import IntelligenceEventStore
from b3_trader.intelligence_reaction_builder import IntelligenceReactionBuilder


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE research_market_ohlcv_mx(
            exchange TEXT NOT NULL,
            market TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            candle_ts REAL NOT NULL,
            close REAL NOT NULL,
            is_closed INTEGER NOT NULL,
            source TEXT NOT NULL,
            received_at REAL NOT NULL,
            PRIMARY KEY(exchange,market,timeframe,candle_ts)
        )"""
    )
    return conn


def _event(store: IntelligenceEventStore, *, external_id: str = "fixture", anchor: float = 1000.0) -> str:
    event = normalize_intelligence_event(
        source_id="us_sec_press_releases",
        source_family="official_news",
        event_type="US_SEC_POLICY",
        title=f"SEC fixture {external_id}",
        source_url=f"https://www.sec.gov/newsroom/press-releases/{external_id}",
        external_id=external_id,
        published_at=anchor,
        received_at=anchor + 5,
    )
    store.ingest([event], seen_at=anchor + 10)
    return event.event_id


def _insert_path(
    conn: sqlite3.Connection,
    *,
    start_candle: int,
    end_candle: int,
    interval: int,
    timeframe: str,
    source: str = "public_rest",
    omit: set[int] | None = None,
) -> None:
    omitted = set(omit or set())
    rows = []
    index = 0
    for candle_ts in range(start_candle, end_candle + 1, interval):
        if candle_ts in omitted:
            index += 1
            continue
        rows.append(
            (
                "upbit",
                "KRW-BTC",
                timeframe,
                float(candle_ts),
                100.0 + index,
                1,
                source,
                float(candle_ts + interval + 2),
            )
        )
        index += 1
    conn.executemany(
        """INSERT INTO research_market_ohlcv_mx(
            exchange,market,timeframe,candle_ts,close,is_closed,source,received_at
        ) VALUES(?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()


def test_builder_aligns_closed_1m_path_forward_only_and_refreshes_memory() -> None:
    conn = _conn()
    event_store = IntelligenceEventStore(conn)
    event_id = _event(event_store, anchor=1000)
    # 960 candle closes at 1020: first completed close after the 1000 event.
    # 1860 candle closes at 1920: first completed close after the 1900 horizon.
    _insert_path(conn, start_candle=960, end_candle=1860, interval=60, timeframe="1m")

    result = IntelligenceReactionBuilder(conn).run(
        now=2000,
        pairs=[("upbit", "KRW-BTC")],
        windows=["15m"],
    )
    assert result["events_considered"] == 1
    assert result["pairs_considered"] == 1
    assert result["due_candidates"] == 1
    assert result["reactions_ready"] == 1
    assert result["missing_price_alignment"] == 0
    assert result["missing_contiguous_path"] == 0
    assert result["ingest"] == {"received": 1, "inserted": 1, "updated": 0}
    assert result["memory"]["groups"] == 1

    row = conn.execute(
        "SELECT * FROM research_intelligence_reactions WHERE event_id=?",
        (event_id,),
    ).fetchone()
    assert row is not None
    assert row["start_at"] == 1020
    assert row["end_at"] == 1920
    assert row["start_delay_seconds"] == 20
    assert row["end_delay_seconds"] == 20
    assert row["provider_id"] == "upbit:public_rest:1m"
    assert row["exchange"] == "upbit"
    assert row["forward_return_pct"] == 15.0


def test_builder_rejects_missing_candle_inside_reaction_path() -> None:
    conn = _conn()
    _event(IntelligenceEventStore(conn), anchor=1000)
    _insert_path(
        conn,
        start_candle=960,
        end_candle=1860,
        interval=60,
        timeframe="1m",
        omit={1500},
    )
    result = IntelligenceReactionBuilder(conn).run(
        now=2000,
        pairs=[("upbit", "KRW-BTC")],
        windows=["15m"],
    )
    assert result["reactions_ready"] == 0
    assert result["missing_contiguous_path"] == 1
    assert conn.execute("SELECT COUNT(*) FROM research_intelligence_reactions").fetchone()[0] == 0


def test_builder_pins_endpoint_to_start_source() -> None:
    conn = _conn()
    _event(IntelligenceEventStore(conn), anchor=1000)
    _insert_path(conn, start_candle=960, end_candle=1800, interval=60, timeframe="1m", source="source_a")
    conn.execute(
        """INSERT INTO research_market_ohlcv_mx(
            exchange,market,timeframe,candle_ts,close,is_closed,source,received_at
        ) VALUES(?,?,?,?,?,?,?,?)""",
        ("upbit", "KRW-BTC", "1m", 1860.0, 110.0, 1, "source_b", 1922.0),
    )
    conn.commit()
    result = IntelligenceReactionBuilder(conn).run(
        now=2000,
        pairs=[("upbit", "KRW-BTC")],
        windows=["15m"],
    )
    assert result["reactions_ready"] == 0
    assert result["missing_price_alignment"] == 1


def test_builder_does_not_create_reaction_before_horizon_is_due() -> None:
    conn = _conn()
    _event(IntelligenceEventStore(conn), anchor=1000)
    _insert_path(conn, start_candle=960, end_candle=1860, interval=60, timeframe="1m")
    result = IntelligenceReactionBuilder(conn).run(
        now=1899,
        pairs=[("upbit", "KRW-BTC")],
        windows=["15m"],
    )
    assert result["due_candidates"] == 0
    assert result["reactions_ready"] == 0


def test_builder_uses_5m_closed_path_for_1d_horizon() -> None:
    conn = _conn()
    _event(IntelligenceEventStore(conn), anchor=900)
    # Both targets land exactly on completed 5m close clocks.
    _insert_path(conn, start_candle=600, end_candle=87000, interval=300, timeframe="5m")
    result = IntelligenceReactionBuilder(conn).run(
        now=87400,
        pairs=[("upbit", "KRW-BTC")],
        windows=["1d"],
    )
    assert result["reactions_ready"] == 1
    row = conn.execute("SELECT * FROM research_intelligence_reactions WHERE window='1d'").fetchone()
    assert row is not None
    assert row["start_at"] == 900
    assert row["end_at"] == 87300
    assert row["provider_id"] == "upbit:public_rest:5m"


def test_builder_has_no_score_paper_decision_or_order_dependency() -> None:
    path = Path(__file__).resolve().parents[1] / "intelligence_reaction_builder.py"
    text = path.read_text(encoding="utf-8").casefold()
    assert "score_engine" not in text
    assert "paper_engine" not in text
    assert "order_executor" not in text
    assert "trading_decision" not in text
