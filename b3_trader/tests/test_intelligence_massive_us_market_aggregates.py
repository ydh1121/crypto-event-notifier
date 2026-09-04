from __future__ import annotations

import sqlite3

import pytest

from b3_trader.intelligence_massive_us_market_aggregates import (
    BAR_SECONDS,
    MASSIVE_AGGREGATE_PROVIDER_ID,
    MAX_WINDOW_SECONDS,
    MassiveIndicesAggregateClient,
    MassiveUsMarketAggregateCaptureService,
    normalize_massive_1m_bar,
)


class _Response:
    def __init__(self, body: dict, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._body


class _Session:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url, *, params, headers, timeout):
        self.calls.append(
            {"url": url, "params": dict(params), "headers": dict(headers), "timeout": timeout}
        )
        if not self.responses:
            raise AssertionError("unexpected network call")
        return self.responses.pop(0)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _bar(ts_ms: int, close: float = 100.5) -> dict:
    return {"t": ts_ms, "o": 100.0, "h": 101.0, "l": 99.5, "c": close}


def test_client_requires_key_and_explicit_plan_without_network_guess() -> None:
    session = _Session([])
    missing_key = MassiveIndicesAggregateClient(api_key="", plan="advanced", session=session)
    assert missing_key.credential_status == "missing"
    with pytest.raises(ValueError, match="credential"):
        missing_key.fetch_1m("I:SPX", start_at=1000, end_at=1100)
    assert session.calls == []

    missing_plan = MassiveIndicesAggregateClient(api_key="secret", plan="", session=session)
    assert missing_plan.plan_status == "missing_or_invalid"
    with pytest.raises(ValueError, match="plan"):
        missing_plan.fetch_1m("I:SPX", start_at=1000, end_at=1100)
    assert session.calls == []


def test_client_uses_bearer_header_and_bounded_minute_endpoint() -> None:
    body = {"status": "OK", "ticker": "I:SPX", "results": [_bar(1_700_000_040_000)]}
    session = _Session([_Response(body)])
    client = MassiveIndicesAggregateClient(api_key="top-secret", plan="advanced", session=session)
    rows = client.fetch_1m("I:SPX", start_at=1_700_000_000, end_at=1_700_000_120)
    assert len(rows) == 1
    assert len(session.calls) == 1
    call = session.calls[0]
    assert "/I:SPX/range/1/minute/" in call["url"]
    assert call["params"] == {"sort": "asc", "limit": 5000}
    assert call["headers"]["Authorization"] == "Bearer top-secret"
    assert "top-secret" not in call["url"]
    assert "top-secret" not in str(call["params"])


def test_normalizer_uses_bar_close_as_observation_clock_for_advanced() -> None:
    start_ms = 1_700_000_040_000
    item = normalize_massive_1m_bar(
        "I:SPX",
        _bar(start_ms, close=4500.25),
        received_at=start_ms / 1000.0 + 120,
        plan="advanced",
    )
    assert item.source_id == "us_sp500"
    assert item.provider_id == MASSIVE_AGGREGATE_PROVIDER_ID
    assert item.observed_at == start_ms / 1000.0 + BAR_SECONDS
    assert item.value == pytest.approx(4500.25)
    assert item.latency_class == "realtime"
    assert item.delayed_seconds == 0.0
    assert item.attributes["bar_start_at"] == start_ms / 1000.0
    assert item.attributes["bar_end_at"] == start_ms / 1000.0 + BAR_SECONDS
    assert item.attributes["available_at"] == item.observed_at


def test_normalizer_preserves_starter_delay_and_basic_eod_semantics() -> None:
    start_ms = 1_700_000_040_000
    received = start_ms / 1000.0 + 2000
    starter = normalize_massive_1m_bar(
        "I:COMP", _bar(start_ms), received_at=received, plan="starter"
    )
    assert starter.source_id == "us_nasdaq_composite"
    assert starter.latency_class == "delayed"
    assert starter.delayed_seconds == 900.0
    assert starter.attributes["available_at"] == starter.observed_at + 900.0

    basic = normalize_massive_1m_bar(
        "I:VIX", _bar(start_ms), received_at=received, plan="basic"
    )
    assert basic.source_id == "us_cboe_vix"
    assert basic.latency_class == "end_of_day"
    assert basic.delayed_seconds is None
    assert basic.attributes["available_at"] is None


