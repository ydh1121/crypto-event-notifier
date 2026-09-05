from __future__ import annotations

import json
import threading
from typing import Any

from . import cloudflare_market_detail_publisher as base
from .market_detail_feature_projection import apply_market_feature_projection
from .strategy_lab_market import read_strategy_lab_market

_PATCH_LOCK = threading.RLock()
_BASE_COMPACT_DETAIL = base._compact_detail

# The Viewer summary snapshot carries current all-market rankings. Detailed
# per-market history is heavier and D1 row-write metered, so the 24/7 path keeps
# a small priority set fresh while rotating the rest at a bounded rate.
_SAFE_LIMITS = {
    "bithumb": {"priority": 4, "rotating": 12, "max_batch": 16},
    "upbit": {"priority": 2, "rotating": 6, "max_batch": 8},
}


def _budgeted_source_configs() -> tuple[dict[str, Any], ...]:
    configs: list[dict[str, Any]] = []
    for source in base.SOURCE_CONFIGS:
        exchange = str(source.get("exchange") or "").lower()
        limits = _SAFE_LIMITS.get(exchange)
        configs.append({**source, **limits} if limits else dict(source))
    return tuple(configs)


def _compact_detail_with_strategy_lab(source: dict[str, Any]) -> dict[str, Any]:
    result = _BASE_COMPACT_DETAIL(source)
    apply_market_feature_projection(source, result)
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    signal = result.get("signal") if isinstance(result.get("signal"), dict) else {}
    exchange = str(summary.get("exchange") or signal.get("exchange") or "").lower()
    market = str(summary.get("market") or signal.get("market") or "").upper()
    result["strategy_lab"] = read_strategy_lab_market(exchange, market)
    result["version"] = max(4, int(result.get("version") or 0))
    return result


class CloudflareMarketDetailPublisher(base.CloudflareMarketDetailPublisher):
    """Phase 4 detail publisher with compact Strategy Lab + market features.

    Transport, rotation and D1 contracts stay owned by the Phase 3 publisher.
    The 24/7 supervisor additionally applies a D1 write budget here so Viewer
    detail refreshes cannot overwhelm the Free-tier row-write allowance.
    """

    def publish_once(self) -> dict[str, Any]:
        with _PATCH_LOCK:
            previous_compactor = base._compact_detail
            previous_configs = base.SOURCE_CONFIGS
            base._compact_detail = _compact_detail_with_strategy_lab
            base.SOURCE_CONFIGS = _budgeted_source_configs()
            try:
                result = super().publish_once()
                if isinstance(result, dict):
                    result["strategy_lab_detail"] = True
                    result["market_feature_detail"] = True
                    result["detail_payload_version"] = 4
                    result["d1_write_budget"] = {
                        "max_details_per_run": sum(
                            int(config.get("max_batch") or 0) for config in base.SOURCE_CONFIGS
                        ),
                        "bithumb_max": 16,
                        "upbit_max": 8,
                    }
                return result
            finally:
                base._compact_detail = previous_compactor
                base.SOURCE_CONFIGS = previous_configs


def main() -> None:
    print(json.dumps(CloudflareMarketDetailPublisher().publish_once(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
