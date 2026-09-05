from __future__ import annotations

import pytest

from b3_trader.intelligence_us_index_intraday import (
    TWELVE_DATA_TIME_SERIES_URL,
    TwelveDataIndexClient,
)


class _Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class _Session:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.payload)


def _payload(symbol: str = "SPX") -> dict[str, object]:
    return {
        "meta": {
            "symbol": symbol,
            "interval": "1min",
            "currency": "USD",
            "exchange_timezone": "America/New_York",
            "exchange": "INDEX",
            "type": "Index",
        },
        "values": [
            {
                "datetime": "2026-09-04 12:00:00",
                "open": "6500.1",
                "high": "6501.2",
                "low": "6499.8",
                "close": "6500.8",
                "volume": None,
            },
            {
                "datetime": "2026-09-04 12:01:00",
                "open": "6500.8",
                "high": "6502.0",
                "low": "6500.4",
                "close": "6501.7",
                "volume": "0",
            },
        ],
        "status": "ok",
    }


def test_missing_credential_fails_before_network() -> None:
    session = _Session(_payload())
    client = TwelveDataIndexClient(api_key="", session=session)
    assert client.credential_status == "missing"
    with pytest.raises(ValueError, match="credential is missing"):
        client.fetch_time_series("SP500")
    assert session.calls == []


def test_client_uses_authorization_header_and_not_api_key_query_param() -> None:
    session = _Session(_payload())
    client = TwelveDataIndexClient(api_key="secret-key", session=session, attempts=1)
    bars = client.fetch_time_series("SP500", interval="1min", outputsize=2)
    assert len(bars) == 2
    assert bars[-1].market_id == "SP500"
    assert bars[-1].requested_symbol == "SPX"
    assert bars[-1].provider_symbol == "SPX"
    assert bars[-1].instrument_type == "Index"
    assert bars[-1].close == pytest.approx(6501.7)

    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == TWELVE_DATA_TIME_SERIES_URL
    assert "secret-key" not in url
    assert kwargs["headers"]["Authorization"] == "apikey secret-key"
    assert "apikey" not in {str(key).casefold() for key in kwargs["params"]}
    assert kwargs["params"]["symbol"] == "SPX"
    assert kwargs["params"]["interval"] == "1min"
    assert kwargs["params"]["outputsize"] == "2"


def test_non_index_resolution_fails_closed() -> None:
    payload = _payload()
    payload["meta"] = dict(payload["meta"], type="Common Stock")
    client = TwelveDataIndexClient(api_key="secret", session=_Session(payload), attempts=1)
    with pytest.raises(ValueError, match="non-index"):
        client.fetch_time_series("SP500")


def test_provider_error_is_sanitized_and_does_not_require_secret_in_url() -> None:
    session = _Session({"status": "error", "code": 403, "message": "plan does not include index data"})
    client = TwelveDataIndexClient(api_key="secret-key", session=session, attempts=1)
    with pytest.raises(ValueError, match="Twelve Data error 403") as exc:
        client.fetch_time_series("VIX")
    assert "secret-key" not in str(exc.value)


def test_symbol_overrides_are_bounded_and_explicit() -> None:
    client = TwelveDataIndexClient(
        api_key="secret",
        session=_Session(_payload("CUSTOM")),
        attempts=1,
        symbols={"SP500": "CUSTOM"},
    )
    bars = client.fetch_time_series("SP500")
    assert bars[0].requested_symbol == "CUSTOM"
