from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .multi_exchange_paper import MultiExchangePaperDemo

STATUS_PATH = Path("dashboard/runtime-demo-upbit.json")


class UpbitPaperResearchRunner:
    """Lazy Supervisor runner for Phase 3 Upbit PAPER research."""

    def __init__(self) -> None:
        self.demo: MultiExchangePaperDemo | None = None

    def _demo(self) -> MultiExchangePaperDemo:
        if self.demo is None:
            self.demo = MultiExchangePaperDemo("upbit", "adaptive")
        return self.demo

    def run_once(self) -> dict[str, Any]:
        demo = self._demo()
        demo.scan_once()
        if not STATUS_PATH.exists():
            return {"status": "scanned", "exchange": "upbit", "strategy": "adaptive"}
        try:
            payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        return {
            "status": "scanned",
            "exchange": "upbit",
            "strategy": "adaptive",
            "market_count": int(payload.get("market_count") or 0),
            "scanned": int(payload.get("scanned_count") or 0),
            "scan_total": int(payload.get("scan_total") or 0),
            "active_positions": int(payload.get("active_positions") or 0),
            "warning_markets": int(payload.get("warning_markets") or 0),
            "scan_number": int(payload.get("scan_number") or 0),
            "error": str(payload.get("error") or ""),
        }
