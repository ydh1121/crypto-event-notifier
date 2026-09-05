from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from b3_trader.intelligence_us_index_intraday import (
    DEFAULT_INDEX_SYMBOLS,
    TWELVE_DATA_DATA_RIGHTS,
    TWELVE_DATA_PROVIDER_ID,
    IndexBar,
)
from b3_trader.intelligence_us_market_reference_capture import UsMarketReferenceCaptureService


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> float:
    return datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc).timestamp()


def _bar(market_id: str, stamp: str, close: float) -> IndexBar:
    symbol = DEFAULT_INDEX_SYMBOLS[market_id]
    return IndexBar(
        market_id=market_id,
        requested_symbol=symbol,
        provider_symbol=symbol,
        interval="1min",
        datetime=stamp,
        open=close - 1.0,
        high=close + 2.0,
        low=close - 2.0,
        close=close,
        volume=None,
        exchange="US",
        exchange_timezone="America/New_York",
        instrument_type="Index",
    )


class _MissingClient:
    credential_status = "missing"

    def fetch_time_series(self, *args, **kwargs):
        raise AssertionError("network must not be called without credential")


class _ReadyClient:
    credential_status = "ready"

    def __init__(self, *, fail_market: str = "") -> None:
        self.fail_market = fail_market
        self.calls: list[tuple[str, str, int]] = []

    def fetch_time_series(self, market_id: str, *, interval: str, outputsize: int):
        self.calls.append((market_id, interval, outputsize))
        if market_id == self.fail_market:
            raise RuntimeError("fixture provider failure")
        base = {
            "SP500": 6500.0,
            "NASDAQ_COMPOSITE": 23000.0,
            "VIX": 18.0,
        }[market_id]
        return [
            _bar(market_id, "2026-09-04 10:00:00", base),
            _bar(market_id, "2026-09-04 10:01:00", base + 1.0),
        ]


def test_missing_credential_initializes_table_without_network() -> None:
    conn = _conn()
    service = UsMarketReferenceCaptureService(conn, client=_MissingClient())

    result = service.run_once(now=_now(), network_enabled=True)

    assert result["ok"] is True
    assert result["status"] == "credential_missing"
    assert result["credential_status"] == "missing"
    assert result["credential_exposed"] is False
    assert result["network_requests"] == 0
    assert result["inserted"] == 0
    assert result["missing_values_coerced_to_zero"] is False
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='research_us_market_reference'"
    ).fetchone()
    assert table is not None


def test_ready_capture_persists_all_three_indices_with_provider_timestamps() -> None:
    conn = _conn()
    client = _ReadyClient()
    service = UsMarketReferenceCaptureService(conn, client=client)

    result = service.run_once(now=_now(), network_enabled=True)

    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["network_requests"] == 3
    assert result["bars_received"] == 6
    assert result["observations_received"] == 6
    assert result["inserted"] == 6
    assert result["updated"] == 0
    assert result["capture_failures"] == 0
    assert result["markets_succeeded"] == ["SP500", "NASDAQ_COMPOSITE", "VIX"]
    assert client.calls == [
        ("SP500", "1min", 32),
        ("NASDAQ_COMPOSITE", "1min", 32),
        ("VIX", "1min", 32),
    ]

    rows = conn.execute(
        "SELECT source_id,provider_id,observed_at,value,change_pct,session_state,latency_class,data_rights,attributes_json "
        "FROM research_us_market_reference ORDER BY source_id,observed_at"
    ).fetchall()
    assert len(rows) == 6
    assert {row["source_id"] for row in rows} == {"us_sp500", "us_nasdaq_composite", "us_cboe_vix"}
    assert {row["provider_id"] for row in rows} == {TWELVE_DATA_PROVIDER_ID}
    assert {row["data_rights"] for row in rows} == {TWELVE_DATA_DATA_RIGHTS}
    assert all(row["observed_at"] > 0 for row in rows)
    assert all(row["value"] > 0 for row in rows)
    assert all(row["change_pct"] is None for row in rows)
    assert all(row["session_state"] == "unknown" for row in rows)
    assert all(row["latency_class"] == "unknown" for row in rows)
    assert all('"missing_values_coerced_to_zero":false' in row["attributes_json"] for row in rows)


def test_repeated_capture_is_idempotent_upsert() -> None:
    conn = _conn()
    client = _ReadyClient()
    service = UsMarketReferenceCaptureService(conn, client=client)

    first = service.run_once(now=_now(), network_enabled=True)
    second = service.run_once(now=_now() + 60.0, network_enabled=True)

    assert first["inserted"] == 6
    assert second["inserted"] == 0
    assert second["updated"] == 6
    assert conn.execute("SELECT COUNT(*) FROM research_us_market_reference").fetchone()[0] == 6


def test_provider_failure_is_partial_but_preserves_successful_real_observations() -> None:
    conn = _conn()
    client = _ReadyClient(fail_market="VIX")
    service = UsMarketReferenceCaptureService(conn, client=client)

    result = service.run_once(now=_now(), network_enabled=True)

    assert result["ok"] is False
    assert result["status"] == "partial"
    assert result["network_requests"] == 3
    assert result["capture_failures"] == 1
    assert result["markets_succeeded"] == ["SP500", "NASDAQ_COMPOSITE"]
    assert result["inserted"] == 4
    assert "fixture provider failure" in result["errors"]["VIX"]
    assert conn.execute("SELECT COUNT(*) FROM research_us_market_reference").fetchone()[0] == 4


def test_network_disabled_never_calls_ready_provider() -> None:
    conn = _conn()
    client = _ReadyClient()
    service = UsMarketReferenceCaptureService(conn, client=client)

    result = service.run_once(now=_now(), network_enabled=False)

    assert result["status"] == "network_disabled"
    assert result["network_requests"] == 0
    assert client.calls == []
