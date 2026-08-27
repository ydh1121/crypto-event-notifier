from __future__ import annotations

from typing import Any


def apply_market_feature_projection(source: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Copy precomputed market features into a bounded Cloudflare detail payload."""
    returns = source.get("return_windows") if isinstance(source.get("return_windows"), dict) else {}
    result["return_windows"] = {
        "as_of_ts": returns.get("as_of_ts"),
        "coverage": int(returns.get("coverage") or 0),
        "d1_pct": returns.get("d1_pct"),
        "d2_pct": returns.get("d2_pct"),
        "d3_pct": returns.get("d3_pct"),
        "d4_pct": returns.get("d4_pct"),
        "d5_pct": returns.get("d5_pct"),
    }
    result["version"] = max(4, int(result.get("version") or 0))
    return result
