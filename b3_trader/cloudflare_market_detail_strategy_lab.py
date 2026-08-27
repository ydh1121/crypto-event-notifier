from __future__ import annotations

import threading
from typing import Any

from . import cloudflare_market_detail_publisher as base
from .market_detail_feature_projection import apply_market_feature_projection
from .strategy_lab_market import read_strategy_lab_market

_PATCH_LOCK = threading.RLock()
_BASE_COMPACT_DETAIL = base._compact_detail


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
    Feature calculations remain outside this projection layer.
    """

    def publish_once(self) -> dict[str, Any]:
        with _PATCH_LOCK:
            previous = base._compact_detail
            base._compact_detail = _compact_detail_with_strategy_lab
            try:
                result = super().publish_once()
                if isinstance(result, dict):
                    result["strategy_lab_detail"] = True
                    result["market_feature_detail"] = True
                    result["detail_payload_version"] = 4
                return result
            finally:
                base._compact_detail = previous
