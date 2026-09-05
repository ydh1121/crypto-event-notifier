from __future__ import annotations

from typing import Any


def _compact_relative_strength(source: dict[str, Any]) -> dict[str, Any]:
    relative = source.get("relative_strength") if isinstance(source.get("relative_strength"), dict) else {}
    horizons = relative.get("horizons") if isinstance(relative.get("horizons"), dict) else {}
    compact_horizons: dict[str, Any] = {}
    for key in ("1", "3", "7", "30"):
        row = horizons.get(key) if isinstance(horizons.get(key), dict) else {}
        if not row:
            continue
        compact_horizons[key] = {
            "as_of_ts": row.get("as_of_ts"),
            "asset_return_pct": row.get("asset_return_pct"),
            "btc_return_pct": row.get("btc_return_pct"),
            "eth_return_pct": row.get("eth_return_pct"),
            "vs_btc_pp": row.get("vs_btc_pp"),
            "vs_eth_pp": row.get("vs_eth_pp"),
            "breadth_positive_pct": row.get("breadth_positive_pct"),
            "breadth_median_return_pct": row.get("breadth_median_return_pct"),
            "vs_breadth_median_pp": row.get("vs_breadth_median_pp"),
            "breadth_sample_count": int(row.get("breadth_sample_count") or 0),
            "breadth_universe_count": int(row.get("breadth_universe_count") or 0),
            "breadth_coverage_pct": row.get("breadth_coverage_pct"),
            "breadth_ready": bool(row.get("breadth_ready")),
            "source_timeframe": str(row.get("source_timeframe") or "1d"),
            "source_ts": row.get("source_ts"),
            "received_at": row.get("received_at"),
            "feature_version": int(row.get("feature_version") or 0),
        }
    return {
        "feature_version": int(relative.get("feature_version") or 0),
        "horizons": compact_horizons,
        "paper_only": True,
        "score_wired": False,
    }


def _compact_cross_exchange_gap(source: dict[str, Any]) -> dict[str, Any]:
    gap = source.get("cross_exchange_gap") if isinstance(source.get("cross_exchange_gap"), dict) else {}
    return {
        "feature_version": int(gap.get("feature_version") or 0),
        "identity_verified": bool(gap.get("identity_verified")),
        "identity_basis": str(gap.get("identity_basis") or ""),
        "gap_ready": bool(gap.get("gap_ready")),
        "bithumb_price": gap.get("bithumb_price"),
        "upbit_price": gap.get("upbit_price"),
        "bithumb_source_ts": gap.get("bithumb_source_ts"),
        "upbit_source_ts": gap.get("upbit_source_ts"),
        "source_skew_seconds": gap.get("source_skew_seconds"),
        "upbit_vs_bithumb_pct": gap.get("upbit_vs_bithumb_pct"),
        "absolute_gap_pct": gap.get("absolute_gap_pct"),
        "source_timeframe": str(gap.get("source_timeframe") or "1m"),
        "received_at": gap.get("received_at"),
        "paper_only": True,
        "score_wired": False,
    }


def _compact_domestic_premium(source: dict[str, Any]) -> dict[str, Any]:
    premium = source.get("domestic_premium") if isinstance(source.get("domestic_premium"), dict) else {}
    return {
        "feature_version": int(premium.get("feature_version") or 0),
        "status": str(premium.get("status") or "not_available"),
        "identity_verified": bool(premium.get("identity_verified")),
        "provider": str(premium.get("provider") or ""),
        "provider_id": str(premium.get("provider_id") or ""),
        "bithumb_price_krw": premium.get("bithumb_price_krw"),
        "upbit_price_krw": premium.get("upbit_price_krw"),
        "reference_exchange": str(premium.get("reference_exchange") or ""),
        "reference_market": str(premium.get("reference_market") or ""),
        "reference_quote_asset": str(premium.get("reference_quote_asset") or ""),
        "reference_price_krw": premium.get("reference_price_krw"),
        "reference_source_ts": premium.get("reference_source_ts"),
        "bithumb_premium_pct": premium.get("bithumb_premium_pct"),
        "upbit_premium_pct": premium.get("upbit_premium_pct"),
        "foreign_verified_sources": int(premium.get("foreign_verified_sources") or 0),
        "foreign_price_gap_pct": premium.get("foreign_price_gap_pct"),
        "received_at": premium.get("received_at"),
        "paper_only": True,
        "score_wired": False,
    }


def apply_market_feature_projection(source: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Copy precomputed market features into a bounded Cloudflare detail payload."""
    returns = source.get("return_windows") if isinstance(source.get("return_windows"), dict) else {}
    result["return_windows"] = {
        "as_of_ts": returns.get("as_of_ts"),
        "coverage": int(returns.get("coverage") or 0),
        "cumulative_coverage": int(returns.get("cumulative_coverage") or 0),
        "d1_pct": returns.get("d1_pct"),
        "d2_pct": returns.get("d2_pct"),
        "d3_pct": returns.get("d3_pct"),
        "d4_pct": returns.get("d4_pct"),
        "d5_pct": returns.get("d5_pct"),
        "cum_1d_pct": returns.get("cum_1d_pct"),
        "cum_3d_pct": returns.get("cum_3d_pct"),
        "cum_5d_pct": returns.get("cum_5d_pct"),
        "cum_7d_pct": returns.get("cum_7d_pct"),
        "cum_30d_pct": returns.get("cum_30d_pct"),
    }
    result["relative_strength"] = _compact_relative_strength(source)
    result["cross_exchange_gap"] = _compact_cross_exchange_gap(source)
    result["domestic_premium"] = _compact_domestic_premium(source)
    result["lifecycle_state"] = str(source.get("lifecycle_state") or "NORMAL")
    result["version"] = max(8, int(result.get("version") or 0))
    return result