def test_normalizer_rejects_unaligned_or_invalid_ohlc() -> None:
    with pytest.raises(ValueError, match="minute-aligned"):
        normalize_massive_1m_bar(
            "I:SPX",
            _bar(1_700_000_040_001),
            received_at=1_700_000_200,
            plan="advanced",
        )
    bad = _bar(1_700_000_040_000)
    bad["h"] = 99.0
    with pytest.raises(ValueError, match="OHLC"):
        normalize_massive_1m_bar(
            "I:SPX", bad, received_at=1_700_000_200, plan="advanced"
        )


class _FakeClient:
    def __init__(self, *, plan: str = "advanced", fail_ticker: str = "", empty: bool = False) -> None:
        self.api_key = "secret"
        self.plan = plan
        self.fail_ticker = fail_ticker
        self.empty = empty
        self.calls: list[str] = []

    @property
    def credential_status(self) -> str:
        return "ready"

    @property
    def plan_status(self) -> str:
        return "ready"

    def fetch_1m(self, ticker: str, *, start_at: float, end_at: float):
        self.calls.append(ticker)
        if ticker == self.fail_ticker:
            raise RuntimeError("fixture entitlement failure")
        if self.empty:
            return []
        values = {"I:COMP": 18000.0, "I:SPX": 5500.0, "I:VIX": 16.0}
        return [_bar(int(start_at * 1000), close=values[ticker])]


def test_capture_is_atomic_across_required_tickers_on_failure() -> None:
    conn = _conn()
    fake = _FakeClient(fail_ticker="I:SPX")
    service = MassiveUsMarketAggregateCaptureService(conn, client=fake)
    result = service.run_window(
        start_at=1_700_000_040,
        end_at=1_700_000_100,
        now=1_700_000_500,
        network_enabled=True,
    )
    assert result["status"] == "partial"
    assert result["capture_failures"] == 1
    assert result["observations_inserted"] == 0
    count = conn.execute("SELECT COUNT(*) FROM research_us_market_reference").fetchone()[0]
    assert count == 0


def test_capture_stores_complete_three_index_path() -> None:
    conn = _conn()
    fake = _FakeClient()
    service = MassiveUsMarketAggregateCaptureService(conn, client=fake)
    result = service.run_window(
        start_at=1_700_000_040,
        end_at=1_700_000_100,
        now=1_700_000_500,
        network_enabled=True,
    )
    assert result["status"] == "ok"
    assert result["network_requests"] == 3
    assert result["bars_received"] == 3
    assert result["observations_inserted"] == 3
    rows = conn.execute(
        "SELECT source_id,provider_id,value,observed_at FROM research_us_market_reference ORDER BY source_id"
    ).fetchall()
    assert len(rows) == 3
    assert {row["source_id"] for row in rows} == {
        "us_nasdaq_composite",
        "us_sp500",
        "us_cboe_vix",
    }
    assert {row["provider_id"] for row in rows} == {MASSIVE_AGGREGATE_PROVIDER_ID}
    assert {row["observed_at"] for row in rows} == {1_700_000_100.0}


def test_empty_provider_intervals_are_not_filled_with_synthetic_bars() -> None:
    conn = _conn()
    fake = _FakeClient(empty=True)
    service = MassiveUsMarketAggregateCaptureService(conn, client=fake)
    result = service.run_window(
        start_at=1_700_000_040,
        end_at=1_700_000_100,
        now=1_700_000_500,
        network_enabled=True,
    )
    assert result["status"] == "ok_no_bars"
    assert result["network_requests"] == 3
    assert result["bars_received"] == 0
    assert conn.execute("SELECT COUNT(*) FROM research_us_market_reference").fetchone()[0] == 0


def test_capture_refuses_windows_larger_than_48_hours_before_network() -> None:
    conn = _conn()
    fake = _FakeClient()
    service = MassiveUsMarketAggregateCaptureService(conn, client=fake)
    result = service.run_window(
        start_at=1_700_000_000,
        end_at=1_700_000_000 + MAX_WINDOW_SECONDS + 1,
        now=1_700_200_000,
        network_enabled=True,
    )
    assert result["status"] == "window_too_large"
    assert fake.calls == []
