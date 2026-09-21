from __future__ import annotations

import json
from typing import Any

from dotenv import load_dotenv

from .intelligence_us_index_intraday import TwelveDataIndexClient


def _safe_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return text.replace("\r", " ").replace("\n", " ")[:300]


def run_check(*, client: Any | None = None) -> tuple[dict[str, Any], int]:
    load_dotenv()
    provider = client or TwelveDataIndexClient()
    credential_status = str(getattr(provider, "credential_status", "missing") or "missing")

    result: dict[str, Any] = {
        "ok": False,
        "provider": "twelve_data",
        "credential_status": credential_status,
        "credential_exposed": False,
        "paper_only": True,
        "shadow_only": True,
        "can_place_orders": False,
        "score_mutation": False,
        "interval": "1min",
        "network_requests": 0,
        "markets": {},
        "status": "not_checked",
    }

    if credential_status != "ready":
        result["status"] = "credential_missing"
        return result, 1

    try:
        symbols = provider.required_symbols()
    except Exception as exc:
        result["status"] = "configuration_error"
        result["error"] = _safe_error(exc)
        return result, 2

    markets: dict[str, Any] = {}
    try:
        for market_id in ("SP500", "NASDAQ_COMPOSITE", "VIX"):
            result["network_requests"] += 1
            bars = provider.fetch_time_series(market_id, interval="1min", outputsize=2)
            latest = bars[-1]
            markets[market_id] = {
                "configured_symbol": symbols[market_id],
                "provider_symbol": latest.provider_symbol,
                "instrument_type": latest.instrument_type,
                "exchange": latest.exchange,
                "exchange_timezone": latest.exchange_timezone,
                "bars": len(bars),
                "latest_datetime": latest.datetime,
            }
    except Exception as exc:
        result["markets"] = markets
        result["status"] = "provider_error"
        result["error"] = _safe_error(exc)
        return result, 2

    result.update({"ok": True, "status": "ok", "markets": markets})
    return result, 0


def main() -> None:
    result, code = run_check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
