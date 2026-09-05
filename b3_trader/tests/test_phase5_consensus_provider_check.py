from __future__ import annotations

from b3_trader.phase5_consensus_provider_check import run_check


class _MissingClient:
    credential_status = "missing"

    def fetch_us_calendar(self, **kwargs):
        raise AssertionError("network must not be called")


class _ReadyClient:
    credential_status = "ready"

    def __init__(self):
        self.calls = []

    def fetch_us_calendar(self, *, start_at: float, end_at: float):
        self.calls.append((start_at, end_at))
        return [
            {
                "Country": "United States",
                "Event": "Inflation Rate MoM",
                "Category": "Inflation Rate MoM",
            },
            {
                "Country": "United States",
                "Event": "Unrelated Event",
                "Category": "Unrelated Event",
            },
        ]


class _ErrorClient:
    credential_status = "ready"

    def fetch_us_calendar(self, **kwargs):
        raise RuntimeError("provider unavailable\nretry later")


def test_missing_credential_is_fail_closed_without_network() -> None:
    result, code = run_check(now=1000, client=_MissingClient())
    assert code == 1
    assert result["ok"] is False
    assert result["status"] == "credential_missing"
    assert result["network_requests"] == 0
    assert result["credential_exposed"] is False


def test_ready_provider_performs_one_bounded_calendar_probe() -> None:
    client = _ReadyClient()
    result, code = run_check(now=1000, client=client)
    assert code == 0
    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["network_requests"] == 1
    assert result["calendar_rows"] == 2
    assert result["supported_metric_rows"] == 1
    assert client.calls == [(1000, 87400)]


def test_provider_error_is_bounded_and_single_line() -> None:
    result, code = run_check(now=1000, client=_ErrorClient())
    assert code == 2
    assert result["ok"] is False
    assert result["status"] == "provider_error"
    assert result["network_requests"] == 1
    assert "\n" not in result["error"]
    assert result["credential_exposed"] is False
