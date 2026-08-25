from __future__ import annotations

import threading
from typing import Any

from . import cloudflare_market_detail_publisher as base
from .strategy_lab_market import read_strategy_lab_market

_PATCH_LOCK = threading.RLock()
_BASE_COMPACT_DETAIL = base._compact_detail


def _compact_detail_with_strategy_lab(source: dict[str, Any]) -> dict[str, Any]:
    result = _BASE_COMPACT_DETAIL(source)
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    signal = result.get("signal") if isinstance(result.get("signal"), dict) else {}
    exchange = str(summary.get("exchange") or signal.get("exchange") or "").lower()
    market = str(summary.get("market") or signal.get("market") or "").upper()
    result["strategy_lab"] = read_strategy_lab_market(exchange, market)
    result["version"] = max(3, int(result.get("version") or 0))
    return result


class CloudflareMarketDetailPublisher(base.CloudflareMarketDetailPublisher):
    """Phase 4 detail publisher with compact per-market Strategy Lab results.

    The transport, rotation and D1 contract remain owned by the Phase 3 publisher.
    Only the compact detail payload is extended, under a lock, while publishing.
    """

    def publish_once(self) -> dict[str, Any]:
        with _PATCH_LOCK:
            previous = base._compact_detail
            base._compact_detail = _compact_detail_with_strategy_lab
            try:
                result = super().publish_once()
                if isinstance(result, dict):
                    result["strategy_lab_detail"] = True
                    result["detail_payload_version"] = 3
                return result
            finally:
                base._compact_detail = previous
