from __future__ import annotations

import sqlite3
from pathlib import Path

from b3_trader.intelligence_event_response import (
    HORIZONS,
    IntelligenceEventResponseCollector,
    PROVIDER_ID,
)


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE research_intelligence_events(
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT NOT NULL,
            source_ts REAL NOT NULL
        );
        CREATE TABLE research_market_trade_flow_mx(
            exchange TEXT NOT NULL,
            market TEXT NOT NULL,
            sequential_id TEXT NOT NULL,
            trade_ts REAL NOT NULL,
            trade_price REAL NOT NULL,
            PRIMARY KEY(exchange,market,sequential_id)
        );
        """
    )
    conn.commit()
    conn.close()


def _insert_event(
    path: Path,
    *,
    event_id: str = "evt",
    event_type: str = "US_EMPLOYMENT",
    source_id: str = "us_bls_release_calendar",
    event_ts: float = 10_000.0,
) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO research_intelligence_events(event_id,event_type,source_id,title,source_ts) VALUES(?,?,?,?,?)",
        (event_id, event_type, source_id, f"{event_type} fixture", event_ts),
    )
    conn.commit()
    conn.close()


def _trade(path: Path, *, seq: str, ts: float, price: float) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """INSERT INTO research_market_trade_flow_mx(
               exchange,market,sequential_id,trade_ts,trade_price
           ) VALUES('bithumb','KRW-BTC',?,?,?)""",
        (seq, ts, price),
    )
    conn.commit()
    conn.close()


def _collector(path: Path) -> tuple[sqlite3.Connection, IntelligenceEventResponseCollector]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn, IntelligenceEventResponseCollector(
        conn,
        benchmarks=(("bithumb", "KRW-BTC"),),
        observation_tolerance_seconds=120,
        event_lookback_seconds=7 * 24 * 60 * 60,
    )


def test_horizon_contract_is_exact() -> None:
    assert HORIZONS == (
        ("15m", 900),
        ("1h", 3600),
        ("4h", 14400),
        ("1d", 86400),
    )


def test_collects_due_horizons_and_keeps_future_horizons_pending(tmp_path: Path) -> None:
    path = tmp_path / "response.sqlite3"
    _init_db(path)
    event_ts = 100_000.0
    _insert_event(path, event_ts=event_ts)
    _trade(path, seq="baseline", ts=event_ts - 5, price=100.0)
    _trade(path, seq="15m", ts=event_ts + 900 + 3, price=101.0)
    _trade(path, seq="1h", ts=event_ts + 3600 + 4, price=103.0)

    conn, collector = _collector(path)
    try:
        result = collector.run_once(now=event_ts + 3700)
        assert result["status"] == "ok"
        assert result["samples_inserted"] == 2
        assert result["future_observations"] == 2
        rows = conn.execute(
            """SELECT horizon_label,baseline_trade_ts,target_trade_ts,return_pct
               FROM research_intelligence_event_responses ORDER BY horizon_seconds"""
        ).fetchall()
        assert [row["horizon_label"] for row in rows] == ["15m", "1h"]
        assert all(float(row["baseline_trade_ts"]) <= event_ts for row in rows)
        assert float(rows[0]["target_trade_ts"]) >= event_ts + 900
        assert float(rows[1]["target_trade_ts"]) >= event_ts + 3600
        assert abs(float(rows[0]["return_pct"]) - 1.0) < 1e-9
        assert abs(float(rows[1]["return_pct"]) - 3.0) < 1e-9
    finally:
        conn.close()


def test_missing_observation_is_not_fabricated_as_zero(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    _init_db(path)
    event_ts = 200_000.0
    _insert_event(path, event_ts=event_ts)
    _trade(path, seq="baseline", ts=event_ts - 1, price=100.0)

    conn, collector = _collector(path)
    try:
        result = collector.run_once(now=event_ts + 1000)
        assert result["due_observations"] == 1
        assert result["missing_target"] == 1
        count = conn.execute(
            "SELECT COUNT(*) FROM research_intelligence_event_responses"
        ).fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_collector_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "idempotent.sqlite3"
    _init_db(path)
    event_ts = 300_000.0
    _insert_event(path, event_ts=event_ts)
    _trade(path, seq="baseline", ts=event_ts - 1, price=100.0)
    _trade(path, seq="target", ts=event_ts + 901, price=102.0)

    conn, collector = _collector(path)
    try:
        first = collector.run_once(now=event_ts + 1000)
        second = collector.run_once(now=event_ts + 1000)
        assert first["samples_inserted"] == 1
        assert second["samples_inserted"] == 0
        assert second["already_captured"] == 1
        count = conn.execute(
            "SELECT COUNT(*) FROM research_intelligence_event_responses WHERE provider_id=?",
            (PROVIDER_ID,),
        ).fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_baseline_must_exist_at_or_before_event(tmp_path: Path) -> None:
    path = tmp_path / "baseline.sqlite3"
    _init_db(path)
    event_ts = 400_000.0
    _insert_event(path, event_ts=event_ts)
    _trade(path, seq="after-event", ts=event_ts + 1, price=100.0)
    _trade(path, seq="target", ts=event_ts + 901, price=101.0)

    conn, collector = _collector(path)
    try:
        result = collector.run_once(now=event_ts + 1000)
        assert result["missing_baseline"] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM research_intelligence_event_responses"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_date_only_fomc_meeting_is_excluded(tmp_path: Path) -> None:
    path = tmp_path / "fomc.sqlite3"
    _init_db(path)
    event_ts = 500_000.0
    _insert_event(
        path,
        event_id="fomc-date-only",
        event_type="FOMC_MEETING",
        source_id="us_fed_fomc_calendar",
        event_ts=event_ts,
    )
    _trade(path, seq="baseline", ts=event_ts - 1, price=100.0)
    _trade(path, seq="target", ts=event_ts + 901, price=105.0)

    conn, collector = _collector(path)
    try:
        result = collector.run_once(now=event_ts + 1000)
        assert result["events_excluded_imprecise"] == 1
        assert result["due_observations"] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM research_intelligence_event_responses"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_event_response_module_has_no_trading_authority_dependency() -> None:
    path = Path(__file__).resolve().parents[1] / "intelligence_event_response.py"
    text = path.read_text(encoding="utf-8").casefold()
    assert "score_engine" not in text
    assert "paper_engine" not in text
    assert "order_executor" not in text
    assert "trading_decision" not in text
