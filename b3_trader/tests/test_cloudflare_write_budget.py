from __future__ import annotations

import json
from pathlib import Path

from b3_trader.cloudflare_market_detail_strategy_lab import _budgeted_source_configs
from b3_trader.research_control import COMPONENT_DEFINITIONS, load_control


def test_cloudflare_component_minimums_are_write_budgeted() -> None:
    snapshot = COMPONENT_DEFINITIONS["cloudflare-snapshot-publish"]
    details = COMPONENT_DEFINITIONS["cloudflare-market-detail-publish"]
    assert snapshot["default_interval_seconds"] >= 60
    assert snapshot["min_interval_seconds"] >= 60
    assert details["default_interval_seconds"] >= 300
    assert details["min_interval_seconds"] >= 300


def test_old_local_control_is_clamped_without_losing_component_state(tmp_path: Path) -> None:
    path = tmp_path / "components.json"
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "revision": 7,
                "enabled": True,
                "components": {
                    "cloudflare-snapshot-publish": {
                        "enabled": True,
                        "interval_seconds": 20,
                        "run_nonce": 3,
                    },
                    "cloudflare-market-detail-publish": {
                        "enabled": True,
                        "interval_seconds": 30,
                        "run_nonce": 4,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    control = load_control(path)
    snapshot = control["components"]["cloudflare-snapshot-publish"]
    details = control["components"]["cloudflare-market-detail-publish"]
    assert snapshot["enabled"] is True
    assert snapshot["interval_seconds"] == 60
    assert snapshot["run_nonce"] == 3
    assert details["enabled"] is True
    assert details["interval_seconds"] == 300
    assert details["run_nonce"] == 4


def test_strategy_lab_detail_publisher_stays_below_endpoint_batch_limit() -> None:
    configs = _budgeted_source_configs()
    by_exchange = {str(row["exchange"]): row for row in configs}
    assert by_exchange["bithumb"]["max_batch"] == 16
    assert by_exchange["upbit"]["max_batch"] == 8
    assert sum(int(row["max_batch"]) for row in configs) == 24
    assert all(int(row["max_batch"]) <= 40 for row in configs)
