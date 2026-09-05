from __future__ import annotations

import sqlite3

from b3_trader.intelligence_ingest_cycle import IntelligenceIngestCycle


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class _ResponseCapture:
    def __init__(self, order: list[str]) -> None:
        self.order = order

    def run_once(self, *, now: float):
        self.order.append("response")
        return {
            "ok": True,
            "status": "ok",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "network_requests": 0,
        }


class _ReferenceCapture:
    def __init__(self, order: list[str], *, status: str = "credential_missing") -> None:
        self.order = order
        self.status = status

    def run_once(self, *, now: float, network_enabled: bool):
        self.order.append("reference")
        if self.status == "raise":
            raise RuntimeError("fixture reference failure")
        return {
            "ok": self.status != "partial",
            "status": self.status,
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "score_authority": False,
            "promotion_eligible": False,
            "credential_status": "missing" if self.status == "credential_missing" else "ready",
            "credential_exposed": False,
            "network_requests": 0 if self.status == "credential_missing" else 3,
            "missing_values_coerced_to_zero": False,
            "capture_failures": 1 if self.status == "partial" else 0,
        }


class _Sensitivity:
    def __init__(self, order: list[str]) -> None:
        self.order = order

    def run(self, *, now: float):
        self.order.append("sensitivity")
        return {
            "ok": True,
            "status": "waiting_for_reference_observations",
            "paper_only": True,
            "shadow_only": True,
            "can_place_orders": False,
            "score_mutation": False,
            "score_authority": False,
            "promotion_eligible": False,
            "network_requests": 0,
            "missing_values_coerced_to_zero": False,
            "pairs": {"pairs_ready": 0},
            "sensitivity": {"source_pairs": 0, "groups": 0},
        }


def _cycle(order: list[str], *, reference_status: str = "credential_missing") -> IntelligenceIngestCycle:
    return IntelligenceIngestCycle(
        conn=_conn(),
        fetchers={"us_sec_press_releases": lambda now: []},
        event_response_capture=_ResponseCapture(order),
        us_market_reference_capture=_ReferenceCapture(order, status=reference_status),
        event_response_us_sensitivity=_Sensitivity(order),
    )


def test_reference_capture_runs_between_response_and_sensitivity() -> None:
    order: list[str] = []
    cycle = _cycle(order)

    result = cycle.run_once(
        network_enabled=True,
        source_ids=["us_sec_press_releases"],
        now=1000,
    )

    assert order == ["response", "reference", "sensitivity"]
    assert result["status"] == "ok"
    assert result["source_failures"] == 0
    assert result["event_response_failures"] == 0
    assert result["us_market_reference_failures"] == 0
    assert result["us_market_sensitivity_failures"] == 0
    reference = result["us_market_reference_capture"]
    assert reference["status"] == "credential_missing"
    assert reference["network_requests"] == 0
    assert reference["credential_exposed"] is False
    assert reference["missing_values_coerced_to_zero"] is False


def test_reference_partial_fails_cycle_closed_without_becoming_official_source_failure() -> None:
    order: list[str] = []
    cycle = _cycle(order, reference_status="partial")

    result = cycle.run_once(
        network_enabled=True,
        source_ids=["us_sec_press_releases"],
        now=2000,
    )

    assert order == ["response", "reference", "sensitivity"]
    assert result["status"] == "partial"
    assert result["source_failures"] == 0
    assert result["event_response_failures"] == 0
    assert result["us_market_reference_failures"] == 1
    assert result["us_market_sensitivity_failures"] == 0


def test_reference_exception_is_isolated_and_fails_cycle_closed() -> None:
    order: list[str] = []
    cycle = _cycle(order, reference_status="raise")

    result = cycle.run_once(
        network_enabled=True,
        source_ids=["us_sec_press_releases"],
        now=3000,
    )

    assert order == ["response", "reference", "sensitivity"]
    assert result["status"] == "partial"
    assert result["source_failures"] == 0
    assert result["us_market_reference_failures"] == 1
    reference = result["us_market_reference_capture"]
    assert reference["status"] == "capture_error"
    assert reference["can_place_orders"] is False
    assert reference["score_mutation"] is False
    assert reference["score_authority"] is False
    assert reference["promotion_eligible"] is False
    assert reference["credential_exposed"] is False
    assert reference["network_requests"] == 0
    assert reference["missing_values_coerced_to_zero"] is False
    assert "fixture reference failure" in reference["error"]


def test_network_disabled_does_not_run_reference_capture() -> None:
    order: list[str] = []
    cycle = _cycle(order)

    result = cycle.run_once(
        network_enabled=False,
        source_ids=["us_sec_press_releases"],
        now=4000,
    )

    assert order == []
    assert result["status"] == "network_disabled"
    assert result["us_market_reference_capture"] == {"status": "not_requested"}
    assert result["us_market_reference_failures"] == 0
