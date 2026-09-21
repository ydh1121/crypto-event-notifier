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


class _Sensitivity:
    def __init__(self, order: list[str], *, fail: bool = False) -> None:
        self.order = order
        self.fail = fail

    def run(self, *, now: float):
        self.order.append("sensitivity")
        if self.fail:
            raise RuntimeError("fixture sensitivity failure")
        return {
            "ok": True,
            "status": "ok",
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


def _cycle(order: list[str], *, sensitivity_fail: bool = False) -> IntelligenceIngestCycle:
    return IntelligenceIngestCycle(
        conn=_conn(),
        fetchers={"us_sec_press_releases": lambda now: []},
        event_response_capture=_ResponseCapture(order),
        event_response_us_sensitivity=_Sensitivity(order, fail=sensitivity_fail),
    )


def test_network_disabled_does_not_run_response_or_us_sensitivity() -> None:
    order: list[str] = []
    cycle = _cycle(order)

    result = cycle.run_once(
        network_enabled=False,
        source_ids=["us_sec_press_releases"],
        now=1000,
    )

    assert result["status"] == "network_disabled"
    assert result["event_response_us_sensitivity"] == {"status": "not_requested"}
    assert result["us_market_sensitivity_failures"] == 0
    assert order == []


def test_strict_us_sensitivity_runs_after_event_response_capture() -> None:
    order: list[str] = []
    cycle = _cycle(order)

    result = cycle.run_once(
        network_enabled=True,
        source_ids=["us_sec_press_releases"],
        now=2000,
    )

    assert order == ["response", "sensitivity"]
    assert result["status"] == "ok"
    assert result["source_failures"] == 0
    assert result["event_response_failures"] == 0
    assert result["us_market_sensitivity_failures"] == 0
    sensitivity = result["event_response_us_sensitivity"]
    assert sensitivity["paper_only"] is True
    assert sensitivity["shadow_only"] is True
    assert sensitivity["can_place_orders"] is False
    assert sensitivity["score_mutation"] is False
    assert sensitivity["score_authority"] is False
    assert sensitivity["promotion_eligible"] is False
    assert sensitivity["missing_values_coerced_to_zero"] is False


def test_us_sensitivity_failure_is_isolated_and_fails_cycle_closed() -> None:
    order: list[str] = []
    cycle = _cycle(order, sensitivity_fail=True)

    result = cycle.run_once(
        network_enabled=True,
        source_ids=["us_sec_press_releases"],
        now=3000,
    )

    assert order == ["response", "sensitivity"]
    assert result["status"] == "partial"
    assert result["source_results"]["us_sec_press_releases"]["status"] == "ok"
    assert result["source_failures"] == 0
    assert result["event_response_failures"] == 0
    assert result["us_market_sensitivity_failures"] == 1
    sensitivity = result["event_response_us_sensitivity"]
    assert sensitivity["status"] == "capture_error"
    assert sensitivity["can_place_orders"] is False
    assert sensitivity["score_mutation"] is False
    assert sensitivity["score_authority"] is False
    assert sensitivity["promotion_eligible"] is False
    assert sensitivity["missing_values_coerced_to_zero"] is False
    assert "fixture sensitivity failure" in sensitivity["error"]


def test_default_strict_sensitivity_waiting_state_is_non_failing() -> None:
    order: list[str] = []
    cycle = IntelligenceIngestCycle(
        conn=_conn(),
        fetchers={"us_sec_press_releases": lambda now: []},
        event_response_capture=_ResponseCapture(order),
    )

    result = cycle.run_once(
        network_enabled=True,
        source_ids=["us_sec_press_releases"],
        now=4000,
    )

    assert order == ["response"]
    assert result["status"] == "ok"
    assert result["us_market_sensitivity_failures"] == 0
    sensitivity = result["event_response_us_sensitivity"]
    assert sensitivity["ok"] is True
    assert sensitivity["status"] == "waiting_for_event_response_table"
    assert sensitivity["pairs"]["pairs_ready"] == 0
    assert sensitivity["sensitivity"] == {"source_pairs": 0, "groups": 0}
