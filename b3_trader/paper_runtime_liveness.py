from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

MIN_STALE_SECONDS = 420.0


def stale_after_seconds(scan_interval_seconds: float) -> float:
    return max(MIN_STALE_SECONDS, max(0.0, float(scan_interval_seconds)) * 2.2)


def status_is_fresh(
    payload: dict[str, Any] | None,
    *,
    scan_interval_seconds: float,
    now: float | None = None,
) -> bool:
    if not payload:
        return False
    updated_at = float(payload.get("updated_at") or 0.0)
    if updated_at <= 0:
        return False
    current = float(time.time() if now is None else now)
    return current - updated_at <= stale_after_seconds(scan_interval_seconds)


def external_status_owner_is_alive(
    payload: dict[str, Any] | None,
    *,
    scan_interval_seconds: float,
    pid_alive: Callable[[int], bool],
    current_pid: int | None = None,
    now: float | None = None,
) -> bool:
    """Return true only for a fresh status whose external process still exists.

    A live/reused PID with a stale status must never suppress PAPER recovery.
    PID-less legacy status is accepted only while fresh.
    """
    if not status_is_fresh(
        payload,
        scan_interval_seconds=scan_interval_seconds,
        now=now,
    ):
        return False

    source = payload or {}
    pid = int(source.get("pid") or 0)
    owner_pid = os.getpid() if current_pid is None else int(current_pid)
    if pid:
        return pid != owner_pid and bool(pid_alive(pid))
    return True
