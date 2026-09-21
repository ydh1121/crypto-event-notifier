from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv

from .auto_demo_v2 import DB_PATH
from .phase5_gate_matrix import evaluate_gate_matrix
from .research_control import platform_snapshot


def build_phase5_gate_dashboard_snapshot(
    *,
    path: Path | str = DB_PATH,
    runtime_snapshot: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the Phase 5 gate matrix for the dashboard without network calls.

    The dashboard path deliberately reuses the already-persisted research supervisor
    snapshot instead of calling the local HTTP API again. This keeps the endpoint
    read-only, avoids recursive localhost requests, and never emits credential values.
    """

    load_dotenv()
    snapshot = dict(runtime_snapshot) if runtime_snapshot is not None else platform_snapshot()
    environment = dict(env) if env is not None else dict(os.environ)

    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        result = evaluate_gate_matrix(snapshot=snapshot, conn=conn, env=environment)
    finally:
        conn.close()

    return {
        **result,
        "read_only": True,
        "source": "persisted_research_runtime_and_local_sqlite",
        "external_network_requests": 0,
        "credential_values_exposed": False,
    }
