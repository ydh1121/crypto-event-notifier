from __future__ import annotations

import json
from pathlib import Path

from b3_trader.paper_strategy_v2_forward_supervisor import PaperV2ForwardSupervisor


def test_supervisor_writes_fail_closed_status(tmp_path: Path) -> None:
    status = tmp_path / "status.json"
    supervisor = PaperV2ForwardSupervisor(interval_seconds=60, status_path=status)
    supervisor._write(True)
    payload = json.loads(status.read_text(encoding="utf-8"))
    assert payload["running"] is True
    assert payload["paper_only"] is True
    assert payload["shadow_only"] is True
    assert payload["can_place_real_orders"] is False
    assert payload["preset"] == "balanced_60_25_r2_agg5"
