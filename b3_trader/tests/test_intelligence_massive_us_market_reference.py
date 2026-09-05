from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from b3_trader.intelligence_massive_us_market_reference import (
    MASSIVE_INDICES_SNAPSHOT_URL,
    MASSIVE_PROVIDER_ID,
    MassiveIndicesSnapshotClient,
    MassiveUsMarketReferenceCaptureService,
    normalize_massive_snapshot,
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _row(
    ticker: str,
    *,
    last_updated_ns: int,
    value: float,
    timeframe: str = "REAL-TIME",
    market_status: str = "regular_trading",
    change_percent: float = 1.25,
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "name": ticker,
        "last_updated": last_updated_ns,
        "market_status": market_status,
        "timeframe": timeframe,
        "type": "indices",
        "value": value,
        "session": {"change_percent": change_percent, "previous_close": value - 10},
    }


class _Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class _Session:
    def __init__(self, payload_by_ticker):
        self.payload_by_ticker = payload_by_ticker
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        ticker = kwargs["params"]["ticker"]
        return _Response(self.payload_by_ticker[ticker])


class _Client:
    credential_status = "ready"

    def __init__(self, rows):
        self.rows = dict(rows)
        self.calls = []

    def fetch_snapshot(self, ticker: str):
        self.calls.append(ticker)
        value = self.rows[ticker]
        if isinstance(value, Exception):
            raise value
        return dict(value)


class _MissingClient:
    credential_status = "missing"

    def __init__(self):
        self.calls = []

    def fetch_snapshot(self, ticker: str):
        self.calls.append(ticker)
        raise AssertionError("network must not be called without Massive credential")


def test_client_uses_bearer_header_and_exact_ticker_filter() -> None:
    payload = {
        "status": "OK",
        "results": [_row("I:COMP", last_updated_ns=2_000_000_000_000, value=20000.0)],
    }
    session = _Session({"I:COMP": payload})
    client = MassiveIndicesSnapshotClient(api_key="massive-secret", session=session, attempts=1)
    result = client.fetch_snapshot("I:COMP")
    assert result["ticker"] == "I:COMP"
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == MASSIVE_INDICES_SNAPSHOT_URL
    assert "massive-secret" not in url
    assert kwargs["params"] == {"ticker": "I:COMP", "limit": 1}
    assert kwargs["headers"]["Authorization"] == "Bearer massive-secret"


def test_snapshot_normalization_maps_ticker_timestamp_session_and_latency() -> None:
    realtime = normalize_massive_snapshot(
        _row(
            "I:COMP",
            last_updated_ns=1_999_500_000_000,
            value=20500.0,
            timeframe="REAL-TIME",
            market_status="regular_trading",
        ),
        received_at=2000.0,
    )
    assert realtime.source_id == "us_nasdaq_composite"
    assert realtime.provider_id == MASSIVE_PROVIDER_ID
    assert realtime.observed_at == pytest.approx(1999.5)
    assert realtime.latency_class == "realtime"
    assert realtime.delayed_seconds == 0.0
    assert realtime.session_state == "regular"
    assert realtime.attributes["feed"] == "Nasdaq"
    assert realtime.attributes["score_authority"] is False

    delayed = normalize_massive_snapshot(
        _row(
            "I:SPX",
            last_updated_ns=1_100_000_000_000,
            value=6500.0,
            timeframe="DELAYED",
            market_status="late_trading",
        ),
        received_at=2000.0,
    )
    assert delayed.source_id == "us_sp500"
    assert delayed.latency_class == "delayed"
    assert delayed.delayed_seconds == 900.0
    assert delayed.session_state == "after_hours"
    assert delayed.attributes["feed"] == "Cboe"


def test_normalizer_rejects_unknown_timeframe_status_and_future_clock() -> None:
    with pytest.raises(ValueError, match="timeframe"):
        normalize_massive_snapshot(
            _row("I:VIX", last_updated_ns=1_000_000_000_000, value=20.0, timeframe="UNKNOWN"),
            received_at=1000.0,
        )
    with pytest.raises(ValueError, match="market_status"):
        normalize_massive_snapshot(
            _row("I:VIX", last_updated_ns=1_000_000_000_000, value=20.0, market_status="mystery"),
            received_at=1000.0,
        )
    with pytest.raises(ValueError, match="ahead"):
        normalize_massive_snapshot(
            _row("I:VIX", last_updated_ns=1_100_000_000_000, value=20.0),
            received_at=1000.0,
        )


def test_capture_service_missing_credential_is_zero_network() -> None:
    client = _MissingClient()
    result = MassiveUsMarketReferenceCaptureService(_conn(), client=client).run_once(
        now=2000.0, network_enabled=True
    )
    assert result["status"] == "credential_missing"
    assert result["network_requests"] == 0
    assert client.calls == []


def test_capture_service_atomically_stores_comp_spx_vix() -> None:
    conn = _conn()
    rows = {
        "I:COMP": _row("I:COMP", last_updated_ns=1_999_000_000_000, value=21000.0),
        "I:SPX": _row("I:SPX", last_updated_ns=1_999_100_000_000, value=6600.0),
        "I:VIX": _row("I:VIX", last_updated_ns=1_999_200_000_000, value=18.5),
    }
    client = _Client(rows)
    result = MassiveUsMarketReferenceCaptureService(conn, client=client).run_once(
        now=2000.0, network_enabled=True
    )
    assert result["status"] == "ok"
    assert result["network_requests"] == 3
    assert result["observations_inserted"] == 3
    assert client.calls == ["I:COMP", "I:SPX", "I:VIX"]
    saved = conn.execute(
        "SELECT source_id,provider_id FROM research_us_market_reference ORDER BY source_id"
    ).fetchall()
    assert {row["source_id"] for row in saved} == {
        "us_nasdaq_composite",
        "us_sp500",
        "us_cboe_vix",
    }
    assert {row["provider_id"] for row in saved} == {MASSIVE_PROVIDER_ID}


def test_capture_service_entitlement_failure_writes_zero_rows() -> None:
    conn = _conn()
    rows = {
        "I:COMP": _row("I:COMP", last_updated_ns=1_999_000_000_000, value=21000.0),
        "I:SPX": RuntimeError("NOT_ENTITLED"),
        "I:VIX": _row("I:VIX", last_updated_ns=1_999_200_000_000, value=18.5),
    }
    result = MassiveUsMarketReferenceCaptureService(conn, client=_Client(rows)).run_once(
        now=2000.0, network_enabled=True
    )
    assert result["status"] == "partial"
    assert result["capture_failures"] == 1
    assert result["observations_inserted"] == 0
    assert conn.execute("SELECT COUNT(*) FROM research_us_market_reference").fetchone()[0] == 0


def test_adapter_uses_comp_for_nasdaq_composite_not_ndx() -> None:
    text = (Path(__file__).resolve().parents[1] / "intelligence_massive_us_market_reference.py").read_text(
        encoding="utf-8"
    )
    assert '"I:COMP": ("us_nasdaq_composite", "Nasdaq")' in text
    assert '"I:NDX": ("us_nasdaq_composite"' not in text


def test_massive_reference_module_has_no_score_paper_decision_or_order_dependency() -> None:
    path = Path(__file__).resolve().parents[1] / "intelligence_massive_us_market_reference.py"
    text = path.read_text(encoding="utf-8").casefold()
    assert "score_engine" not in text
    assert "paper_engine" not in text
    assert "order_executor" not in text
    assert "trading_decision" not in text
