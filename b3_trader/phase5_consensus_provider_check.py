from __future__ import annotations

import json
import sys
import time
from typing import Any

from dotenv import load_dotenv

from .intelligence_trading_economics_consensus import (
    TradingEconomicsCalendarClient,
    _metric_id,
)


def _safe_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    # Authentication is header-only in the provider client, so the key should
    # never appear in the URL. Keep the CLI output bounded regardless.
    return text.replace("\r", " ").replace("\n", " ")[:300]


def run_check(*, now: float | None = None, client: Any | None = None) -> tuple[dict[str, Any], int]:
    load_dotenv()
    current = float(now if now is not None else time.time())
    provider = client or TradingEconomicsCalendarClient()
    credential_status = str(getattr(provider, "credential_status", "missing") or "missing")

    result: dict[str, Any] = {
        "ok": False,
        "provider": "trading_economics",
        "credential_status": credential_status,
        "credential_exposed": False,
        "network_requests": 0,
        "calendar_rows": 0,
        "supported_metric_rows": 0,
        "status": "not_checked",
    }

    if credential_status != "ready":
        result["status"] = "credential_missing"
        return result, 1

    try:
        result["network_requests"] = 1
        rows = provider.fetch_us_calendar(start_at=current, end_at=current + 86400)
    except Exception as exc:
        result["status"] = "provider_error"
        result["error"] = _safe_error(exc)
        return result, 2

    clean_rows = [dict(row) for row in rows if isinstance(row, dict)]
    supported = sum(1 for row in clean_rows if _metric_id(row))
    result.update(
        {
            "ok": True,
            "status": "ok",
            "calendar_rows": len(clean_rows),
            "supported_metric_rows": supported,
        }
    )
    return result, 0


def main() -> None:
    result, code = run_check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
