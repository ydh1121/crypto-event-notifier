from __future__ import annotations

from b3_trader.paper_runtime_liveness import (
    external_status_owner_is_alive,
    stale_after_seconds,
    status_is_fresh,
)


def test_stale_threshold_matches_dashboard_contract() -> None:
    assert stale_after_seconds(180.0) == 420.0
    assert stale_after_seconds(300.0) == 660.0


def test_status_freshness_rejects_missing_and_stale_status() -> None:
    assert status_is_fresh({}, scan_interval_seconds=180.0, now=1_000.0) is False
    assert status_is_fresh({"updated_at": 0}, scan_interval_seconds=180.0, now=1_000.0) is False
    assert status_is_fresh({"updated_at": 600.0}, scan_interval_seconds=180.0, now=1_000.0) is True
    assert status_is_fresh({"updated_at": 579.0}, scan_interval_seconds=180.0, now=1_000.0) is False


def test_live_pid_cannot_mask_stale_status() -> None:
    checked: list[int] = []

    def pid_alive(pid: int) -> bool:
        checked.append(pid)
        return True

    assert external_status_owner_is_alive(
        {"pid": 11644, "updated_at": 500.0},
        scan_interval_seconds=180.0,
        pid_alive=pid_alive,
        current_pid=999,
        now=1_000.0,
    ) is False
    assert checked == []


def test_fresh_external_pid_requires_process_to_exist() -> None:
    assert external_status_owner_is_alive(
        {"pid": 11644, "updated_at": 900.0},
        scan_interval_seconds=180.0,
        pid_alive=lambda _pid: False,
        current_pid=999,
        now=1_000.0,
    ) is False
    assert external_status_owner_is_alive(
        {"pid": 11644, "updated_at": 900.0},
        scan_interval_seconds=180.0,
        pid_alive=lambda _pid: True,
        current_pid=999,
        now=1_000.0,
    ) is True


def test_current_process_pid_is_not_treated_as_external_owner() -> None:
    assert external_status_owner_is_alive(
        {"pid": 999, "updated_at": 900.0},
        scan_interval_seconds=180.0,
        pid_alive=lambda _pid: True,
        current_pid=999,
        now=1_000.0,
    ) is False


def test_fresh_pidless_legacy_status_is_temporarily_accepted() -> None:
    assert external_status_owner_is_alive(
        {"pid": 0, "updated_at": 900.0},
        scan_interval_seconds=180.0,
        pid_alive=lambda _pid: False,
        current_pid=999,
        now=1_000.0,
    ) is True
