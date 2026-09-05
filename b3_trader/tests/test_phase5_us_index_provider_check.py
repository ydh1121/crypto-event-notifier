from __future__ import annotations

from dataclasses import dataclass

from b3_trader.phase5_us_index_provider_check import run_check


@dataclass
class _Bar:
    market_id: str
    requested_symbol: str
    provider_symbol: str
    interval: str = "1min"
    datetime: str = "2026-09-04 12:01:00"
    open: float = 1.0
    high: float = 1.0
    low: float = 1.0
    close: float = 1.0
    volume: float | None = None
    exchange: str = "INDEX"
    exchange_timezone: str = "America/New_York"
    instrument_type: str = "Index"


class _MissingClient:
    credential_status = "missing"

    def required_symbols(self):
        raise AssertionError("configuration/network must not be touched")


class _ReadyClient:
    credential_status = "ready"

    def __init__(self):
        self.calls = []

    def required_symbols(self):
        return {
            "SP500": "SPX",
            "NASDAQ_COMPOSITE": "IXIC",
            "VIX": "VIX",
        }

    def fetch_time_series(self, market_id: str, *, interval: str, outputsize: int):
        self.calls.append((market_id, interval, outputsize))
        symbol = self.required_symbols()[market_id]
        return [
            _Bar(market_id=market_id, requested_symbol=symbol, provider_symbol=symbol),
            _Bar(
                market_id=market_id,
                requested_symbol=symbol,
                provider_symbol=symbol,
                datetime="2026-09-04 12:02:00",
            ),
        ]


class _ErrorClient(_ReadyClient):
    def fetch_time_series(self, market_id: str, *, interval: str, outputsize: int):
        self.calls.append((market_id, interval, outputsize))
        raise RuntimeError("provider unavailable\nretry later")


def test_missing_credential_is_fail_closed_without_requests() -> None:
    result, code = run_check(client=_MissingClient())
    assert code == 1
    assert result["ok"] is False
    assert result["status"] == "credential_missing"
    assert result["network_requests"] == 0
    assert result["credential_exposed"] is False


def test_ready_provider_checks_all_three_required_indices() -> None:
    client = _ReadyClient()
    result, code = run_check(client=client)
    assert code == 0
    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["network_requests"] == 3
    assert set(result["markets"]) == {"SP500", "NASDAQ_COMPOSITE", "VIX"}
    assert all(row["bars"] == 2 for row in result["markets"].values())
    assert client.calls == [
        ("SP500", "1min", 2),
        ("NASDAQ_COMPOSITE", "1min", 2),
        ("VIX", "1min", 2),
    ]


def test_provider_error_is_bounded_single_line_and_no_secret_flag() -> None:
    result, code = run_check(client=_ErrorClient())
    assert code == 2
    assert result["ok"] is False
    assert result["status"] == "provider_error"
    assert result["network_requests"] == 1
    assert "\n" not in result["error"]
    assert result["credential_exposed"] is False
